using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

internal sealed class EduScanLauncher : Form
{
    private const string BuiltForCheckout = @"__EDUSCAN_CHECKOUT__";
    private readonly string checkout;
    private readonly ComboBox databaseMode = new ComboBox();
    private readonly TextBox status = new TextBox();
    private readonly List<Button> actions = new List<Button>();
    private bool busy;

    [STAThread]
    private static void Main(string[] args)
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        try
        {
            string folder = FindCheckout(args);
            bool created;
            using (var mutex = new Mutex(true, @"Local\EduScanDesktopLauncher", out created))
            {
                if (!created)
                {
                    MessageBox.Show("EduScan Launcher is already open.", "EduScan Launcher");
                    return;
                }

                try { Application.Run(new EduScanLauncher(folder)); }
                finally { mutex.ReleaseMutex(); }
            }
        }
        catch (Exception error)
        {
            MessageBox.Show(error.Message, "EduScan Launcher", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private static string FindCheckout(string[] args)
    {
        string executableFolder = AppDomain.CurrentDomain.BaseDirectory;
        string[] candidates = {
            args.Length > 0 ? args[0] : BuiltForCheckout,
            executableFolder,
            Path.Combine(executableFolder, "..", "EduScan")
        };
        foreach (string candidate in candidates)
        {
            string folder = Path.GetFullPath(candidate);
            if (File.Exists(Path.Combine(folder, "scripts", "manage-eduscan.ps1")))
                return folder;
        }
        throw new DirectoryNotFoundException("The EduScan checkout could not be found. Open the launcher from the EduScan folder.");
    }

    private EduScanLauncher(string folder)
    {
        checkout = folder;
        Text = "EduScan Launcher";
        Font = new Font("Segoe UI", 10);
        AutoScaleMode = AutoScaleMode.Font;
        ClientSize = new Size(604, 244);
        StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        FormClosing += delegate(object sender, FormClosingEventArgs e) { e.Cancel = busy; };

        Controls.Add(new Label { Text = "Database mode", AutoSize = true, Location = new Point(12, 19) });
        databaseMode.AccessibleName = "Database mode";
        databaseMode.DropDownStyle = ComboBoxStyle.DropDownList;
        databaseMode.SetBounds(135, 15, 232, 28);
        databaseMode.Items.AddRange(new object[] { "Configured database", "Offline (local SQLite)" });
        databaseMode.SelectedIndex = 0;
        Controls.Add(databaseMode);

        AddAction("Start EduScan", "start");
        AddAction("Restart EduScan", "restart");
        AddAction("Close EduScan", "stop");
        AddAction("Start API Server", "start-api");

        status.AccessibleName = "EduScan status";
        status.Multiline = true;
        status.ReadOnly = true;
        status.ScrollBars = ScrollBars.Vertical;
        status.SetBounds(12, 103, 580, 129);
        status.Text = "Offline mode uses a separate local database. Start EduScan opens the site in your browser.";
        Controls.Add(status);
    }

    private void AddAction(string label, string action)
    {
        var button = new Button { Text = label, Tag = action };
        button.SetBounds(12 + actions.Count * 146, 52, 138, 38);
        button.Click += RunAction;
        actions.Add(button);
        Controls.Add(button);
    }

    private async void RunAction(object sender, EventArgs e)
    {
        var action = (string)((Button)sender).Tag;
        string manager = Path.Combine(checkout, "scripts", "manage-eduscan.ps1");
        string mode = databaseMode.SelectedIndex == 1 ? " -Offline" : "";
        var startInfo = new ProcessStartInfo {
            FileName = Path.Combine(Environment.SystemDirectory, "WindowsPowerShell", "v1.0", "powershell.exe"),
            Arguments = "-NoProfile -STA -ExecutionPolicy Bypass -File \"" + manager +
                "\" -ShowDatabasePrompt -OpenBrowser -Action " + action + mode,
            WorkingDirectory = checkout,
            CreateNoWindow = true,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true
        };

        SetBusy(true);
        status.Text = "Working...";
        try
        {
            using (Process process = Process.Start(startInfo))
            {
                Task<string> output = process.StandardOutput.ReadToEndAsync();
                Task<string> errors = process.StandardError.ReadToEndAsync();
                await Task.Run(() => process.WaitForExit());
                status.Text = ((await output) + (await errors)).Trim();
                if (status.Text.Length == 0)
                    status.Text = "EduScan finished with exit code " + process.ExitCode + ".";
            }
        }
        catch (Exception error) { status.Text = error.Message; }
        finally { SetBusy(false); }
    }

    private void SetBusy(bool value)
    {
        busy = value;
        databaseMode.Enabled = !value;
        foreach (Button button in actions)
            button.Enabled = !value;
    }
}
