@echo off
echo Building EXE with PyInstaller...
pyinstaller --noconsole --onedir --icon=icon.png --name=scrcpy-tray tray.pyw
echo Copying dependencies and assets...
xcopy /Y *.exe dist\scrcpy-tray\
xcopy /Y *.dll dist\scrcpy-tray\
xcopy /Y *.png dist\scrcpy-tray\
xcopy /Y scrcpy-server dist\scrcpy-tray\
echo Build complete.
pause
