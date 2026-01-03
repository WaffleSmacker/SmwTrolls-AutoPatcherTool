"""
Build script for ROM Patcher with proper Tkinter/Tcl/Tk bundling
Based on the working sample build script
"""

import PyInstaller.__main__
import os
import sys
import platform
import subprocess

script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)
separator = ';' if platform.system() == 'Windows' else ':'

# Find icon file (dragoncoin.ico for executable, PNG for window icon)
# Note: PyInstaller requires ICO for Windows executable icons
icon_path = None
possible_icon_paths = [
    os.path.join(script_dir, 'dragoncoin.ico'),  # Prefer ICO for executable icon
    os.path.join(script_dir, '..', 'static', 'images', 'dragoncoin.ico'),
    os.path.join(script_dir, 'static', 'images', 'dragoncoin.ico'),
    # Fallback to PNG (PyInstaller may convert it, but ICO is recommended)
    os.path.join(script_dir, 'dragoncoin.png'),
    os.path.join(script_dir, '..', 'static', 'images', 'dragoncoin.png'),
    os.path.join(script_dir, 'static', 'images', 'dragoncoin.png'),
]
for path in possible_icon_paths:
    if os.path.exists(path):
        icon_path = os.path.abspath(path)
        print(f"Found icon: {icon_path}")
        break

print("Building SMW Trolls ROM Patcher with Tkinter support...")
print()

# Check Tkinter availability
print("Checking Tkinter availability...")
try:
    result = subprocess.run(
        [sys.executable, '-c', 'import tkinter, sys; print("Tkinter OK; Tk version:", tkinter.TkVersion)'],
        capture_output=True,
        text=True
    )
    print(result.stdout.strip())
except:
    print("Warning: Could not verify Tkinter")

# Get Python base directory
python_base = sys.base_prefix
print(f"Python base: {python_base}")
print()

# Find Tcl/Tk DLLs
print("Locating Tcl/Tk DLLs...")
dll_dirs = []
for dll_dir in [
    os.path.join(python_base, "DLLs"),
    os.path.join(python_base, "Library", "bin"),  # Conda
]:
    if os.path.exists(dll_dir):
        dll_dirs.append(dll_dir)
        print(f"  Found DLL directory: {dll_dir}")

# Common DLL names (version numbers may vary)
dll_names = ["tcl86t.dll", "tk86t.dll", "tcl86.dll", "tk86.dll",
             "tcl87t.dll", "tk87t.dll", "tcl87.dll", "tk87.dll",
             "tcl88t.dll", "tk88t.dll", "tcl88.dll", "tk88.dll"]

dll_args = []
for dll_dir in dll_dirs:
    for name in dll_names:
        dll_path = os.path.join(dll_dir, name)
        if os.path.exists(dll_path):
            dll_args.extend(["--add-binary", f"{dll_path}{separator}."])
            print(f"  Found DLL: {name}")

# Find Tcl/Tk data directories
print()
print("Locating Tcl/Tk data directories...")
tcl_roots = []
for tcl_root in [
    os.path.join(python_base, "tcl"),
    os.path.join(python_base, "Library", "lib"),  # Conda
]:
    if os.path.exists(tcl_root):
        tcl_roots.append(tcl_root)
        print(f"  Found Tcl root: {tcl_root}")

# Only include the FIRST tcl and tk directory found (like the sample does)
# This prevents bundling multiple versions and reduces size significantly
data_args = []
tcl_dir = None
tk_dir = None
tcl_tk_size = 0

for root in tcl_roots:
    if os.path.exists(root):
        # Find first tcl* directory
        if not tcl_dir:
            for item in os.listdir(root):
                item_path = os.path.join(root, item)
                if os.path.isdir(item_path) and item.startswith("tcl") and item[3:].replace(".", "").isdigit():
                    tcl_dir = item_path
                    # Calculate size for reporting
                    try:
                        for dirpath, dirnames, filenames in os.walk(item_path):
                            for filename in filenames:
                                tcl_tk_size += os.path.getsize(os.path.join(dirpath, filename))
                    except:
                        pass
                    data_args.extend(["--add-data", f"{item_path}{separator}tcl"])
                    print(f"  Found Tcl data: {item}")
                    break
        
        # Find first tk* directory
        if not tk_dir:
            for item in os.listdir(root):
                item_path = os.path.join(root, item)
                if os.path.isdir(item_path) and item.startswith("tk") and item[2:].replace(".", "").isdigit():
                    tk_dir = item_path
                    # Calculate size for reporting
                    try:
                        for dirpath, dirnames, filenames in os.walk(item_path):
                            for filename in filenames:
                                tcl_tk_size += os.path.getsize(os.path.join(dirpath, filename))
                    except:
                        pass
                    data_args.extend(["--add-data", f"{item_path}{separator}tk"])
                    print(f"  Found Tk data: {item}")
                    break

