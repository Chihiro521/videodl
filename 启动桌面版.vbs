Option Explicit
Dim shell, fso, root, pythonw
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = fso.BuildPath(root, ".venv\Scripts\pythonw.exe")
If Not fso.FileExists(pythonw) Then
    MsgBox "Please install desktop dependencies first. See desktop/README.md.", 48, "VideoDL Desktop"
    WScript.Quit 1
End If
shell.CurrentDirectory = root
shell.Run Chr(34) & pythonw & Chr(34) & " -m desktop", 1, False
