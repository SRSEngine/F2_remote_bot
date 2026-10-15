using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Forms;

static class Program
{
    public static string ShotsDir = @"C:\Users\Reach\Desktop\New Remote\Screenshot\Shots";

    [DllImport("user32.dll")] static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] static extern bool SetProcessDpiAwarenessContext(IntPtr ctx);

    [STAThread]
    static void Main()
    {
        bool created;
        using (var m = new Mutex(true, "RemoteShot_SingleInstance", out created))
        {
            if (!created) { MessageBox.Show("RemoteShot در حال اجراست (آیکون کنار ساعت).", "RemoteShot"); return; }
            // Same DPI mode as xbrp (per-monitor v2), so window positions and screen pixels agree.
            bool dpiOk = false;
            try { dpiOk = SetProcessDpiAwarenessContext(new IntPtr(-4)); } catch { }
            if (!dpiOk) { try { SetProcessDPIAware(); } catch { } }
            Directory.CreateDirectory(ShotsDir);
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new HotkeyWindow());
        }
    }
}

class HotkeyWindow : Form
{
    [DllImport("user32.dll")] static extern bool RegisterHotKey(IntPtr h, int id, uint mod, uint vk);
    [DllImport("user32.dll")] static extern bool UnregisterHotKey(IntPtr h, int id);
    const uint MOD_ALT = 1, MOD_CONTROL = 2, MOD_NOREPEAT = 0x4000;
    const int WM_HOTKEY = 0x0312;

    NotifyIcon tray;
    bool busy;

    public HotkeyWindow()
    {
        ShowInTaskbar = false;
        WindowState = FormWindowState.Minimized;
        FormBorderStyle = FormBorderStyle.FixedToolWindow;
        Opacity = 0;

        var menu = new ContextMenuStrip();
        menu.Items.Add("گرفتن اسکرین‌شات (Ctrl+Alt+S)", null, (s, e) => TakeShot());
        menu.Items.Add("باز کردن پوشه Shots", null, (s, e) => System.Diagnostics.Process.Start("explorer.exe", "\"" + Program.ShotsDir + "\""));
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("خروج", null, (s, e) => Close());

        tray = new NotifyIcon
        {
            Icon = SystemIcons.Application,
            Text = "RemoteShot - Ctrl+Alt+S",
            Visible = true,
            ContextMenuStrip = menu
        };
        tray.MouseClick += (s, e) => { if (e.Button == MouseButtons.Left) TakeShot(); };
    }

    protected override void OnLoad(EventArgs e)
    {
        base.OnLoad(e);
        Hide();
        if (!RegisterHotKey(Handle, 1, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, (uint)Keys.S))
            tray.ShowBalloonTip(4000, "RemoteShot", "کلید Ctrl+Alt+S آزاد نیست. با کلیک روی آیکون کنار ساعت عکس بگیرید.", ToolTipIcon.Warning);
        else
            tray.ShowBalloonTip(2500, "RemoteShot", "آماده است. Ctrl+Alt+S را بزنید.", ToolTipIcon.Info);
    }

    protected override void WndProc(ref Message m)
    {
        if (m.Msg == WM_HOTKEY) TakeShot();
        base.WndProc(ref m);
    }

