using System.Diagnostics;
using System.Runtime.InteropServices;

internal static class Program
{
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int MessageBox(IntPtr hWnd, string text, string caption, uint type);

    [STAThread]
    private static void Main(string[] args)
    {
        string root = AppContext.BaseDirectory;
        string python = Path.Combine(root, "python", "pythonw.exe");
        string app = Path.Combine(root, "资料库", "app.py");
        try
        {
            if (!File.Exists(python) || !File.Exists(app))
                throw new FileNotFoundException("请先完整解压便携包，确认启动程序旁的 python 和资料库目录完整。");
            var info = new ProcessStartInfo(python) { UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = root };
            info.ArgumentList.Add(app);
            info.ArgumentList.Add("--root");
            info.ArgumentList.Add(root);
            foreach (string arg in args) info.ArgumentList.Add(arg);
            Process.Start(info);
        }
        catch (Exception e)
        {
            MessageBox(IntPtr.Zero, "无法启动 TweetArchive：" + e.Message, "TweetArchive", 0x10);
        }
    }
}
