' Launch the FrenchDaily daily build with no visible window.
' The scheduled task calls this instead of cmd.exe, so nothing ever flashes on
' the desktop while it runs.
Dim fso, root, bat, sh
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
bat = root & "\scripts\daily.bat"
Set sh = CreateObject("WScript.Shell")
sh.Run  & bat & , 0, False