    void TakeShot()
    {
        if (busy) return;
        busy = true;
        List<RemoteWindows.Info> remotes = new List<RemoteWindows.Info>();
        try
        {
            Rectangle vs = SystemInformation.VirtualScreen;
            Bitmap full = new Bitmap(vs.Width, vs.Height, PixelFormat.Format32bppArgb);
            using (var g = Graphics.FromImage(full))
                g.CopyFromScreen(vs.Left, vs.Top, 0, 0, vs.Size, CopyPixelOperation.SourceCopy);

            // Remote windows on screen now; ask each for its real picture in the background.
            remotes = RemoteWindows.List();
            foreach (var r in remotes) r.StartSnap();

            Rectangle sel;
            using (var ov = new SelectOverlay(full, vs))
            {
                if (ov.ShowDialog() != DialogResult.OK) { full.Dispose(); return; }
                sel = ov.Selection;
            }
            Rectangle selScreen = new Rectangle(sel.X + vs.Left, sel.Y + vs.Top, sel.Width, sel.Height);
            Point center = new Point(selScreen.X + selScreen.Width / 2, selScreen.Y + selScreen.Height / 2);

            RemoteWindows.Info hit = null;
            foreach (var r in remotes) if (r.Client.Contains(center)) { hit = r; break; }

            Bitmap crop;
            Rectangle coords;
            string where;
            using (full)
            {
                if (hit != null)
                {
                    // The picture fills the whole client area of the remote window (no black bars).
                    Rectangle c = Rectangle.Intersect(selScreen, hit.Client);
                    Bitmap frame = hit.WaitSnap();
                    Size fs = frame != null ? frame.Size : new Size(1280, 720);
                    double kx = (double)fs.Width / hit.Client.Width, ky = (double)fs.Height / hit.Client.Height;
                    int fx = (int)Math.Round((c.X - hit.Client.X) * kx), fy = (int)Math.Round((c.Y - hit.Client.Y) * ky);
                    int fr = (int)Math.Round((c.Right - hit.Client.X) * kx), fb = (int)Math.Round((c.Bottom - hit.Client.Y) * ky);
                    fr = Math.Min(fr, fs.Width); fb = Math.Min(fb, fs.Height);
                    if (fr <= fx) fr = Math.Min(fx + 1, fs.Width);
                    if (fb <= fy) fb = Math.Min(fy + 1, fs.Height);
                    coords = Rectangle.FromLTRB(fx, fy, fr, fb);
                    where = "ریموت " + hit.Name + " (" + fs.Width + "x" + fs.Height + ")";
                    if (frame != null)
                    {
                        using (frame) crop = frame.Clone(coords, PixelFormat.Format32bppArgb);
                    }
                    else
                    {
                        crop = full.Clone(new Rectangle(c.X - vs.Left, c.Y - vs.Top, c.Width, c.Height), full.PixelFormat);
                        where += " - عکس از مانیتور";
                    }
                }
                else
                {
                    coords = selScreen;
                    where = "بیرون از ریموت: مختصات مانیتور";
                    crop = full.Clone(sel, full.PixelFormat);
                }
            }

            using (crop)
            {
                string info = where + "    x=" + coords.X + " y=" + coords.Y + " w=" + coords.Width + " h=" + coords.Height;
                string name = NameDialog.Ask(crop, info);
                if (name == null) return;
                string path = UniquePath(name);
                crop.Save(path, ImageFormat.Png);
                string line = "(\"" + Path.GetFileNameWithoutExtension(path) + "\", " +
                              coords.X + "," + coords.Y + "," + coords.Width + "," + coords.Height + ")";
                try { Clipboard.SetText(line); } catch { }
                tray.ShowBalloonTip(3000, hit != null ? "ذخیره و کپی شد" : "ذخیره شد (بیرون از ریموت)", line,
                                    hit != null ? ToolTipIcon.Info : ToolTipIcon.Warning);
            }
        }
        catch (Exception ex)
        {
            MessageBox.Show("خطا: " + ex.Message, "RemoteShot");
        }
        finally
        {
            foreach (var r in remotes) r.DropSnap();
            busy = false;
        }
    }

    static string UniquePath(string name)
    {
        foreach (char c in Path.GetInvalidFileNameChars()) name = name.Replace(c, '_');
        name = name.Trim().TrimEnd('.');
        if (name.EndsWith(".png", StringComparison.OrdinalIgnoreCase)) name = name.Substring(0, name.Length - 4);
        if (name.Length == 0) name = "shot_" + DateTime.Now.ToString("yyyy-MM-dd_HH-mm-ss");
        string p = Path.Combine(Program.ShotsDir, name + ".png");
        for (int i = 2; File.Exists(p); i++) p = Path.Combine(Program.ShotsDir, name + " (" + i + ").png");
        return p;
    }

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        UnregisterHotKey(Handle, 1);
        tray.Visible = false;
        tray.Dispose();
        base.OnFormClosing(e);
    }
}

