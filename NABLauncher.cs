// NAB Launcher - shows an animated splash instantly, starts NAB.exe, and closes the splash
// when NAB signals that its window is up. C# 5 compatible (built with the csc.exe that ships with Windows).
using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

[assembly: AssemblyTitle("News Automation Bot")]
[assembly: AssemblyProduct("NAB - News Automation Bot")]
[assembly: AssemblyDescription("NAB launcher")]
[assembly: AssemblyVersion("1.0.0.0")]

namespace NabLauncher
{
    // Per-pixel-alpha splash: the artwork floats on the desktop with no window frame or background box.
    class SplashForm : Form
    {
        const double BaseW = 640.0, BaseH = 427.0;
        [StructLayout(LayoutKind.Sequential)] struct PT { public int x, y; }
        [StructLayout(LayoutKind.Sequential)] struct SZ { public int cx, cy; }
        [StructLayout(LayoutKind.Sequential, Pack = 1)] struct BLEND { public byte Op, Flags, Alpha, Format; }
        [DllImport("user32.dll", SetLastError = true)] static extern bool UpdateLayeredWindow(IntPtr hwnd, IntPtr hdcDst, ref PT pptDst, ref SZ psize, IntPtr hdcSrc, ref PT pprSrc, int crKey, ref BLEND pblend, int dwFlags);
        [DllImport("user32.dll")] static extern IntPtr GetDC(IntPtr hWnd);
        [DllImport("user32.dll")] static extern int ReleaseDC(IntPtr hWnd, IntPtr hDC);
        [DllImport("gdi32.dll")] static extern IntPtr CreateCompatibleDC(IntPtr hDC);
        [DllImport("gdi32.dll")] static extern bool DeleteDC(IntPtr hDC);
        [DllImport("gdi32.dll")] static extern IntPtr SelectObject(IntPtr hDC, IntPtr hObj);
        [DllImport("gdi32.dll")] static extern bool DeleteObject(IntPtr hObj);

        const int MFrames = 7, MCellW = 194, MCellH = 300;
        Bitmap art, strip; DateTime t0 = DateTime.UtcNow; float angle; System.Windows.Forms.Timer tick; float scale; bool closing; double fade;
        int W, H; PT pos;

        public SplashForm()
        {
            using (Graphics g0 = Graphics.FromHwnd(IntPtr.Zero)) { scale = Math.Max(1f, g0.DpiX / 96f); }
            FormBorderStyle = FormBorderStyle.None; ShowInTaskbar = false; TopMost = true; StartPosition = FormStartPosition.Manual;
            Rectangle wa = Screen.PrimaryScreen.Bounds; W = wa.Width; H = wa.Height;
            pos.x = wa.Left; pos.y = wa.Top;
            Bounds = new Rectangle(pos.x, pos.y, W, H);
            tick = new System.Windows.Forms.Timer(); tick.Interval = 33;
            tick.Tick += delegate
            {
                angle = (angle + 8f) % 360f;
                fade = closing ? fade : 1;
                Present();
            };
        }

        protected override CreateParams CreateParams
        {
            get { CreateParams cp = base.CreateParams; cp.ExStyle |= 0x80000 | 0x80; return cp; }   // WS_EX_LAYERED | WS_EX_TOOLWINDOW
        }
        protected override bool ShowWithoutActivation { get { return true; } }

        protected override void OnShown(EventArgs e) { base.OnShown(e); fade = 1; Present(); }

        public static void DrawSpinner(Graphics g, float W, float H, float angle)
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            float u = Math.Min(W, H), cx = W * 0.5f, cy = H * 0.5f, r = u * 0.035f, pw = Math.Max(2f, u * 0.006f);
            RectangleF rc = new RectangleF(cx - r, cy - r, r * 2, r * 2);
            using (Pen track = new Pen(Color.FromArgb(90, 91, 140, 255), pw)) g.DrawEllipse(track, rc);
            using (Pen glow = new Pen(Color.FromArgb(70, 91, 140, 255), pw * 2.8f)) { glow.StartCap = LineCap.Round; glow.EndCap = LineCap.Round; g.DrawArc(glow, rc, angle, 100f); }
            using (Pen arc = new Pen(Color.FromArgb(255, 150, 185, 255), pw)) { arc.StartCap = LineCap.Round; arc.EndCap = LineCap.Round; g.DrawArc(arc, rc, angle, 100f); }
            using (Pen arc2 = new Pen(Color.FromArgb(170, 91, 140, 255), pw)) { arc2.StartCap = LineCap.Round; arc2.EndCap = LineCap.Round; g.DrawArc(arc2, rc, angle + 180f, 50f); }
        }

