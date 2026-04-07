# scrcpy-tray

A Python-based system tray application for managing multiple Android devices using `scrcpy` and `adb`.

## Features
- **Device Management**: Automatically detects connected Android devices.
- **App Launching**: Fetch and launch third-party apps directly from the tray.
- **Navigation Shortcuts**: Floating taskbar-style buttons for Back, Home, and Recents for each device.
- **Favorites**: Save your most-used apps for quick access across devices.
- **Automation**: Automatic screen wake, rotation locking, and navigation mode switching upon connection.

## Installation / Compilation

### Prerequisites
1. **Python 3.x**
2. **Pip Packages**: `pip install pystray Pillow`
3. **Android Platform Tools & Scrcpy**: 
   Since this repository only contains the source code, you must manually add the required binaries:
   - Download **Platform Tools (ADB)** from [Google](https://developer.android.com/tools/releases/platform-tools).
   - Download **Scrcpy** from [Genymobile/scrcpy](https://github.com/Genymobile/scrcpy).
   - Place all `.exe`, `.dll`, and `scrcpy-server` files into the root directory of this project.

### Building the Executable
- Ensure **PyInstaller** is installed: `pip install pyinstaller`.
- Run the provided `build_exe.bat` to generate a standalone folder in `dist/`.

### Creating the Installer
- Install [Inno Setup](https://jrsoftware.org/isdl.php).
- Compile the `installer.iss` script to generate a setup file.

## License
MIT