// xbrp video windows (class XBRPVideo): where the picture is on screen, and the real frame via the remote's pipe.
static class RemoteWindows
{
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern IntPtr FindWindowEx(IntPtr parent, IntPtr after, string cls, string title);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] static extern bool GetClientRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] static extern bool ClientToScreen(IntPtr h, ref POINT p);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder sb, int n);
    [StructLayout(LayoutKind.Sequential)] struct RECT { public int L, T, R, B; }
    [StructLayout(LayoutKind.Sequential)] struct POINT { public int X, Y; }

    const string RemotesDir = @"C:\Users\Reach\Desktop\New Remote\Controller\remotes";

    public class Info
    {
        public IntPtr Hwnd;
        public Rectangle Client;
        public string Name = "";
        public string Pipe;
        Thread th;
        volatile Bitmap snap;

        public void StartSnap()
        {
            if (Pipe == null) return;
            string pipe = Pipe;
            th = new Thread(() => { try { snap = Snap(pipe); } catch { } });
            th.IsBackground = true;
            th.Start();
        }
        public Bitmap WaitSnap()
        {
            if (th == null) return null;
            th.Join(3500);
            Bitmap b = snap; snap = null;
            return b;
        }
        public void DropSnap()
        {
            if (th != null) th.Join(3500);
            Bitmap b = snap; snap = null;
            if (b != null) b.Dispose();
        }
    }

    public static List<Info> List()
    {
        // hwnd -> (pipe, name) from Controller\remotes\*.json, written by each running remote
        var pipes = new Dictionary<long, string[]>();
        try
        {
            foreach (var f in Directory.GetFiles(RemotesDir, "*.json"))
            {
                string j = File.ReadAllText(f);
                var mh = Regex.Match(j, "\"hwnd\"\\s*:\\s*(\\d+)");
                var mp = Regex.Match(j, "\"pipe\"\\s*:\\s*\"((?:[^\"\\\\]|\\\\.)*)\"");
                var mn = Regex.Match(j, "\"name\"\\s*:\\s*\"([^\"]*)\"");
                if (mh.Success && mp.Success)
                    pipes[long.Parse(mh.Groups[1].Value)] = new[] {
                        mp.Groups[1].Value.Replace("\\\\", "\\"),
                        mn.Success ? mn.Groups[1].Value : Path.GetFileNameWithoutExtension(f) };
            }
        }
        catch { }

        var list = new List<Info>();
        IntPtr h = IntPtr.Zero;
        while ((h = FindWindowEx(IntPtr.Zero, h, "XBRPVideo", null)) != IntPtr.Zero)
        {
            if (!IsWindowVisible(h) || IsIconic(h)) continue;
            RECT rc;
            if (!GetClientRect(h, out rc) || rc.R <= 0 || rc.B <= 0) continue;
            POINT p = new POINT();
            if (!ClientToScreen(h, ref p)) continue;
            var info = new Info { Hwnd = h, Client = new Rectangle(p.X, p.Y, rc.R, rc.B) };
            string[] pn;
            if (pipes.TryGetValue(h.ToInt64(), out pn)) { info.Pipe = pn[0]; info.Name = pn[1]; }
            else { var sb = new StringBuilder(256); GetWindowText(h, sb, 256); info.Name = sb.ToString(); }
            list.Add(info);
        }
        return list;
    }

    // "snap <file>" on the remote's pipe saves the next decoded picture at the stream's real size (1280x720).
    static Bitmap Snap(string pipe)
    {
        string name = pipe;
        int i = name.LastIndexOf('\\');
        if (i >= 0) name = name.Substring(i + 1);
        string tmp = Path.Combine(Path.GetTempPath(), "remoteshot-" + Guid.NewGuid().ToString("N") + ".png");
        try
        {
            using (var c = new NamedPipeClientStream(".", name, PipeDirection.InOut))
            {
                c.Connect(1500);
                byte[] cmd = Encoding.UTF8.GetBytes("snap " + tmp + "\n");
                c.Write(cmd, 0, cmd.Length);
                c.Flush();
                byte[] buf = new byte[4096];
                int n = c.Read(buf, 0, buf.Length);
                if (!Encoding.UTF8.GetString(buf, 0, n).StartsWith("ok")) return null;
            }
            using (var fs = new FileStream(tmp, FileMode.Open, FileAccess.Read))
            using (var img = Image.FromStream(fs))
                return new Bitmap(img);
        }
        finally { try { File.Delete(tmp); } catch { } }
    }
}

class SelectOverlay : Form
{
    readonly Bitmap shot;
    Point start;
    bool dragging;
    Rectangle rect;
    public Rectangle Selection { get { return rect; } }

    public SelectOverlay(Bitmap shot, Rectangle vs)
    {
        this.shot = shot;
        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.Manual;
        Bounds = vs;
        TopMost = true;
        ShowInTaskbar = false;
        DoubleBuffered = true;
        Cursor = Cursors.Cross;
        KeyPreview = true;
    }

    protected override void OnShown(EventArgs e) { base.OnShown(e); Activate(); }

    protected override void OnKeyDown(KeyEventArgs e)
    {
        if (e.KeyCode == Keys.Escape) { DialogResult = DialogResult.Cancel; Close(); }
    }

