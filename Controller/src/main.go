// xbpad - press Xbox controller buttons on a running xbrp remote, and compare the ways to do it.
//
//	xbpad list                                   running remotes (from ..\remotes\*.json)
//	xbpad send  -r XBOX [-m pipe] press a        one command (methods below)
//	xbpad snap  -r XBOX out.png                  save the remote's current picture
//	xbpad bench -r XBOX [-n 10] [-methods ...]   latency of every method (Xbox button -> picture changes)
//	xbpad isolation -a XBOX -b TEST              commands sent to one remote never reach the other
//	xbpad smartglass                             look for the old SmartGlass protocol on the LAN (UDP 5050)
//
// Methods: pipe, tcp, udp, wmcopy (WM_COPYDATA), keys (PostMessage key to the remote's window),
// sendinput (real keyboard into the focused remote window), cloud (Xbox Live "InjectKey", no stream needed).
package main

import (
	"bufio"
	"bytes"
	crand "crypto/rand"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

var (
	kernel32 = syscall.NewLazyDLL("kernel32.dll")
	user32   = syscall.NewLazyDLL("user32.dll")

	pQPC                      = kernel32.NewProc("QueryPerformanceCounter")
	pQPF                      = kernel32.NewProc("QueryPerformanceFrequency")
	pOpenProcess              = kernel32.NewProc("OpenProcess")
	pGetExitCodeProcess       = kernel32.NewProc("GetExitCodeProcess")
	pSendMessageTimeoutW      = user32.NewProc("SendMessageTimeoutW")
	pPostMessageW             = user32.NewProc("PostMessageW")
	pMapVirtualKeyW           = user32.NewProc("MapVirtualKeyW")
	pSendInput                = user32.NewProc("SendInput")
	pSetForegroundWindow      = user32.NewProc("SetForegroundWindow")
	pGetForegroundWindow      = user32.NewProc("GetForegroundWindow")
	pKeybdEvent               = user32.NewProc("keybd_event")
	pIsWindow                 = user32.NewProc("IsWindow")
	pGetWindowThreadProcessId = user32.NewProc("GetWindowThreadProcessId")
	pAttachThreadInput        = user32.NewProc("AttachThreadInput")
	pBringWindowToTop         = user32.NewProc("BringWindowToTop")
	pGetCurrentThreadId       = kernel32.NewProc("GetCurrentThreadId")
	qpcHz                     int64
)

func qpc() int64 {
	var v int64
	pQPC.Call(uintptr(unsafe.Pointer(&v)))
	return v
}

func qpcMs(d int64) float64 {
	if qpcHz == 0 {
		pQPF.Call(uintptr(unsafe.Pointer(&qpcHz)))
	}
	return float64(d) * 1000 / float64(qpcHz)
}

func exeDir() string {
	exe, err := os.Executable()
	if err != nil {
		return "."
	}
	return filepath.Dir(exe)
}

// ---- remotes ----

type remote struct {
	Name     string `json:"name"`
	Console  string `json:"console"`
	ServerID string `json:"serverId"`
	PID      int    `json:"pid"`
	Pipe     string `json:"pipe"`
	TCP      string `json:"tcp"`
	UDP      string `json:"udp"`
	HWND     uint64 `json:"hwnd"`
	XInput   int    `json:"xinput"`
}

func alive(pid int) bool {
	h, _, _ := pOpenProcess.Call(0x1000, 0, uintptr(pid)) // PROCESS_QUERY_LIMITED_INFORMATION
	if h == 0 {
		return false
	}
	defer syscall.CloseHandle(syscall.Handle(h))
	var code uint32
	pGetExitCodeProcess.Call(h, uintptr(unsafe.Pointer(&code)))
	return code == 259 // STILL_ACTIVE
}

func remotesDir() string {
	if d := os.Getenv("XBPAD_REMOTES"); d != "" {
		return d
	}
	for _, d := range []string{filepath.Join(exeDir(), "remotes"), filepath.Join(exeDir(), "..", "remotes")} {
		if st, err := os.Stat(d); err == nil && st.IsDir() {
			return d
		}
	}
	return filepath.Join(exeDir(), "remotes")
}

func listRemotes() []remote {
	files, _ := filepath.Glob(filepath.Join(remotesDir(), "*.json"))
	var out []remote
	for _, f := range files {
		b, err := os.ReadFile(f)
		if err != nil {
			continue
		}
		var r remote
		if json.Unmarshal(b, &r) != nil || !alive(r.PID) {
			continue
		}
		out = append(out, r)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Name < out[j].Name })
	return out
}

