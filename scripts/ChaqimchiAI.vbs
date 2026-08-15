Set WshShell = CreateObject("WScript.Shell")
strCurrentDir = WshShell.CurrentDirectory

' Fon rejimida run_windows.bat ni ishga tushirish (oynasiz / 0 = hidden)
WshShell.Run "cmd /c """ & strCurrentDir & "\scripts\run_windows.bat""", 0, False
