"""
SMW Trolls ROM Patcher Desktop Application
Applies BPS patches to Super Mario World ROMs and launches them
"""

import os
import sys
import json
import requests
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
from pathlib import Path
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import zipfile
import tempfile
import shutil

# Import our BPS patcher
try:
    from bps_patcher import apply_bps_patch as apply_bps
    HAS_BPS_LIB = True
except ImportError:
    HAS_BPS_LIB = False
    print("Warning: bps_patcher module not found.")


class PatchRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for receiving patch requests from website"""
    
    # Security: Maximum request size (10MB)
    MAX_REQUEST_SIZE = 10 * 1024 * 1024
    
    def do_POST(self):
        if self.path == '/patch':
            try:
                # Security: Limit request size
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length > self.MAX_REQUEST_SIZE:
                    self.send_response(413)  # Payload too large
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': 'Request too large'}).encode())
                    return
                
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                # Security: Validate required fields
                if 'patch_url' not in data:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': 'Missing patch_url'}).encode())
                    return
                
                patch_url = data.get('patch_url', '')
                # Security: Basic URL validation - must be http or https
                if not (patch_url.startswith('http://') or patch_url.startswith('https://')):
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': 'Invalid URL format'}).encode())
                    return
                
                # Security: Limit URL length
                if len(patch_url) > 2048:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': 'URL too long'}).encode())
                    return
                
                # Get the app instance from server
                app = self.server.app
                app.receive_patch_request(data)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS, GET')
                self.send_header('Access-Control-Allow-Headers', 'Content-Type')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True, 'message': 'Patch request received'}).encode())
            except json.JSONDecodeError:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Invalid JSON'}).encode())
            except ValueError as e:
                # Invalid content length
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Invalid request'}).encode())
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Internal server error'}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_OPTIONS(self):
        """Handle CORS preflight requests"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS, GET')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Max-Age', '3600')
        self.end_headers()
    
    def do_GET(self):
        """Handle GET requests (for testing/health checks)"""
        if self.path == '/health' or self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS, GET')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok', 'message': 'ROM Patcher server is running'}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Suppress default logging