if tcl_tk_size > 0:
    print(f"  Tcl/Tk data size: {tcl_tk_size / (1024*1024):.1f} MB")
    print("  Note: Only including first Tcl/Tk version found (like sample build)")

print()

# Build arguments
# Note: --onefile creates a single exe but is larger (~250MB)
#       --onedir creates a folder with exe + DLLs, smaller total size (~150MB) but multiple files
#       For smallest size, use --onedir + UPX compression
build_args = [
    'rom_patcher.py',
    '--name=SMWTrollsROMPatcher',
    '--onefile',  # Change to '--onedir' for smaller size (but creates a folder instead of single exe)
    '--windowed',
    f'--add-data=bps_patcher.py{separator}.',
    # Tkinter support - use collect-all like the sample (more efficient)
    '--collect-all=tkinter',
    '--hidden-import=_tkinter',
    # Other imports
    '--hidden-import=http.server',
    '--hidden-import=threading',
    '--hidden-import=json',
    '--hidden-import=requests',
    '--hidden-import=subprocess',
    '--hidden-import=zipfile',
    '--hidden-import=tempfile',
    '--hidden-import=shutil',
    # Note: py7zr is NOT included as hidden-import - it's imported dynamically only when needed
    # This saves ~50-100MB since py7zr and its compression libs are huge
    
    # Exclude ONLY safe modules that won't break runtime
    # Don't exclude: email, urllib, http, html, xml - they're needed by stdlib modules we use
    # Note: distutils removed from excludes - it's removed in Python 3.12+ and causes import conflicts
    '--exclude-module=pkg_resources',
    '--exclude-module=setuptools',
    # Test modules (safe to exclude)
    '--exclude-module=pydoc',
    '--exclude-module=doctest',
    '--exclude-module=unittest',
    '--exclude-module=test',
    '--exclude-module=tests',
    '--exclude-module=tkinter.test',
    # Large optional dependencies we definitely don't use
    '--exclude-module=matplotlib',
    '--exclude-module=numpy',
    '--exclude-module=pandas',
    '--exclude-module=scipy',
    '--exclude-module=PIL',
    '--exclude-module=Pillow',
    '--exclude-module=cryptography',
    # Note: py7zr is included for 7Z support (adds ~50-100MB but enables 7Z extraction)
    # If you want to exclude it to reduce size, uncomment the next line and users will need 7-Zip installed
    # '--exclude-module=py7zr',
    # Note: --strip doesn't work on Windows (Unix-only tool)
    '--clean',
    '--noconfirm',
]

# Add icon if found
if icon_path:
    build_args.append(f'--icon={icon_path}')
    # Also include icon as data file so it can be loaded at runtime for window icon
    build_args.append(f'--add-data={icon_path}{separator}.')
    print(f"Using icon: {icon_path}")
else:
    print("Warning: Icon file (dragoncoin.png or dragoncoin.ico) not found. Building without icon.")

# Add DLL and data arguments
build_args.extend(dll_args)
build_args.extend(data_args)

# Optional: Use UPX compression for smaller exe (requires UPX to be installed)
# Uncomment the next line if you have UPX installed and want a smaller exe
# build_args.append('--upx-dir=upx')  # or path to UPX executable

print("Building executable...")
print("This may take a few minutes...")
print("Note: For even smaller size, install UPX and uncomment the UPX line in build script")
print()

PyInstaller.__main__.run(build_args)

print()
print("Build complete! Check the 'dist' folder for SMWTrollsROMPatcher.exe")

