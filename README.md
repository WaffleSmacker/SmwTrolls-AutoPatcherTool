# SMW Trolls ROM Patcher

Desktop application for applying BPS patches to Super Mario World ROMs and launching them automatically.

## Features

- Apply BPS patches to ROM files
- Automatic ROM launching with configured emulator
- Receive patch requests directly from the SMW Trolls website
- Save patched ROMs to a specified folder

## Installation

1. Download or build the `SMWTrollsROMPatcher.exe` file
   - If building from source, see `BUILD_INSTRUCTIONS.md` for details
   - The executable is self-contained and includes all dependencies

2. No additional installation required - the exe file is ready to use!

## Usage

1. Double-click `SMWTrollsROMPatcher.exe` to launch the application

2. Configure settings:
   - Select your base Super Mario World ROM file
   - Choose an output folder for patched ROMs
   - (Optional) Select your emulator executable

3. Click "Save Settings" to save your configuration

4. The app will start a local server on `http://localhost:8765` to receive patch requests from the website

5. When you click "Play Now" on a level page (as wafflesmacker), the patch will be automatically downloaded, applied, and the ROM will launch!

## Requirements

- Windows (for the .exe file)
- A base Super Mario World ROM file (.smc or .sfc)
- (Optional) An emulator to launch patched ROMs

**Note:** If you need to build from source or run on Linux/Mac, you'll need Python 3.7+ and the dependencies listed in `requirements.txt`. See `BUILD_INSTRUCTIONS.md` for details.

## Configuration

Settings are saved to `~/.smwtrolls_patcher.json` and persist between sessions.

## Credits

This application uses **[Flips](https://github.com/Alcaro/Flips)** (Floating IPS) for reliable BPS patch application. Flips is an excellent patcher for IPS and BPS files developed by Alcaro. If you place `flips.exe` in the same folder as this application, it will be automatically used for more reliable patch application. Many thanks to the Flips project!