    protected override void OnMouseDown(MouseEventArgs e)
    {
        if (e.Button == MouseButtons.Right) { DialogResult = DialogResult.Cancel; Close(); return; }
        dragging = true; start = e.Location; rect = Rectangle.Empty;
    }

    protected override void OnMouseMove(MouseEventArgs e)
    {
        if (!dragging) return;
        rect = Rectangle.FromLTRB(Math.Min(start.X, e.X), Math.Min(start.Y, e.Y), Math.Max(start.X, e.X), Math.Max(start.Y, e.Y));
        rect.Intersect(new Rectangle(Point.Empty, shot.Size));
        Invalidate();
    }

    protected override void OnMouseUp(MouseEventArgs e)
    {
        if (!dragging) return;
        dragging = false;
        if (rect.Width < 3 || rect.Height < 3) { rect = Rectangle.Empty; Invalidate(); return; }
        DialogResult = DialogResult.OK;
        Close();
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics;
        g.DrawImageUnscaled(shot, 0, 0);
        using (var dim = new SolidBrush(Color.FromArgb(120, 0, 0, 0)))
        using (var region = new Region(new Rectangle(Point.Empty, shot.Size)))
        {
            if (rect.Width > 0) region.Exclude(rect);
            g.FillRegion(dim, region);
        }
        if (rect.Width > 0)
        {
            using (var pen = new Pen(Color.DeepSkyBlue, 2)) g.DrawRectangle(pen, rect);
            string sz = rect.Width + " x " + rect.Height;
            using (var f = new Font("Segoe UI", 10))
            using (var bg = new SolidBrush(Color.FromArgb(180, 0, 0, 0)))
            {
                var ts = g.MeasureString(sz, f);
                float y = rect.Top - ts.Height - 4; if (y < 0) y = rect.Top + 4;
                g.FillRectangle(bg, rect.Left, y, ts.Width + 6, ts.Height);
                g.DrawString(sz, f, Brushes.White, rect.Left + 3, y);
            }
        }
        else
        {
            string hint = "ناحیه را با موس انتخاب کنید  |  Esc یا کلیک راست: لغو";
            using (var f = new Font("Segoe UI", 14))
            using (var bg = new SolidBrush(Color.FromArgb(180, 0, 0, 0)))
            {
                var ts = g.MeasureString(hint, f);
                float x = (Width - ts.Width) / 2;
                g.FillRectangle(bg, x - 10, 30, ts.Width + 20, ts.Height + 10);
                g.DrawString(hint, f, Brushes.White, x, 35);
            }
        }
    }
}

static class NameDialog
{
    public static string Ask(Bitmap preview, string info)
    {
        using (var f = new Form())
        {
            f.Text = "اسم اسکرین‌شات";
            f.FormBorderStyle = FormBorderStyle.FixedDialog;
            f.StartPosition = FormStartPosition.CenterScreen;
            f.MinimizeBox = false;
            f.MaximizeBox = false;
            f.TopMost = true;
            f.RightToLeft = RightToLeft.Yes;
            f.RightToLeftLayout = true;
            f.Font = new Font("Segoe UI", 10);
            f.ClientSize = new Size(420, 356);

            var pic = new PictureBox
            {
                Image = preview,
                SizeMode = PictureBoxSizeMode.Zoom,
                Bounds = new Rectangle(10, 10, 400, 220),
                BorderStyle = BorderStyle.FixedSingle
            };
            var where = new Label { Text = info, Bounds = new Rectangle(10, 236, 400, 22), RightToLeft = RightToLeft.No, Font = new Font("Segoe UI", 9) };
            var lbl = new Label { Text = "اسم فایل:", Bounds = new Rectangle(10, 262, 400, 22) };
            var tb = new TextBox
            {
                Text = "shot_" + DateTime.Now.ToString("yyyy-MM-dd_HH-mm-ss"),
                Bounds = new Rectangle(10, 286, 400, 26),
                RightToLeft = RightToLeft.No
            };
            var ok = new Button { Text = "ذخیره", DialogResult = DialogResult.OK, Bounds = new Rectangle(10, 320, 100, 30) };
            var cancel = new Button { Text = "لغو", DialogResult = DialogResult.Cancel, Bounds = new Rectangle(118, 320, 100, 30) };
            f.Controls.AddRange(new Control[] { pic, where, lbl, tb, ok, cancel });
            f.AcceptButton = ok;
            f.CancelButton = cancel;
            f.Shown += (s, e) => { f.Activate(); tb.Focus(); tb.SelectAll(); };
            return f.ShowDialog() == DialogResult.OK ? tb.Text : null;
        }
    }
}
