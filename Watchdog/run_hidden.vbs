' Starts run_watchdog.ps1 with no window (used by Task Scheduler "F2 Watchdog")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
CreateObject("WScript.Shell").Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & here & "\run_watchdog.ps1""", 0, False