func findRemote(name string) (remote, error) {
	rs := listRemotes()
	if name == "" && len(rs) == 1 {
		return rs[0], nil
	}
	for _, r := range rs {
		if strings.EqualFold(r.Name, name) || strings.EqualFold(r.Console, name) || strings.EqualFold(r.ServerID, name) {
			return r, nil
		}
	}
	return remote{}, fmt.Errorf("remote %q is not running (xbpad list)", name)
}

// ---- senders ----

type sender interface {
	send(cmd string) (string, error)
	close()
}

type pipeSender struct{ f *os.File }

func newPipe(r remote) (*pipeSender, error) {
	var err error
	for i := 0; i < 50; i++ { // all instances busy: wait a little and try again
		var f *os.File
		if f, err = os.OpenFile(r.Pipe, os.O_RDWR, 0); err == nil {
			return &pipeSender{f}, nil
		}
		if !strings.Contains(err.Error(), "busy") {
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	return nil, err
}
func (p *pipeSender) send(cmd string) (string, error) {
	if _, err := p.f.Write([]byte(cmd + "\n")); err != nil {
		return "", err
	}
	buf := make([]byte, 4096)
	n, err := p.f.Read(buf)
	return strings.TrimSpace(string(buf[:n])), err
}
func (p *pipeSender) close() { p.f.Close() }

type tcpSender struct {
	c  net.Conn
	rd *bufio.Reader
}

func newTCP(r remote) (*tcpSender, error) {
	c, err := net.Dial("tcp", r.TCP)
	if err != nil {
		return nil, err
	}
	return &tcpSender{c, bufio.NewReader(c)}, nil
}
func (t *tcpSender) send(cmd string) (string, error) {
	if _, err := t.c.Write([]byte(cmd + "\n")); err != nil {
		return "", err
	}
	l, err := t.rd.ReadString('\n')
	return strings.TrimSpace(l), err
}
func (t *tcpSender) close() { t.c.Close() }

type udpSender struct{ c net.Conn }

func newUDP(r remote) (*udpSender, error) {
	c, err := net.Dial("udp", r.UDP)
	if err != nil {
		return nil, err
	}
	return &udpSender{c}, nil
}
func (u *udpSender) send(cmd string) (string, error) {
	if _, err := u.c.Write([]byte(cmd)); err != nil {
		return "", err
	}
	_ = u.c.SetReadDeadline(time.Now().Add(2 * time.Second))
	buf := make([]byte, 2048)
	n, err := u.c.Read(buf)
	return string(buf[:n]), err
}
func (u *udpSender) close() { u.c.Close() }

type copyDataStruct struct {
	dwData uintptr
	cbData uint32
	lpData uintptr
}

type wmcopySender struct{ hwnd uintptr }

func (w *wmcopySender) send(cmd string) (string, error) {
	b := []byte(cmd)
	cds := copyDataStruct{dwData: 0x50524258, cbData: uint32(len(b)), lpData: uintptr(unsafe.Pointer(&b[0]))}
	var res uintptr
	r, _, err := pSendMessageTimeoutW.Call(w.hwnd, 0x004A, 0, uintptr(unsafe.Pointer(&cds)), 0x0002 /*SMTO_ABORTIFHUNG*/, 3000, uintptr(unsafe.Pointer(&res)))
	if r == 0 {
		return "", fmt.Errorf("SendMessageTimeout: %v", err)
	}
	if res == 1 {
		return "ok", nil
	}
	return "err (remote said no)", nil
}
func (w *wmcopySender) close() {}

// keyboard keys understood by the remote window (same table as xbrp's ctlserver.go)
var keyVK = map[string]uintptr{
	"up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27, "a": 0x0D, "b": 0x1B,
	"x": 'X', "y": 'Y', "lb": 'Q', "rb": 'E', "lt": 'Z', "rt": 'C',
	"lsup": 'W', "lsdown": 'S', "lsleft": 'A', "lsright": 'D', "rsup": 'I', "rsdown": 'K', "rsleft": 'J', "rsright": 'L',
	"ls": 'F', "rs": 'H', "view": 0x09, "menu": 'M', "nexus": 'G', "guide": 'G', "xbox": 'G',
}

// parsePress turns "press a [ms]" / "down a" / "up a" into keys and a hold time.
func parsePress(cmd string) (verb string, keys []string, hold time.Duration, err error) {
	f := strings.Fields(strings.ToLower(cmd))
	if len(f) > 0 && strings.HasPrefix(f[0], "@") {
		f = f[1:]
	}
	if len(f) < 2 || (f[0] != "press" && f[0] != "down" && f[0] != "up") {
		return "", nil, 0, errors.New("this method only does press/down/up")
	}
	hold = 80 * time.Millisecond
	if len(f) > 2 {
		if ms, e := strconv.Atoi(f[2]); e == nil {
			hold = time.Duration(ms) * time.Millisecond
		}
	}
	return f[0], strings.Split(f[1], "+"), hold, nil
}

type keysSender struct{ hwnd uintptr }

func keyLParam(vk uintptr, up bool) uintptr {
	sc, _, _ := pMapVirtualKeyW.Call(vk, 0)
	lp := uintptr(1) | sc<<16
	if vk >= 0x21 && vk <= 0x28 {
		lp |= 1 << 24 // extended key (arrows, home)
	}
	if up {
		lp |= 0xC0000000
	}
	return lp
}

func (k *keysSender) send(cmd string) (string, error) {
	verb, keys, hold, err := parsePress(cmd)
	if err != nil {
		return "", err
	}
	var vks []uintptr
	for _, key := range keys {
		vk, ok := keyVK[key]
		if !ok {
			return "", fmt.Errorf("no keyboard key for %q", key)
		}
		vks = append(vks, vk)
	}
	if verb != "up" {
		for _, vk := range vks {
			pPostMessageW.Call(k.hwnd, 0x0100, vk, keyLParam(vk, false))
		}
	}
	if verb == "press" {
		time.Sleep(hold)
	}
	if verb != "down" {
		for _, vk := range vks {
			pPostMessageW.Call(k.hwnd, 0x0101, vk, keyLParam(vk, true))
		}
	}
	return "posted", nil
}
func (k *keysSender) close() {}

// sendinputSender: brings the remote window to the front and types like a real keyboard.
type sendinputSender struct{ hwnd uintptr }

type keybdInput struct {
	typ   uint32
	_     uint32
	vk    uint16
	scan  uint16
	flags uint32
	time  uint32
	_     uint32
	extra uintptr
	_     [8]byte
}

func sendKey(vk uintptr, up bool) {
	sc, _, _ := pMapVirtualKeyW.Call(vk, 0)
	in := keybdInput{typ: 1, vk: uint16(vk), scan: uint16(sc)}
	if vk >= 0x21 && vk <= 0x28 {
		in.flags |= 0x1 // KEYEVENTF_EXTENDEDKEY
	}
	if up {
		in.flags |= 0x2
	}
	pSendInput.Call(1, uintptr(unsafe.Pointer(&in)), unsafe.Sizeof(in))
}

func (s *sendinputSender) send(cmd string) (string, error) {
	verb, keys, hold, err := parsePress(cmd)
	if err != nil {
		return "", err
	}
	if fg, _, _ := pGetForegroundWindow.Call(); fg != s.hwnd {
		defer func() { // give the focus back to the window the user was in
			pKeybdEvent.Call(0x12, 0, 0, 0)
			pKeybdEvent.Call(0x12, 0, 2, 0)
			pSetForegroundWindow.Call(fg)
		}()
		// Windows only lets the foreground owner change focus: join its input queue for a moment.
		fgThread, _, _ := pGetWindowThreadProcessId.Call(fg, 0)
		me, _, _ := pGetCurrentThreadId.Call()
		pAttachThreadInput.Call(me, fgThread, 1)
		pKeybdEvent.Call(0x12, 0, 0, 0) // a tap of Alt also unlocks SetForegroundWindow
		pKeybdEvent.Call(0x12, 0, 2, 0)
		pBringWindowToTop.Call(s.hwnd)
		pSetForegroundWindow.Call(s.hwnd)
		pAttachThreadInput.Call(me, fgThread, 0)
		time.Sleep(30 * time.Millisecond)
		if fg2, _, _ := pGetForegroundWindow.Call(); fg2 != s.hwnd {
			return "", errors.New("could not bring the remote window to the front")
		}
	}
	for _, key := range keys {
		vk, ok := keyVK[key]
		if !ok {
			return "", fmt.Errorf("no keyboard key for %q", key)
		}
		if verb != "up" {
			sendKey(vk, false)
		}
		if verb == "press" {
			time.Sleep(hold)
		}
		if verb != "down" {
			sendKey(vk, true)
		}
	}
	return "typed", nil
}
func (s *sendinputSender) close() {}

func newSender(r remote, method string) (sender, error) {
	switch method {
	case "pipe":
		return newPipe(r)
	case "tcp":
		return newTCP(r)
	case "udp":
		return newUDP(r)
	case "wmcopy":
		if ok, _, _ := pIsWindow.Call(uintptr(r.HWND)); ok == 0 {
			return nil, errors.New("remote window not found")
		}
		return &wmcopySender{uintptr(r.HWND)}, nil
	case "keys":
		return &keysSender{uintptr(r.HWND)}, nil
	case "sendinput":
		return &sendinputSender{uintptr(r.HWND)}, nil
	case "cloud":
		return newCloud(r.ServerID)
	case "xinput":
		return newVigem(r)
	}
	return nil, fmt.Errorf("unknown method %q", method)
}

// ---- cloud: Xbox Live SmartGlass REST "InjectKey" (what the phone app's remote uses) ----

type cloudSender struct {
	auth    string
	console string
	session string
	client  *http.Client
}

var cloudKeys = map[string]string{"a": "A", "b": "B", "x": "X", "y": "Y", "up": "Up", "down": "Down", "left": "Left", "right": "Right",
	"nexus": "Nexus", "guide": "Nexus", "xbox": "Nexus", "menu": "Menu", "view": "View"}

func tokenPath() string {
	if p := os.Getenv("XBPAD_TOKEN"); p != "" {
		return p
	}
	for _, p := range []string{filepath.Join(exeDir(), "..", "CPU Decode", "xbrp_token.json"), filepath.Join(exeDir(), "xbrp_token.json")} {
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	return "xbrp_token.json"
}

func postJSON(c *http.Client, u string, hdr map[string]string, body any, out any) (int, []byte, error) {
	b, _ := json.Marshal(body)
	req, _ := http.NewRequest("POST", u, bytes.NewReader(b))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	for k, v := range hdr {
		req.Header.Set(k, v)
	}
	resp, err := c.Do(req)
	if err != nil {
		return 0, nil, err
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(resp.Body)
	if out != nil {
		_ = json.Unmarshal(data, out)
	}
	return resp.StatusCode, data, nil
}

func newCloud(console string) (*cloudSender, error) {
	c := &http.Client{Timeout: 15 * time.Second}
	tp := tokenPath()
	b, err := os.ReadFile(tp)
	if err != nil {
		return nil, fmt.Errorf("login file: %v", err)
	}
	var saved map[string]any
	if err := json.Unmarshal(b, &saved); err != nil {
		return nil, err
	}
	rt, _ := saved["refresh_token"].(string)
	cid, _ := saved["client_id"].(string)
	if cid == "" {
		cid = "000000004C12AE6F"
	}
	form := url.Values{"grant_type": {"refresh_token"}, "refresh_token": {rt}, "client_id": {cid}, "scope": {"service::user.auth.xboxlive.com::MBI_SSL"}}
	resp, err := c.PostForm("https://login.live.com/oauth20_token.srf", form)
	if err != nil {
		return nil, err
	}
	data, _ := io.ReadAll(resp.Body)
	resp.Body.Close()
	var t map[string]any
	_ = json.Unmarshal(data, &t)
	at, _ := t["access_token"].(string)
	if at == "" {
		return nil, fmt.Errorf("Microsoft login refresh failed (HTTP %d)", resp.StatusCode)
	}
	if nrt, _ := t["refresh_token"].(string); nrt != "" { // keep the login file current, like xbrp does
		saved["access_token"], saved["refresh_token"] = at, nrt
		if nb, err := json.MarshalIndent(saved, "", "  "); err == nil {
			_ = os.WriteFile(tp, nb, 0o600)
		}
	}
	var ut struct{ Token string }
	if code, _, err := postJSON(c, "https://user.auth.xboxlive.com/user/authenticate", map[string]string{"x-xbl-contract-version": "1"},
		map[string]any{"RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT",
			"Properties": map[string]any{"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": at}}, &ut); err != nil || ut.Token == "" {
		return nil, fmt.Errorf("Xbox user token failed (HTTP %d, %v)", code, err)
	}
	var xs struct {
		Token         string
		DisplayClaims struct {
			Xui []struct {
				Uhs string `json:"uhs"`
			} `json:"xui"`
		}
	}
	if code, _, err := postJSON(c, "https://xsts.auth.xboxlive.com/xsts/authorize", map[string]string{"x-xbl-contract-version": "1"},
		map[string]any{"RelyingParty": "http://xboxlive.com", "TokenType": "JWT",
			"Properties": map[string]any{"SandboxId": "RETAIL", "UserTokens": []string{ut.Token}}}, &xs); err != nil || xs.Token == "" || len(xs.DisplayClaims.Xui) == 0 {
		return nil, fmt.Errorf("XSTS (xboxlive.com) failed (HTTP %d, %v)", code, err)
	}
	return &cloudSender{auth: "XBL3.0 x=" + xs.DisplayClaims.Xui[0].Uhs + ";" + xs.Token, console: console, session: newUUID(), client: c}, nil
}

func newUUID() string {
	var b [16]byte
	_, _ = crand.Read(b[:])
	b[6] = b[6]&0x0f | 0x40
	b[8] = b[8]&0x3f | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:])
}

func (c *cloudSender) hdr() map[string]string {
	return map[string]string{"Authorization": c.auth, "x-xbl-contract-version": "4", "skillplatform": "RemoteManagement"}
}

func (c *cloudSender) injectKey(key string) (string, error) {
	body := map[string]any{"destination": "Xbox", "type": "Shell", "command": "InjectKey", "sessionId": c.session,
		"sourceId": "com.microsoft.smartglass", "parameters": []map[string]string{{"keyType": key}}, "linkedXboxId": c.console}
	var r struct {
		Status struct {
			ErrorCode    string `json:"errorCode"`
			ErrorMessage string `json:"errorMessage"`
		} `json:"status"`
	}
	code, data, err := postJSON(c.client, "https://xccs.xboxlive.com/commands", c.hdr(), body, &r)
	if err != nil {
		return "", err
	}
	if code != 200 || r.Status.ErrorCode != "OK" {
		s := string(data)
		if len(s) > 200 {
			s = s[:200]
		}
		return "", fmt.Errorf("HTTP %d %s %s", code, r.Status.ErrorCode, s)
	}
	return "ok", nil
}

func (c *cloudSender) send(cmd string) (string, error) {
	verb, keys, _, err := parsePress(cmd)
	if err != nil {
		return "", err
	}
	if verb != "press" {
		return "", errors.New("cloud can only tap a button (no hold / down / up)")
	}
	var out []string
	for _, k := range keys {
		ck, ok := cloudKeys[k]
		if !ok {
			ck = k // try it anyway (to find out what the service accepts)
		}
		r, err := c.injectKey(ck)
		if err != nil {
			return "", err
		}
		out = append(out, r)
	}
	return strings.Join(out, ","), nil
}
func (c *cloudSender) close() {}

// ---- commands ----

func must(err error) {
	if err != nil {
		fmt.Println("ERROR:", err)
		os.Exit(1)
	}
}

func cmdList() {
	rs := listRemotes()
	if len(rs) == 0 {
		fmt.Println("no remote is running (folder", remotesDir()+")")
		return
	}
	for _, r := range rs {
		fmt.Printf("%-12s console=%-10s pid=%-6d pipe=%s tcp=%s udp=%s hwnd=0x%X xinput=%d\n", r.Name, r.Console, r.PID, r.Pipe, r.TCP, r.UDP, r.HWND, r.XInput)
	}
}

func cmdSend(args []string) {
	fs := flag.NewFlagSet("send", flag.ExitOnError)
	rn := fs.String("r", "", "remote name (console name)")
	m := fs.String("m", "pipe", "method: pipe tcp udp wmcopy keys sendinput xinput cloud")
	_ = fs.Parse(args)
	r, err := findRemote(*rn)
	must(err)
	s, err := newSender(r, *m)
	must(err)
	defer s.close()
	cmd := strings.Join(fs.Args(), " ")
	t0 := qpc()
	if *m == "pipe" || *m == "tcp" || *m == "udp" || *m == "wmcopy" {
		cmd = fmt.Sprintf("@%d %s", t0, cmd)
	}
	rep, err := s.send(cmd)
	must(err)
	fmt.Printf("%s  (call %.3f ms)\n", rep, qpcMs(qpc()-t0))
	if strings.HasPrefix(fs.Arg(0), "press") || strings.HasPrefix(fs.Arg(0), "down") || strings.HasPrefix(fs.Arg(0), "up") {
		time.Sleep(10 * time.Millisecond)
	}
}

func cmdSnap(args []string) {
	fs := flag.NewFlagSet("snap", flag.ExitOnError)
	rn := fs.String("r", "", "remote name")
	_ = fs.Parse(args)
	r, err := findRemote(*rn)
	must(err)
	p, err := newPipe(r)
	must(err)
	defer p.close()
	out, _ := filepath.Abs(fs.Arg(0))
	rep, err := p.send("snap " + out)
	must(err)
	fmt.Println(rep)
}

func field(rep, key string) string {
	for _, f := range strings.Fields(rep) {
		if strings.HasPrefix(f, key+"=") {
			return strings.TrimPrefix(f, key+"=")
		}
	}
	return ""
}

type trial struct {
	Method  string  `json:"method"`
	CallMs  float64 `json:"call_ms"`  // time until the sending call returned
	LocalMs float64 `json:"local_ms"` // client send -> report handed to the stream's input channel (-1 = not measurable)
	E2EMs   float64 `json:"e2e_ms"`   // client send -> first decoded picture that changed (-1 = no change)
	Note    string  `json:"note,omitempty"`
}

func cmdBench(args []string) {
	fs := flag.NewFlagSet("bench", flag.ExitOnError)
	rn := fs.String("r", "", "remote name")
	n := fs.Int("n", 10, "trials per method")
	methods := fs.String("methods", "pipe,tcp,udp,wmcopy,keys,sendinput,xinput,cloud", "methods to test")
	pct := fs.Int("pct", 2, "percent of the picture that must change")
	gap := fs.Int("gap", 900, "ms between trials")
	out := fs.String("out", filepath.Join(exeDir(), "results", "bench-"+time.Now().Format("20060102-150405")+".json"), "result file")
	_ = fs.Parse(args)
	r, err := findRemote(*rn)
	must(err)
	ctl, err := newPipe(r)
	must(err)
	defer ctl.close()
	var all []trial
	senders := map[string]sender{}
	ms := strings.Split(*methods, ",")
	for _, m := range ms {
		s, err := newSender(r, m)
		if err != nil {
			fmt.Printf("%-10s not available: %v\n", m, err)
			all = append(all, trial{Method: m, LocalMs: -1, E2EMs: -1, Note: "not available: " + err.Error()})
			continue
		}
		senders[m] = s
		defer s.close()
	}
	// Round robin (pipe, tcp, ..., pipe, tcp, ...) so Wi-Fi hiccups hit every method alike.
	// D-pad right / left only moves the selection on the Home screen: safe to repeat.
	for i := 0; i < *n; i++ {
		for mi, m := range ms {
			s := senders[m]
			if s == nil {
				continue
			}
			dir := "right" // every method alternates right / left from round to round
			if (mi+i)%2 == 1 {
				dir = "left"
			}
			lastRep, _ := ctl.send("last")
			lastN := field(lastRep, "n")
			t0 := qpc()
			_, _ = ctl.send(fmt.Sprintf("@%d probe now %d", t0, *pct))
			time.Sleep(40 * time.Millisecond) // baseline picture
			cmd := "press " + dir + " 80"
			ts := qpc()
			if m == "pipe" || m == "tcp" || m == "udp" || m == "wmcopy" {
				cmd = fmt.Sprintf("@%d %s", ts, cmd)
			}
			_, err := s.send(cmd)
			call := qpcMs(qpc() - ts)
			tr := trial{Method: m, CallMs: call, LocalMs: -1, E2EMs: -1}
			if err != nil {
				tr.Note = err.Error()
				fmt.Printf("%-10s #%d ERROR %v\n", m, i+1, err)
				all = append(all, tr)
				continue
			}
			if m != "cloud" {
				for w := 0; w < 50; w++ {
					lr, _ := ctl.send("last " + lastN)
					if !strings.Contains(lr, "none") {
						if sq, err := strconv.ParseInt(field(lr, "sent_qpc"), 10, 64); err == nil {
							tr.LocalMs = qpcMs(sq - ts)
						}
						break
					}
					time.Sleep(5 * time.Millisecond)
				}
			}
			for w := 0; w < 80; w++ {
				pr, _ := ctl.send("probe?")
				if !strings.Contains(pr, "pending") {
					if strings.Contains(pr, " ms") {
						v, _ := strconv.ParseFloat(strings.Fields(strings.TrimPrefix(pr, "ok "))[0], 64)
						tr.E2EMs = v - qpcMs(ts-t0)
					} else {
						tr.Note = strings.TrimPrefix(pr, "ok ")
					}
					break
				}
				time.Sleep(25 * time.Millisecond)
			}
			fmt.Printf("%-10s #%-2d %-5s call %7.2f ms  local %7.3f ms  e2e %7.1f ms %s\n", m, i+1, dir, tr.CallMs, tr.LocalMs, tr.E2EMs, tr.Note)
			all = append(all, tr)
			time.Sleep(time.Duration(*gap) * time.Millisecond)
		}
	}
	b, _ := json.MarshalIndent(all, "", "  ")
	_ = os.MkdirAll(filepath.Dir(*out), 0o755)
	_ = os.WriteFile(*out, b, 0o644)
	fmt.Println("saved", *out)
	summarize(all)
}

func median(v []float64) float64 {
	if len(v) == 0 {
		return -1
	}
	sort.Float64s(v)
	if len(v)%2 == 1 {
		return v[len(v)/2]
	}
	return (v[len(v)/2-1] + v[len(v)/2]) / 2
}

func summarize(all []trial) {
	order := []string{}
	by := map[string][]trial{}
	for _, t := range all {
		if _, ok := by[t.Method]; !ok {
			order = append(order, t.Method)
		}
		by[t.Method] = append(by[t.Method], t)
	}
	fmt.Println("\nmethod      ok/n   call(med)  local(med)  e2e(med)  e2e(min)  e2e(max)")
	for _, m := range order {
		var call, local, e2e []float64
		ok := 0
		for _, t := range by[m] {
			if t.Note == "" || t.E2EMs >= 0 {
				call = append(call, t.CallMs)
			}
			if t.LocalMs >= 0 {
				local = append(local, t.LocalMs)
			}
			if t.E2EMs >= 0 {
				e2e = append(e2e, t.E2EMs)
				ok++
			}
		}
		mn, mx := -1.0, -1.0
		if len(e2e) > 0 {
			s := append([]float64(nil), e2e...)
			sort.Float64s(s)
			mn, mx = s[0], s[len(s)-1]
		}
		fmt.Printf("%-10s %2d/%-3d %8.2f  %10.3f  %8.1f  %8.1f  %8.1f\n", m, ok, len(by[m]), median(call), median(local), median(e2e), mn, mx)
	}
}

// isolation: every method sends to remote B; remote A's command counters must not move (and the other way round).
func cmdIsolation(args []string) {
	fs := flag.NewFlagSet("isolation", flag.ExitOnError)
	an := fs.String("a", "", "first remote")
	bn := fs.String("b", "", "second remote")
	methods := fs.String("methods", "pipe,tcp,udp,wmcopy,keys", "methods")
	cmd := fs.String("cmd", "press rs 30", "harmless command to send")
	_ = fs.Parse(args)
	ra, err := findRemote(*an)
	must(err)
	rb, err := findRemote(*bn)
	must(err)
	stats := func(r remote) string {
		p, err := newPipe(r)
		if err != nil {
			return "?"
		}
		defer p.close()
		s, _ := p.send("stats")
		return s[strings.Index(s, "counts{"):]
	}
	fmt.Printf("%-8s %-6s  %-45s %-45s %s\n", "method", "target", "counts on "+ra.Name+" (after)", "counts on "+rb.Name+" (after)", "result")
	for _, target := range []remote{rb, ra} {
		other := ra
		if target.Name == ra.Name {
			other = rb
		}
		for _, m := range strings.Split(*methods, ",") {
			beforeT, beforeO := stats(target), stats(other)
			s, err := newSender(target, m)
			if err != nil {
				fmt.Printf("%-8s %-6s  not available: %v\n", m, target.Name, err)
				continue
			}
			_, err = s.send(*cmd)
			s.close()
			time.Sleep(150 * time.Millisecond)
			afterT, afterO := stats(target), stats(other)
			res := "OK (only the target got it)"
			if err != nil {
				res = "send error: " + err.Error()
			} else if afterT == beforeT {
				res = "FAIL: target did not get it"
			} else if afterO != beforeO {
				res = "FAIL: the OTHER remote got it too"
			}
			ca, cb := afterT, afterO
			if target.Name != ra.Name {
				ca, cb = afterO, afterT
			}
			fmt.Printf("%-8s %-6s  %-45s %-45s %s\n", m, target.Name, ca, cb, res)
		}
	}
}

// smartglass: the old local Xbox One protocol (UDP 5050). Discovery request, wait for answers.
func cmdSmartglass(args []string) {
	fs := flag.NewFlagSet("smartglass", flag.ExitOnError)
	ip := fs.String("ip", "255.255.255.255", "console IP (default: broadcast)")
	_ = fs.Parse(args)
	pc, err := net.ListenPacket("udp4", ":0")
	must(err)
	defer pc.Close()
	payload := []byte{0, 0, 0, 0, 0, 8, 0, 0, 0, 2} // flags u32, client type 8 (Windows Store), min ver 0, max ver 2
	pkt := append([]byte{0xDD, 0x00, 0, byte(len(payload)), 0, 0}, payload...)
	dst := &net.UDPAddr{IP: net.ParseIP(*ip), Port: 5050}
	t0 := time.Now()
	for i := 0; i < 3; i++ {
		_, err = pc.WriteTo(pkt, dst)
		must(err)
		time.Sleep(100 * time.Millisecond)
	}
	_ = pc.SetReadDeadline(time.Now().Add(3 * time.Second))
	buf := make([]byte, 4096)
	found := 0
	for {
		n, from, err := pc.ReadFrom(buf)
		if err != nil {
			break
		}
		if n >= 2 && buf[0] == 0xDD && buf[1] == 0x01 {
			found++
			name := ""
			if n > 18 {
				l := int(buf[16])<<8 | int(buf[17])
				if 18+l <= n {
					name = string(buf[18 : 18+l])
				}
			}
			fmt.Printf("SmartGlass answer from %s after %v (%d bytes) name=%q\n", from, time.Since(t0).Round(time.Millisecond), n, name)
		}
	}
	if found == 0 {
		fmt.Println("no SmartGlass answer on UDP 5050 within 3 s")
	}
}

func main() {
	if len(os.Args) < 2 {
		fmt.Println("usage: xbpad list | send -r NAME [-m METHOD] press a | snap -r NAME file.png | bench -r NAME | isolation -a A -b B | smartglass")
		os.Exit(2)
	}
	switch os.Args[1] {
	case "list":
		cmdList()
	case "send":
		cmdSend(os.Args[2:])
	case "snap":
		cmdSnap(os.Args[2:])
	case "bench":
		cmdBench(os.Args[2:])
	case "isolation":
		cmdIsolation(os.Args[2:])
	case "smartglass":
		cmdSmartglass(os.Args[2:])
	case "pads":
		cmdPads()
	default:
		fmt.Println("unknown command", os.Args[1])
		os.Exit(2)
	}
}