        void Present()
        {
            if (!IsHandleCreated) return;
            using (Bitmap frame = new Bitmap(W, H, PixelFormat.Format32bppArgb))
            {
                using (Graphics g = Graphics.FromImage(frame))
                {
                    g.Clear(Color.FromArgb(255, 11, 12, 19));
                }
                IntPtr screenDc = GetDC(IntPtr.Zero), memDc = CreateCompatibleDC(screenDc), hBmp = IntPtr.Zero, old = IntPtr.Zero;
                try
                {
                    hBmp = frame.GetHbitmap(Color.FromArgb(0));
                    old = SelectObject(memDc, hBmp);
                    SZ size = new SZ(); size.cx = W; size.cy = H;
                    PT src = new PT(); PT dst = pos;
                    BLEND bl = new BLEND(); bl.Op = 0; bl.Flags = 0; bl.Alpha = (byte)(255 * Math.Max(0, Math.Min(1, fade))); bl.Format = 1;   // AC_SRC_OVER, AC_SRC_ALPHA
                    UpdateLayeredWindow(Handle, screenDc, ref dst, ref size, memDc, ref src, 0, ref bl, 2);
                }
                finally
                {
                    if (old != IntPtr.Zero) SelectObject(memDc, old);
                    if (hBmp != IntPtr.Zero) DeleteObject(hBmp);
                    DeleteDC(memDc); ReleaseDC(IntPtr.Zero, screenDc);
                }
            }
        }

        public void FadeAndClose()
        {
            if (closing) return; closing = true;
            System.Windows.Forms.Timer f = new System.Windows.Forms.Timer(); f.Interval = 25;
            f.Tick += delegate { fade -= 0.12; if (fade <= 0.02) { f.Stop(); tick.Stop(); Close(); } else Present(); };
            f.Start();
        }
    }

    static class Program
    {
        [DllImport("user32.dll")] static extern bool SetProcessDPIAware();

        [STAThread]
        static int Main(string[] args)
        {
            bool created;
            Mutex once = new Mutex(true, "Local\\NAB_Launcher_Once", out created);
            if (!created) return 0;                                   // a launch is already in progress

            try { SetProcessDPIAware(); } catch { }
            string dir = AppDomain.CurrentDomain.BaseDirectory;
            string core = Path.Combine(dir, "NAB.exe");
            if (!File.Exists(core))
            {
                MessageBox.Show("NAB.exe was not found next to the launcher:\n" + dir, "News Automation Bot", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }

            EventWaitHandle ready = new EventWaitHandle(false, EventResetMode.ManualReset, "Local\\NAB_Splash_Ready");
            ready.Reset();
            Process p;
            try
            {
                ProcessStartInfo si = new ProcessStartInfo(core);
                si.WorkingDirectory = dir; si.UseShellExecute = false;
                if (args.Length > 0) si.Arguments = string.Join(" ", args);
                p = Process.Start(si);
            }
            catch (Exception ex)
            {
                MessageBox.Show("Could not start NAB:\n" + ex.Message, "News Automation Bot", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }

            Application.EnableVisualStyles();
            SplashForm f = new SplashForm();
            Thread waiter = new Thread(delegate()
            {
                try
                {
                    // wait until NAB says its window is up, or the process ends, or 2 minutes pass
                    DateTime end = DateTime.UtcNow.AddSeconds(120);
                    while (DateTime.UtcNow < end)
                    {
                        if (ready.WaitOne(150)) { Thread.Sleep(700); break; }   // short pause so the window is really on screen
                        if (p != null && p.HasExited) break;
                    }
                }
                catch { }
                try { f.BeginInvoke(new MethodInvoker(f.FadeAndClose)); } catch { }
            });
            waiter.IsBackground = true; waiter.Start();
            Application.Run(f);
            GC.KeepAlive(once);
            return 0;
        }
    }
}
