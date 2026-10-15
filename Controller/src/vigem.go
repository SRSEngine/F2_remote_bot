package main

// "xinput" method: a virtual Xbox 360 controller (ViGEmBus + ViGEmClient.dll next to xbpad.exe).
// The remote is told to follow that controller's XInput number ("xinput N" on its pipe), so a
// program can drive it like a real pad. A real controller works the same way (xbrp -xinput N).

import (
	"errors"
	"fmt"
	"path/filepath"
	"syscall"
	"time"
	"unsafe"
)

const vigemOK = 0x20000000

type xusbReport struct {
	buttons uint16
	lt, rt  uint8
	lx, ly  int16
	rx, ry  int16
}

var xusbBits = map[string]uint16{
	"up": 0x0001, "down": 0x0002, "left": 0x0004, "right": 0x0008, "menu": 0x0010, "view": 0x0020,
	"ls": 0x0040, "rs": 0x0080, "lb": 0x0100, "rb": 0x0200, "nexus": 0x0400, "guide": 0x0400, "xbox": 0x0400,
	"a": 0x1000, "b": 0x2000, "x": 0x4000, "y": 0x8000,
}

type vigemSender struct {
	dll            *syscall.LazyDLL
	client, target uintptr
	idx            int
	rep            xusbReport
	ctl            *pipeSender
}

func (v *vigemSender) call(name string, a ...uintptr) uintptr {
	r, _, _ := v.dll.NewProc(name).Call(a...)
	return r
}

func newVigem(r remote) (*vigemSender, error) {
	v := &vigemSender{dll: syscall.NewLazyDLL(filepath.Join(exeDir(), "ViGEmClient.dll"))}
	if err := v.dll.Load(); err != nil {
		return nil, fmt.Errorf("ViGEmClient.dll: %v", err)
	}
	v.client = v.call("vigem_alloc")
	if e := v.call("vigem_connect", v.client); e != vigemOK {
		return nil, fmt.Errorf("ViGEmBus not reachable (0x%X)", e)
	}
	v.target = v.call("vigem_target_x360_alloc")
	if e := v.call("vigem_target_add", v.client, v.target); e != vigemOK {
		return nil, fmt.Errorf("vigem_target_add 0x%X", e)
	}
	var idx uint32
	for i := 0; i < 20; i++ {
		time.Sleep(50 * time.Millisecond)
		if v.call("vigem_target_x360_get_user_index", v.client, v.target, uintptr(unsafe.Pointer(&idx))) == vigemOK {
			break
		}
	}
	v.idx = int(idx)
	ctl, err := newPipe(r)
	if err != nil {
		v.close()
		return nil, err
	}
	v.ctl = ctl
	if rep, err := ctl.send(fmt.Sprintf("xinput %d", v.idx)); err != nil || rep == "" {
		v.close()
		return nil, errors.New("remote did not accept the controller number")
	}
	time.Sleep(600 * time.Millisecond) // the remote notices the controller
	fmt.Printf("virtual controller = XInput %d, remote follows it\n", v.idx)
	return v, nil
}

func (v *vigemSender) update() {
	r := v.rep
	v.call("vigem_target_x360_update", v.client, v.target, uintptr(unsafe.Pointer(&r)))
}

func (v *vigemSender) set(key string, down bool) error {
	if b, ok := xusbBits[key]; ok {
		if down {
			v.rep.buttons |= b
		} else {
			v.rep.buttons &^= b
		}
		return nil
	}
	val := func(x int16) int16 {
		if down {
			return x
		}
		return 0
	}
	switch key {
	case "lt":
		v.rep.lt = map[bool]uint8{true: 255}[down]
	case "rt":
		v.rep.rt = map[bool]uint8{true: 255}[down]
	case "lsup":
		v.rep.ly = val(32767)
	case "lsdown":
		v.rep.ly = val(-32767)
	case "lsleft":
		v.rep.lx = val(-32767)
	case "lsright":
		v.rep.lx = val(32767)
	case "rsup":
		v.rep.ry = val(32767)
	case "rsdown":
		v.rep.ry = val(-32767)
	case "rsleft":
		v.rep.rx = val(-32767)
	case "rsright":
		v.rep.rx = val(32767)
	default:
		return fmt.Errorf("unknown button %q", key)
	}
	return nil
}

func (v *vigemSender) send(cmd string) (string, error) {
	verb, keys, hold, err := parsePress(cmd)
	if err != nil {
		return "", err
	}
	for _, k := range keys {
		if err := v.set(k, verb != "up"); err != nil {
			return "", err
		}
	}
	v.update()
	if verb == "press" {
		time.Sleep(hold)
		for _, k := range keys {
			_ = v.set(k, false)
		}
		v.update()
	}
	return "updated", nil
}

func (v *vigemSender) close() {
	if v.ctl != nil {
		_, _ = v.ctl.send("xinput off")
		v.ctl.close()
	}
	if v.target != 0 {
		v.call("vigem_target_remove", v.client, v.target)
		v.call("vigem_target_free", v.target)
	}
	if v.client != 0 {
		v.call("vigem_disconnect", v.client)
		v.call("vigem_free", v.client)
	}
}

// cmdPads lists the four XInput slots (which controllers Windows sees).
func cmdPads() {
	dll := syscall.NewLazyDLL("xinput1_4.dll")
	get := dll.NewProc("XInputGetState")
	for i := 0; i < 4; i++ {
		var st [16]byte
		r, _, _ := get.Call(uintptr(i), uintptr(unsafe.Pointer(&st[0])))
		state := "empty"
		if r == 0 {
			state = "connected"
		}
		fmt.Printf("XInput %d: %s\n", i, state)
	}
}
