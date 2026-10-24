Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
ScriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
BatPath = fso.BuildPath(ScriptDir, "run_server.bat")
WshShell.Run Chr(34) & BatPath & Chr(34), 0, False
Set WshShell = Nothing