class ROMPatcher:
    def __init__(self, root):
        try:
            self.root = root
            self.root.title("SMW Trolls ROM Patcher")
            self.root.geometry("500x350")
            
            # Set window icon if available
            try:
                icon_path = self.get_icon_path()
                if icon_path and os.path.exists(icon_path):
                    # Try to set icon (works with PNG on some systems, ICO preferred on Windows)
                    try:
                        self.root.iconbitmap(icon_path)
                    except:
                        # If iconbitmap fails (e.g., PNG on Windows), try iconphoto
                        try:
                            from PIL import Image, ImageTk
                            img = Image.open(icon_path)
                            photo = ImageTk.PhotoImage(img)
                            self.root.iconphoto(False, photo)
                        except:
                            # If PIL not available, try with tkinter's PhotoImage (PNG support varies)
                            try:
                                img = tk.PhotoImage(file=icon_path)
                                self.root.iconphoto(False, img)
                            except:
                                pass  # Icon setting failed, continue without it
            except Exception as e:
                print(f"Could not set window icon: {e}")
            
            # Configuration
            self.config_file = Path.home() / ".smwtrolls_patcher.json"
            self.config = self.load_config()
            
            # Base ROM path
            self.base_rom_path = self.config.get('base_rom_path', '')
            
            # Output directory
            self.output_dir = self.config.get('output_dir', str(Path.home() / 'Desktop' / 'PatchedROMs'))
            
            # Website URL
            self.website_url = self.config.get('website_url', 'https://smwtrolls.com')
            
            # Emulator path
            self.emulator_path = self.config.get('emulator_path', '')
            
            # Show README setting
            self.show_readme = self.config.get('show_readme', False)
            
            # Setup UI first (creates server_status_var)
            self.setup_ui()
            
            # Server shutdown flag
            self.shutting_down = False
            
            # Start local HTTP server for receiving patch requests (after UI is set up)
            self.start_local_server()
        except Exception as e:
            # Show error in GUI
            messagebox.showerror("Initialization Error", 
                               f"Failed to initialize ROM Patcher:\n{str(e)}\n\nCheck error.log for details.")
            # Log to file
            try:
                with open('error.log', 'w') as f:
                    import traceback
                    f.write(traceback.format_exc())
            except:
                pass
            raise
        
    def load_config(self):
        """Load configuration from file"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_config(self):
        """Save configuration to file"""
        self.config = {
            'base_rom_path': self.base_rom_path,
            'output_dir': self.output_dir,
            'website_url': self.website_url,
            'emulator_path': self.emulator_path,
            'flips_path': self.flips_path,
            'show_readme': self.show_readme
        }
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def setup_ui(self):
        """Setup the user interface"""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="8")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Base ROM selection
        ttk.Label(main_frame, text="Base ROM:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.rom_path_var = tk.StringVar(value=self.base_rom_path)
        ttk.Entry(main_frame, textvariable=self.rom_path_var, width=45).grid(row=0, column=1, padx=5, pady=3)
        ttk.Button(main_frame, text="Browse", command=self.select_base_rom).grid(row=0, column=2, pady=3)
        
        # Output directory
        ttk.Label(main_frame, text="Output Folder:").grid(row=1, column=0, sticky=tk.W, pady=3)
        self.output_dir_var = tk.StringVar(value=self.output_dir)
        ttk.Entry(main_frame, textvariable=self.output_dir_var, width=45).grid(row=1, column=1, padx=5, pady=3)
        ttk.Button(main_frame, text="Browse", command=self.select_output_dir).grid(row=1, column=2, pady=3)
        
        # Emulator path
        ttk.Label(main_frame, text="Emulator:").grid(row=2, column=0, sticky=tk.W, pady=3)
        self.emulator_var = tk.StringVar(value=self.emulator_path)
        ttk.Entry(main_frame, textvariable=self.emulator_var, width=45).grid(row=2, column=1, padx=5, pady=3)
        ttk.Button(main_frame, text="Browse", command=self.select_emulator).grid(row=2, column=2, pady=3)
        
        # Flips path (optional)
        self.flips_path = self.config.get('flips_path', '')
        ttk.Label(main_frame, text="Flips.exe (optional):").grid(row=3, column=0, sticky=tk.W, pady=3)
        self.flips_var = tk.StringVar(value=self.flips_path if self.flips_path else "Auto-detect")
        flips_entry = ttk.Entry(main_frame, textvariable=self.flips_var, width=45)
        flips_entry.grid(row=3, column=1, padx=5, pady=3)
        ttk.Button(main_frame, text="Browse", command=self.select_flips).grid(row=3, column=2, pady=3)
        
        # Show README setting
        self.show_readme_var = tk.BooleanVar(value=self.show_readme)
        ttk.Checkbutton(main_frame, text="Show README files from archives", 
                       variable=self.show_readme_var).grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=3)
        
        # Status
        ttk.Label(main_frame, text="Status:").grid(row=5, column=0, sticky=tk.W, pady=3)
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(main_frame, textvariable=self.status_var).grid(row=5, column=1, sticky=tk.W, padx=5, pady=3)
        
        # Progress bar
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=7, column=0, columnspan=3, pady=5)
        
        ttk.Button(button_frame, text="How to", command=self.show_help_window).pack(side=tk.LEFT, padx=3)
        ttk.Button(button_frame, text="Save Settings", command=self.save_settings).pack(side=tk.LEFT, padx=3)
        ttk.Button(button_frame, text="Apply Patch from URL", command=self.patch_from_url).pack(side=tk.LEFT, padx=3)
        ttk.Button(button_frame, text="Shutdown", command=self.shutdown_app).pack(side=tk.LEFT, padx=3)
        
        # Status indicator for server
        self.server_status_var = tk.StringVar(value="Server: Starting...")
        ttk.Label(main_frame, textvariable=self.server_status_var, foreground="green").grid(row=8, column=0, columnspan=3, pady=3)
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def start_local_server(self):
        """Start local HTTP server to receive patch requests"""
        def run_server():
            try:
                # Only bind to localhost (127.0.0.1) - not accessible from network
                server = HTTPServer(('127.0.0.1', 8765), PatchRequestHandler)
                server.app = self  # Store app reference
                self.server = server
                self.server_thread = threading.current_thread()
                self.server_status_var.set("Server: Running on http://localhost:8765")
                server.serve_forever()
            except Exception as e:
                if not self.shutting_down:
                    self.server_status_var.set(f"Server: Error - {str(e)}")
        
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
    
    def receive_patch_request(self, data):
        """Handle patch request from website"""
        patch_url = data.get('patch_url')
        level_title = data.get('level_title', 'level')
        
        if patch_url:
            # Schedule patch application on main thread
            self.root.after(0, lambda: self.apply_patch_from_url(patch_url, level_title))
    
    def shutdown_app(self):
        """Shutdown the application cleanly"""
        self.shutting_down = True
        if hasattr(self, 'server') and self.server:
            try:
                # Update status
                self.server_status_var.set("Server: Shutting down...")
                # Shutdown the server (this stops serve_forever())
                self.server.shutdown()
                # Close the server socket
                self.server.server_close()
            except Exception as e:
                print(f"Error shutting down server: {e}")
        
        # Destroy the window (this will exit the mainloop)
        self.root.quit()
        self.root.destroy()
    
    def on_closing(self):
        """Handle window closing (X button)"""
        self.shutdown_app()
    
    def select_base_rom(self):
        """Select base ROM file"""
        filename = filedialog.askopenfilename(
            title="Select Base ROM",
            filetypes=[("ROM files", "*.smc *.sfc"), ("All files", "*.*")]
        )
        if filename:
            self.rom_path_var.set(filename)
            self.base_rom_path = filename
    
    def select_output_dir(self):
        """Select output directory"""
        dirname = filedialog.askdirectory(title="Select Output Folder")
        if dirname:
            self.output_dir_var.set(dirname)
            self.output_dir = dirname
    
    def select_emulator(self):
        """Select emulator executable"""
        filename = filedialog.askopenfilename(
            title="Select Emulator",
            filetypes=[("Executable files", "*.exe"), ("All files", "*.*")]
        )
        if filename:
            self.emulator_var.set(filename)
            self.emulator_path = filename
    
    def select_flips(self):
        """Select flips.exe executable"""
        filename = filedialog.askopenfilename(
            title="Select Flips.exe",
            filetypes=[("Executable files", "*.exe"), ("All files", "*.*")]
        )
        if filename:
            self.flips_var.set(filename)
            self.flips_path = filename
    
    def save_settings(self):
        """Save current settings"""
        self.base_rom_path = self.rom_path_var.get()
        self.output_dir = self.output_dir_var.get()
        self.emulator_path = self.emulator_var.get()
        flips_path = self.flips_var.get()
        self.flips_path = flips_path if flips_path and flips_path != "Auto-detect" else ""
        self.show_readme = self.show_readme_var.get()
        self.save_config()
        messagebox.showinfo("Settings", "Settings saved successfully!")
    
    def patch_from_url(self):
        """Apply patch from URL (called by website)"""
        url = tk.simpledialog.askstring("Patch URL", "Enter patch URL:")
        if url:
            self.apply_patch_from_url(url)
    
    def apply_patch_from_url(self, patch_url, level_name="level"):
        """Download and apply patch from URL"""
        # Security: Validate URL before processing
        if not (patch_url.startswith('http://') or patch_url.startswith('https://')):
            messagebox.showerror("Error", "Invalid URL format. Only http:// and https:// URLs are allowed.")
            return
        
        if not self.base_rom_path or not os.path.exists(self.base_rom_path):
            messagebox.showerror("Error", "Please select a valid base ROM file first!")
            return
        
        if not self.output_dir:
            messagebox.showerror("Error", "Please select an output directory first!")
            return
        
        # Security: Sanitize level name to prevent path traversal
        level_name = "".join(c for c in level_name if c.isalnum() or c in (' ', '-', '_', '.'))[:100]
        if not level_name:
            level_name = "level"
        
        self.status_var.set("Downloading patch...")
        self.progress.start()
        
        def do_patch():
            try:
                # Security: Download with size limit (50MB max)
                MAX_DOWNLOAD_SIZE = 50 * 1024 * 1024
                self.status_var.set("Downloading patch...")
                response = requests.get(patch_url, timeout=60, stream=True, allow_redirects=True)
                response.raise_for_status()
                
                # Security: Check content length
                content_length = response.headers.get('content-length')
                if content_length and int(content_length) > MAX_DOWNLOAD_SIZE:
                    raise Exception(f"File too large (max {MAX_DOWNLOAD_SIZE // (1024*1024)}MB)")
                
                # Get content type and filename
                content_type = response.headers.get('content-type', '').lower()
                content_disposition = response.headers.get('content-disposition', '')
                
                # Determine if it's an archive
                is_archive = False
                archive_ext = None
                
                # Check content type and URL extension
                if 'zip' in content_type or patch_url.lower().endswith('.zip'):
                    is_archive = True
                    archive_ext = '.zip'
                elif '7z' in content_type or 'x-7z' in content_type or patch_url.lower().endswith('.7z'):
                    is_archive = True
                    archive_ext = '.7z'
                elif patch_url.lower().endswith(('.rar', '.tar', '.gz', '.bz2')):
                    is_archive = True
                    archive_ext = os.path.splitext(patch_url.lower())[1]
                
                # Download to temporary file with size limit
                downloaded_size = 0
                with tempfile.NamedTemporaryFile(delete=False, suffix=archive_ext or '.tmp') as temp_file:
                    for chunk in response.iter_content(chunk_size=8192):
                        downloaded_size += len(chunk)
                        if downloaded_size > MAX_DOWNLOAD_SIZE:
                            os.unlink(temp_file.name)
                            raise Exception(f"Download exceeded size limit (max {MAX_DOWNLOAD_SIZE // (1024*1024)}MB)")
                        temp_file.write(chunk)
                    temp_path = temp_file.name
                
                # Extract BPS file if it's an archive
                if is_archive:
                    self.status_var.set("Extracting archive...")
                    bps_files_list, readme_content = self.extract_bps_from_archive(temp_path, archive_ext)
                    # Show README if enabled and found (check checkbox value directly)
                    if readme_content and (self.show_readme_var.get() if hasattr(self, 'show_readme_var') else self.show_readme):
                        # Use default parameter to capture readme_content value in lambda closure
                        self.root.after(0, lambda content=readme_content: self.show_readme_window(content))
                    os.unlink(temp_path)  # Clean up temp file
                else:
                    # Read as BPS file directly
                    with open(temp_path, 'rb') as f:
                        patch_data = f.read()
                    # Convert single BPS file to list format for consistency
                    bps_files_list = [(patch_data, "patch.bps")]
                    readme_content = None
                    os.unlink(temp_path)  # Clean up temp file
                
                # Read base ROM
                with open(self.base_rom_path, 'rb') as f:
                    rom_data = f.read()
                
                # Apply patches (handle multiple BPS files)
                if len(bps_files_list) == 1:
                    # Single patch - apply and save as before
                    patch_data, patch_filename = bps_files_list[0]
                    self.status_var.set("Applying patch...")
                    try:
                        patched_rom = self.apply_bps_patch(rom_data, patch_data)
                    except Exception as patch_error:
                        error_msg = str(patch_error)
                        if "timeout" in error_msg.lower() or "exceeded" in error_msg.lower():
                            raise Exception(f"Patch application timed out or failed. The patch file may be corrupted or incompatible.\n\nError: {error_msg}\n\nTip: Try downloading the patch file manually and use 'Apply Patch from URL' button.")
                        else:
                            raise Exception(f"Failed to apply patch: {error_msg}\n\nTip: If you have flips.exe, place it in the same folder as this application for more reliable patching.")
                    
                    if patched_rom is None:
                        raise Exception("Failed to apply patch - no output generated")
                
                # Save patched ROM
                # Security: Ensure output directory is absolute and within safe bounds
                output_dir = os.path.abspath(self.output_dir)
                os.makedirs(output_dir, exist_ok=True)
                
                # Security: Sanitize filename to prevent path traversal
                safe_filename = "".join(c for c in level_name if c.isalnum() or c in (' ', '-', '_', '.'))[:100]
                if not safe_filename:
                    safe_filename = "patched_rom"
                output_filename = f"{safe_filename}.smc"
                output_path = os.path.join(output_dir, output_filename)
                
                # Security: Ensure output path is within the output directory (prevent path traversal)
                output_path = os.path.abspath(output_path)
                if not output_path.startswith(os.path.abspath(output_dir)):
                    raise Exception("Invalid output path")
                
                with open(output_path, 'wb') as f:
                    f.write(patched_rom)
                
                self.status_var.set(f"Patch applied! Saved to {output_path}")
                
                # Launch ROM if emulator is set
                if self.emulator_path and os.path.exists(self.emulator_path):
                    self.launch_rom(output_path)
                
                messagebox.showinfo("Success", f"Patch applied successfully!\nSaved to: {output_path}")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to apply patch: {str(e)}")
                self.status_var.set("Error: " + str(e))
            finally:
                self.progress.stop()
                self.status_var.set("Ready")
        
        threading.Thread(target=do_patch, daemon=True).start()
    
    def apply_bps_patch(self, rom_data, patch_data):
        """Apply BPS patch to ROM data - tries flips.exe first, then Python implementation"""
        # Try flips.exe first (most reliable)
        try:
            flips_result = self._try_flips_patch(rom_data, patch_data)
            if flips_result:
                return flips_result
        except Exception as flips_error:
            # If flips failed with an error, show it to the user instead of silently falling back
            raise Exception(f"flips.exe failed: {str(flips_error)}")
        
        # Fall back to Python implementation
        global apply_bps, HAS_BPS_LIB
        
        if not HAS_BPS_LIB:
            try:
                import importlib.util
                # Try multiple paths for PyInstaller compatibility
                possible_paths = [
                    os.path.join(os.path.dirname(__file__), 'bps_patcher.py'),
                    'bps_patcher.py',
                    os.path.join(sys._MEIPASS if hasattr(sys, '_MEIPASS') else '.', 'bps_patcher.py')
                ]
                
                for bps_path in possible_paths:
                    if os.path.exists(bps_path):
                        spec = importlib.util.spec_from_file_location("bps_patcher", bps_path)
                        if spec and spec.loader:
                            bps_module = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(bps_module)
                            apply_bps = bps_module.apply_bps_patch
                            HAS_BPS_LIB = True
                            break
            except Exception as e:
                pass
        
        if not HAS_BPS_LIB:
            raise Exception("BPS patching module not available. Please install flips.exe or ensure bps_patcher.py is included.")
        
        try:
            # Convert to bytes if needed
            if isinstance(rom_data, bytearray):
                rom_bytes = bytes(rom_data)
            else:
                rom_bytes = rom_data
            
            return apply_bps(rom_bytes, patch_data)
        except Exception as e:
            print(f"BPS patching error: {e}")
            import traceback
            traceback.print_exc()
            raise Exception(f"Failed to apply BPS patch: {str(e)}")
    
    def _try_flips_patch(self, rom_data, patch_data):
        """Try to use flips.exe to apply patch (most reliable method)"""
        import tempfile
        import subprocess
        
        # Check if user specified a custom flips path in settings
        if hasattr(self, 'flips_path') and self.flips_path and os.path.exists(self.flips_path):
            flips = self.flips_path
        else:
            # Auto-detect flips
            # Get the directory where the exe/script is located
            if getattr(sys, 'frozen', False):
                # Running as compiled executable
                exe_dir = os.path.dirname(sys.executable)
            else:
                # Running as script
                exe_dir = os.path.dirname(os.path.abspath(__file__))
            
            flips_paths = [
                'flips.exe',  # Current working directory
                os.path.join(exe_dir, 'flips.exe'),  # Same directory as exe/script
                os.path.join(os.path.dirname(__file__), 'flips.exe') if '__file__' in globals() else None,
                'C:\\Program Files\\flips\\flips.exe',
            ]
            
            # Filter out None values
            flips_paths = [p for p in flips_paths if p]
            
            flips = None
            for path in flips_paths:
                if path and os.path.exists(path):
                    flips = path
                    break
        
        if not flips:
            # Try to find it in PATH
            try:
                result = subprocess.run(['where', 'flips'], capture_output=True, text=True, timeout=2)
                if result.returncode == 0 and result.stdout.strip():
                    flips = result.stdout.strip().split('\n')[0]
            except:
                pass
        
        if not flips:
            return None  # flips not available, use Python implementation
        
        # Initialize paths to None
        source_path = None
        patch_path = None
        output_path = None
        
        try:
            # Create temp files
            with tempfile.NamedTemporaryFile(delete=False, suffix='.smc') as source_file:
                source_file.write(rom_data)
                source_path = source_file.name
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.bps') as patch_file:
                patch_file.write(patch_data)
                patch_path = patch_file.name
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.smc') as output_file:
                output_path = output_file.name
            
            # Apply patch using flips
            # flips command: flips -a patch.bps rom.smc output.smc (or flips --apply)
            # Try both command formats for compatibility
            # Don't use check=True - we'll check return code and output file existence
            result = None
            flips_error = None
            try:
                cmd = [flips, '-a', patch_path, source_path, output_path]
                result = subprocess.run(
                    cmd,
                    check=False,  # Don't raise on error, check return code manually
                    capture_output=True,
                    timeout=30,
                    text=True
                )
            except FileNotFoundError:
                flips_error = f"flips.exe not found at: {flips}"
            except subprocess.TimeoutExpired:
                flips_error = "flips.exe timed out"
            except Exception as e:
                flips_error = f"Error running flips.exe: {str(e)}"
            
            # If first format failed, try alternative
            if result is None or (result.returncode != 0 and not os.path.exists(output_path)):
                try:
                    cmd = [flips, '--apply', patch_path, source_path, output_path]
                    result = subprocess.run(
                        cmd,
                        check=False,  # Don't raise on error, check return code manually
                        capture_output=True,
                        timeout=30,
                        text=True
                    )
                except Exception as e:
                    if not flips_error:
                        flips_error = f"Error running flips.exe: {str(e)}"
            
            # Check if output file was created (flips might return non-zero but still succeed)
            if not os.path.exists(output_path):
                # flips failed - construct error message
                error_msg = flips_error or "flips.exe failed"
                if result:
                    error_msg += f" (return code: {result.returncode})"
                    if result.stderr:
                        error_msg += f"\nflips.exe stderr: {result.stderr}"
                    if result.stdout:
                        error_msg += f"\nflips.exe stdout: {result.stdout}"
                raise Exception(error_msg)
            
            # Read result
            with open(output_path, 'rb') as f:
                patched_data = f.read()
            
            # Cleanup
            for path in [source_path, patch_path, output_path]:
                try:
                    if path and os.path.exists(path):
                        os.unlink(path)
                except:
                    pass
            
            return patched_data
        except subprocess.TimeoutExpired:
            # Cleanup on timeout
            for path in [source_path, patch_path, output_path]:
                try:
                    if path and os.path.exists(path):
                        os.unlink(path)
                except:
                    pass
            return None
        except Exception as e:
            # If this is our flips error, re-raise it so caller can see it
            error_msg = str(e)
            if "flips.exe" in error_msg or "flips" in error_msg.lower():
                # Cleanup before re-raising
                for path in [source_path, patch_path, output_path]:
                    try:
                        if path and os.path.exists(path):
                            os.unlink(path)
                    except:
                        pass
                # Re-raise so caller sees the flips error
                raise
            # Other errors - cleanup and return None to fall back to Python
            for path in [source_path, patch_path, output_path]:
                try:
                    if path and os.path.exists(path):
                        os.unlink(path)
                except:
                    pass
            return None  # Fall back to Python implementation
    
    def extract_bps_from_archive(self, archive_path, archive_ext):
        """Extract BPS files from compressed archive. Returns (bps_files_list, readme_content).
        bps_files_list is a list of tuples: [(bps_data, filename), ...]"""
        temp_dir = tempfile.mkdtemp()
        readme_content = None
        try:
            if archive_ext == '.zip':
                # Handle ZIP files
                with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                    
                    bps_files = []
                    # Find all BPS files and README in extracted contents
                    for root, dirs, files in os.walk(temp_dir):
                        for file in files:
                            file_lower = file.lower()
                            file_path = os.path.join(root, file)
                            
                            # Look for BPS files (collect all of them)
                            if file_lower.endswith('.bps'):
                                with open(file_path, 'rb') as f:
                                    bps_data = f.read()
                                    bps_files.append((bps_data, file))  # Store data and filename
                            
                            # Look for README files (if not already found)
                            if readme_content is None:
                                readme_names = ['readme.txt', 'readme.md', 'readme', 'readme.txt.txt']
                                if file_lower in readme_names or (file_lower.startswith('readme') and file_lower.endswith(('.txt', '.md', '.text'))):
                                    try:
                                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                            readme_content = f.read()
                                    except:
                                        try:
                                            with open(file_path, 'r', encoding='latin-1', errors='ignore') as f:
                                                readme_content = f.read()
                                        except:
                                            pass
                    
                    if not bps_files:
                        raise Exception("No BPS file found in ZIP archive")
                    return (bps_files, readme_content)
                    
            elif archive_ext == '.7z':
                # Handle 7Z files - try using py7zr or 7z.exe
                py7zr_failed = False
                try:
                    import py7zr
                    with py7zr.SevenZipFile(archive_path, mode='r') as archive:
                        archive.extractall(temp_dir)
                    
                    bps_files = []
                    # Find all BPS files and README in extracted contents
                    for root, dirs, files in os.walk(temp_dir):
                        for file in files:
                            file_lower = file.lower()
                            file_path = os.path.join(root, file)
                            
                            # Look for BPS files (collect all of them)
                            if file_lower.endswith('.bps'):
                                with open(file_path, 'rb') as f:
                                    bps_data = f.read()
                                bps_files.append((bps_data, file))  # Store data and filename
                            
                            # Look for README files (if not already found)
                            if readme_content is None:
                                readme_names = ['readme.txt', 'readme.md', 'readme', 'readme.txt.txt']
                                if file_lower in readme_names or (file_lower.startswith('readme') and file_lower.endswith(('.txt', '.md', '.text'))):
                                    try:
                                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                            readme_content = f.read()
                                    except:
                                        try:
                                            with open(file_path, 'r', encoding='latin-1', errors='ignore') as f:
                                                readme_content = f.read()
                                        except:
                                            pass
                    
                    if not bps_files:
                        raise Exception("No BPS file found in 7Z archive")
                    return (bps_files, readme_content)
                except ImportError:
                    py7zr_failed = True
                except Exception as e:
                    # py7zr is installed but failed for some reason, try 7z.exe as fallback
                    py7zr_failed = True
                    py7zr_error = str(e)
                
                if py7zr_failed:
                    # Try using 7z.exe if available
                    # Get the directory where the exe/script is located
                    if getattr(sys, 'frozen', False):
                        # Running as compiled executable
                        exe_dir = os.path.dirname(sys.executable)
                    else:
                        # Running as script
                        exe_dir = os.path.dirname(os.path.abspath(__file__))
                    
                    possible_7z_paths = [
                        os.path.join(exe_dir, '7z.exe'),  # Same directory as exe/script (highest priority)
                        '7z.exe',  # Current working directory or PATH
                        'C:\\Program Files\\7-Zip\\7z.exe',
                        'C:\\Program Files (x86)\\7-Zip\\7z.exe',
                    ]
                    
                    for seven_z_path in possible_7z_paths:
                        if os.path.exists(seven_z_path) or seven_z_path == '7z.exe':
                            try:
                                result = subprocess.run(
                                    [seven_z_path, 'x', archive_path, f'-o{temp_dir}', '-y'],
                                    capture_output=True,
                                    timeout=30,
                                    text=True
                                )
                                if result.returncode == 0:
                                    # Find all BPS files and README
                                    bps_files = []
                                    for root, dirs, files in os.walk(temp_dir):
                                        for file in files:
                                            file_lower = file.lower()
                                            file_path = os.path.join(root, file)
                                            
                                            # Look for BPS files (collect all of them)
                                            if file_lower.endswith('.bps'):
                                                with open(file_path, 'rb') as f:
                                                    bps_data = f.read()
                                                bps_files.append((bps_data, file))  # Store data and filename
                                            
                                            # Look for README files (if not already found)
                                            if readme_content is None:
                                                readme_names = ['readme.txt', 'readme.md', 'readme', 'readme.txt.txt']
                                                if file_lower in readme_names or (file_lower.startswith('readme') and file_lower.endswith(('.txt', '.md', '.text'))):
                                                    try:
                                                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                                            readme_content = f.read()
                                                    except:
                                                        try:
                                                            with open(file_path, 'r', encoding='latin-1', errors='ignore') as f:
                                                                readme_content = f.read()
                                                        except:
                                                            pass
                                    if not bps_files:
                                        raise Exception("No BPS file found in 7Z archive")
                                    return (bps_files, readme_content)
                            except Exception:
                                continue
                    
                    raise Exception("7Z extraction failed. Please install py7zr (pip install py7zr) or 7-Zip")
            else:
                raise Exception(f"Unsupported archive format: {archive_ext}")
        finally:
            # Clean up temp directory
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
    
    def launch_rom(self, rom_path):
        """Launch ROM with emulator"""
        try:
            # Security: Validate paths before executing
            if not os.path.exists(self.emulator_path):
                raise Exception("Emulator path does not exist")
            if not os.path.exists(rom_path):
                raise Exception("ROM file does not exist")
            
            # Security: Use absolute paths and validate they're files (not directories)
            emulator_abs = os.path.abspath(self.emulator_path)
            rom_abs = os.path.abspath(rom_path)
            
            if not os.path.isfile(emulator_abs):
                raise Exception("Emulator path is not a file")
            if not os.path.isfile(rom_abs):
                raise Exception("ROM path is not a file")
            
            # Security: Only allow .exe files as emulator
            if not emulator_abs.lower().endswith('.exe'):
                raise Exception("Emulator must be an .exe file")
            
            # Launch with absolute paths
            subprocess.Popen([emulator_abs, rom_abs])
            self.status_var.set(f"Launched: {rom_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch emulator: {str(e)}")
    
    def open_folder(self, folder_path):
        """Open a folder in Windows Explorer"""
        try:
            folder_abs = os.path.abspath(folder_path)
            if not os.path.exists(folder_abs):
                raise Exception("Folder does not exist")
            if not os.path.isdir(folder_abs):
                raise Exception("Path is not a directory")
            
            # Use Windows explorer command
            if sys.platform == 'win32':
                os.startfile(folder_abs)
            else:
                # For other platforms, try common commands
                try:
                    subprocess.Popen(['xdg-open', folder_abs])  # Linux
                except:
                    try:
                        subprocess.Popen(['open', folder_abs])  # macOS
                    except:
                        raise Exception("Platform not supported for opening folders")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open folder: {str(e)}")
    
    def show_help_window(self):
        """Display help/instructions window"""
        help_window = tk.Toplevel(self.root)
        help_window.title("How to Use - SMW Trolls ROM Patcher")
        help_window.geometry("600x550")
        
        # Create frame with scrollbar
        frame = ttk.Frame(help_window, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Text widget with scrollbar
        text_frame = ttk.Frame(frame)
        text_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        text_widget = tk.Text(text_frame, wrap=tk.WORD, yscrollcommand=scrollbar.set, 
                             font=('Segoe UI', 10), padx=15, pady=15)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=text_widget.yview)
        
        # Help content
        help_text = """HOW TO USE SMW TROLLS ROM PATCHER

OVERVIEW
This application applies BPS patch files to Super Mario World ROM files. You can receive patch requests directly from the SMW Trolls website, or manually apply patches from URLs.


SETTINGS EXPLANATION

• Base ROM:
  This is your original, unmodified Super Mario World ROM file (.smc or .sfc format).
  The application uses this as the source file to apply patches to. You need a clean,
  unmodified ROM file for patches to work correctly.

• Output Folder:
  This is where the patched ROM files will be saved. After applying a patch, the new
  patched ROM will be saved to this location. If multiple patches are found in an
  archive, they will be saved to a subfolder here.

• Emulator:
  (Optional) The path to your SNES emulator executable (.exe file). If set, the application
  will automatically launch the patched ROM in your emulator after successful patching.

• Flips.exe (optional):
  (Optional) Path to the flips.exe BPS patcher tool. If provided, the application will use
  flips.exe for more reliable patch application. If not set, the application will use its
  built-in Python patcher. Using flips.exe is recommended for better compatibility.

• Show README files from archives:
  When enabled, if a compressed archive (ZIP/7Z) contains a README file, it will be
  automatically displayed in a separate window after extraction. This is useful for
  reading level descriptions or instructions.


HOW IT WORKS

1. Configure your settings:
   - Select your Base ROM file
   - Choose an Output Folder for patched ROMs
   - (Optional) Set your Emulator and Flips.exe paths
   - Click "Save Settings" to save your preferences

2. Applying patches:
   - Patches can be applied automatically when you click "Play Now" on the SMW Trolls
     website (the application must be running)
   - You can also manually apply patches using the "Apply Patch from URL" button

3. Multiple patches:
   - If an archive contains multiple BPS files, all patches will be applied
   - Each patched ROM will be saved to a folder (named after the level)
   - The folder will open automatically instead of launching the ROM

4. Server:
   - The application runs a local web server on http://localhost:8765
   - This allows the website to send patch requests directly to the application
   - The server only accepts connections from localhost (secure)


TIPS

• Make sure your Base ROM is a clean, unmodified Super Mario World ROM
• Using flips.exe provides better compatibility and reliability
• The application remembers your settings between sessions
• If a patch fails, try using flips.exe for better results
• README files from archives can provide important level information"""
        
        # Insert help content
        text_widget.insert('1.0', help_text)
        text_widget.config(state=tk.DISABLED)  # Make it read-only
        
        # Close button
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(button_frame, text="Close", command=help_window.destroy).pack()
    
    def show_readme_window(self, readme_content):
        """Display README content in a scrollable window"""
        # Create a new top-level window
        readme_window = tk.Toplevel(self.root)
        readme_window.title("README")
        readme_window.geometry("600x500")
        
        # Create frame with scrollbar
        frame = ttk.Frame(readme_window, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Text widget with scrollbar
        text_frame = ttk.Frame(frame)
        text_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        text_widget = tk.Text(text_frame, wrap=tk.WORD, yscrollcommand=scrollbar.set, 
                             font=('Consolas', 10), padx=10, pady=10)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=text_widget.yview)
        
        # Insert README content
        text_widget.insert('1.0', readme_content)
        text_widget.config(state=tk.DISABLED)  # Make it read-only
        
        # Close button
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(button_frame, text="Close", command=readme_window.destroy).pack()
    
    def get_icon_path(self):
        """Get path to icon file (prefers dragoncoin.png, falls back to dragoncoin.ico)"""
        # Try multiple possible locations, prefer PNG format (better quality)
        icon_extensions = ['.png', '.ico']  # Try PNG first
        base_paths = [
            # PyInstaller bundled location (in _MEIPASS or same dir as exe)
            get_resource_path(''),
            # Current working directory
            os.getcwd(),
            # Relative to script location
            os.path.dirname(os.path.abspath(__file__)),
            # If running as exe, check exe directory
            os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else None,
            # Relative to parent directory (static/images)
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'images'),
            # Absolute path from project root
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'static', 'images'),
        ]
        
        # Filter out None values
        base_paths = [p for p in base_paths if p is not None]
        
        # Try each extension in order, then each base path
        for ext in icon_extensions:
            for base_path in base_paths:
                path = os.path.join(base_path, f'dragoncoin{ext}')
                if os.path.exists(path):
                    return path
        return None


def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
    
    return os.path.join(base_path, relative_path)


def main():
    try:
        root = tk.Tk()
        app = ROMPatcher(root)
        root.mainloop()
    except Exception as e:
        # Show error in a message box if GUI fails
        try:
            import tkinter.messagebox as mb
            mb.showerror("Error", f"Failed to start ROM Patcher:\n{str(e)}\n\nCheck error.log for details.")
        except:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
        
        # Also log to file
        try:
            with open('error.log', 'w') as f:
                import traceback
                f.write(traceback.format_exc())
        except:
            pass
        
        input("Press Enter to exit...")  # Keep window open if running from command prompt


if __name__ == "__main__":
    main()

