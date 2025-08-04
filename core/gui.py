"""
Modern GUI Revamp for Rulescrape

A complete redesign using customtkinter with modern UI/UX improvements.
This GUI integrates with the existing rulescrape.py system, using its
settings, download functions, and configuration files.

Installation: pip install customtkinter pillow requests tqdm

Features:
- Modern, responsive interface
- Real-time download progress
- Image gallery with previews
- Download history tracking
- Advanced search options
- Theme switching
- Integration with existing rulescrape settings
"""

import os
import json
import logging
import multiprocessing
import configparser
from pathlib import Path
from datetime import datetime
import webbrowser
import sys
import time
import threading
import queue
import concurrent.futures
from typing import List, Dict, Optional, Tuple, TYPE_CHECKING

# For type hints
if TYPE_CHECKING:
    from PIL import Image

# Error queue for CLI integration
error_queue = queue.Queue()
_error_queue_stopping = False

def poll_error_queue(root):
    """Poll for error messages from CLI operations"""
    global _error_queue_stopping
    
    # Check if stopping or root still exists and is valid
    if _error_queue_stopping:
        return
        
    try:
        if not root.winfo_exists():
            return
    except:
        return
    
    try:
        while True:
            try:
                msg = error_queue.get_nowait()
                # For modern GUI, we'll just print to console for now
                print(f"CLI Error: {msg}")
            except queue.Empty:
                break
    except Exception as e:
        print(f"Error polling error queue: {e}")
    
    # Only schedule next poll if not stopping and root still exists
    if not _error_queue_stopping:
        try:
            if root and root.winfo_exists():
                root.after(500, lambda: poll_error_queue(root))
        except:
            pass  # Widget destroyed, stop polling

# Try to import GUI dependencies
try:
    import customtkinter as ctk
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    from PIL import Image, ImageTk
    import requests
    GUI_DEPENDENCIES_AVAILABLE = True
except ImportError as e:
    print(f"GUI dependencies not available: {e}")
    print("To install required GUI dependencies, run:")
    print("pip install customtkinter pillow requests tqdm")
    print("\nAlternatively, use conda:")
    print("conda install -c conda-forge pillow requests tqdm")
    print("pip install customtkinter")  # customtkinter is not available in conda-forge
    GUI_DEPENDENCIES_AVAILABLE = False

# Import existing modules
try:
    from .booru_api import fetch_booru_posts, BOORU_APIS
    from .download import run_download
    # Import from parent directory (rulescrape.py)
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from rulescrape import load_user_settings, save_user_settings, run_script
    from .dupe_check import get_dupe_checker
    from .animated_preview import AnimatedPreview, PreviewCache, AnimationManager
    from .thumbnail_cache import DiskThumbnailCache
    MODULES_AVAILABLE = True
except ImportError as e:
    print(f"Error: Could not import required modules: {e}")
    print("Please ensure booru_api.py, download.py, rulescrape.py, and dupe_check.py are available.")
    MODULES_AVAILABLE = False

# Only proceed with GUI setup if dependencies are available
if GUI_DEPENDENCIES_AVAILABLE:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")


if GUI_DEPENDENCIES_AVAILABLE:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")


class ProgressiveGalleryLoader:
    """
    Progressive gallery loader that loads thumbnails in batches
    to provide responsive UI while processing large image collections.
    """
    
    def __init__(self, gui_instance, batch_size: int = 12):
        self.gui = gui_instance
        self.batch_size = batch_size
        self.loading_thread = None
        self.stop_loading = False
        
    def load_gallery_progressive(self, media_files: List[Path], gallery_limit: int):
        """Load gallery progressively in batches"""
        if self.loading_thread and self.loading_thread.is_alive():
            self.stop_loading = True
            self.loading_thread.join(timeout=1.0)
        
        self.stop_loading = False
        
        # Check if all thumbnails are already cached by testing a small batch
        # Since disk cache doesn't expose cache state directly, we'll use progressive loading
        cached_count = 0
        # For disk cache, we'll always use progressive loading for better responsiveness
        
        # Use progressive loading for all content with disk cache
        self.gui.log_message(f"📦 Loading {len(media_files[:gallery_limit])} thumbnails using disk cache...")
        self.loading_thread = threading.Thread(
            target=self._load_batches,
            args=(media_files[:gallery_limit],),
            daemon=True
        )
        self.loading_thread.start()
    
    def _load_cached_instantly(self, media_files: List[Path]):
        """Load all cached thumbnails instantly without progressive batching"""
        try:
            # Get all thumbnails at once (they're all cached)
            thumbnails = self.gui.thumbnail_cache.get_thumbnails_batch(media_files)
            
            # Display all thumbnails immediately
            displayed_count = 0
            for i, media_path in enumerate(media_files):
                if media_path in thumbnails:
                    try:
                        # Convert PIL Image to PhotoImage for tkinter
                        pil_thumbnail = thumbnails[media_path]
                        photo_thumbnail = ImageTk.PhotoImage(pil_thumbnail)
                        
                        row = i // 3
                        col = i % 3
                        self.gui.create_media_frame_optimized(media_path, photo_thumbnail, row, col)
                        displayed_count += 1
                    except Exception as e:
                        self.gui.log_message(f"❌ Error displaying {media_path.name}: {e}")
            
            # Update status immediately
            self.gui.update_status("Gallery loading complete")
            self.gui.log_message(f"✅ Gallery loaded instantly with {displayed_count} cached thumbnails")
            
        except Exception as e:
            self.gui.log_message(f"❌ Error in instant loading: {e}")
            # Fallback to progressive loading
            self.loading_thread = threading.Thread(
                target=self._load_batches,
                args=(media_files,),
                daemon=True
            )
            self.loading_thread.start()
    
    def _load_batches(self, media_files: List[Path]):
        """Load media files in batches"""
        total_files = len(media_files)
        processed = 0
        
        # Process files in batches
        for i in range(0, total_files, self.batch_size):
            if self.stop_loading:
                break
                
            batch = media_files[i:i + self.batch_size]
            
            # Get thumbnails for this batch
            thumbnails = self.gui.thumbnail_cache.get_thumbnails_batch(batch)
            
            # Schedule UI updates on main thread safely
            if not getattr(self.gui, 'is_closing', False):
                try:
                    self.gui.root.after(0, self._display_batch, batch, thumbnails, processed)
                except:
                    break  # GUI destroyed, stop loading
            
            processed += len(batch)
            
            # Brief pause to keep UI responsive during thumbnail processing
            # With disk cache, we always add a small delay for smooth loading
            time.sleep(0.01)
        
        # Update progress on completion
        if not self.stop_loading and not getattr(self.gui, 'is_closing', False):
            try:
                self.gui.root.after(0, self._loading_complete, processed)
            except:
                pass  # GUI destroyed, ignore
    
    def _display_batch(self, batch: List[Path], thumbnails: Dict[Path, 'Image.Image'], start_index: int):
        """Display a batch of thumbnails in the gallery"""
        displayed_count = 0
        for i, media_path in enumerate(batch):
            if self.stop_loading:
                break
                
            pil_thumbnail = thumbnails.get(media_path)
            if pil_thumbnail:
                try:
                    # Convert PIL Image to PhotoImage for tkinter
                    photo_thumbnail = ImageTk.PhotoImage(pil_thumbnail)
                    
                    # Calculate grid position
                    index = start_index + i
                    row = index // 3
                    col = index % 3
                    
                    self.gui.create_media_frame_optimized(media_path, photo_thumbnail, row, col)
                    displayed_count += 1
                except Exception as e:
                    self.gui.log_message(f"❌ Error displaying {media_path.name}: {e}")
        
        # Update progress status
        total_loaded = start_index + len(batch)
        try:
            if hasattr(self.gui, 'gallery_total_files'):
                self.gui.update_status(f"Loaded thumbnails: {total_loaded}/{self.gui.gallery_total_files}")
            else:
                self.gui.update_status(f"Loaded thumbnails: {total_loaded}")
        except:
            pass  # Gracefully handle missing update_status method
        
        return displayed_count
    
    def _loading_complete(self, total_loaded: int):
        """Called when loading is complete"""
        self.gui.log_message(f"✅ Gallery loaded with {total_loaded} media files")
        try:
            self.gui.update_status("Gallery loading complete")
        except:
            pass  # Gracefully handle missing update_status method
    
    def stop(self):
        """Stop the current loading process"""
        self.stop_loading = True
        if self.loading_thread and self.loading_thread.is_alive():
            self.loading_thread.join(timeout=1.0)


# Only proceed with GUI setup if dependencies are available
if GUI_DEPENDENCIES_AVAILABLE:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

class RulescrapGUI:
    def __init__(self):
        if not GUI_DEPENDENCIES_AVAILABLE:
            raise ImportError("GUI dependencies not available")
        
        self.root = ctk.CTk()
        self.root.title("Rulescrape v2.0")
        self.root.geometry("1200x800")
        self.root.minsize(900, 600)
        
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        
        self.download_queue = queue.Queue()
        self.is_downloading = False
        self.is_closing = False  # Flag to prevent scheduling during shutdown
        self.download_history = []
        self.settings = self.load_settings()
        self.migrate_history_file()  # Migrate history file to logs directory if needed
        self.load_history()
        
        # Download control
        self.current_download_manager = None
        self.download_thread = None
        
        # Initialize animation manager for gallery previews
        self.animation_manager = AnimationManager(self.root)
        
        # Initialize disk-based thumbnail cache
        cache_size_mb = self.settings.get("thumbnail_cache_size", 500)  # Now in MB
        max_workers = self.settings.get("thumbnail_workers", min(8, (os.cpu_count() or 1) + 4))
        cache_dir = os.path.join(self.settings.get("output_dir", "images"), "..", "cache", "thumbnails")
        self.thumbnail_cache = DiskThumbnailCache(cache_dir, cache_size_mb, max_workers)
        
        # Initialize progressive gallery loader
        batch_size = self.settings.get("gallery_batch_size", 12)
        self.gallery_loader = ProgressiveGalleryLoader(self, batch_size)
        
        self.create_sidebar()
        self.create_main_area()
        self.create_status_bar()
        
        self.process_queue()
        
        # Start error queue polling for CLI integration
        poll_error_queue(self.root)
        
    def load_settings(self):
        # Default settings that combine both rulescrape and GUI settings
        default_settings = {
            # Core rulescrape settings
            "booru_type": "rule34",
            "tag": "",
            "limit": 10,
            "anti_ai": False,
            "multithread": False,
            "org_method": "By extension and first tag",
            "max_workers": 4,
            "output_dir": "images",
            "skin": None,
            "window_width": 1200,
            "window_height": 800,
            # GUI-specific settings
            "theme": "dark",
            "animated_previews": True,  # Enable animated previews on hover
            "confirm_exit": True,
            "download_history_limit": 100,
            "gallery_image_limit": 50,  # Max images to load in gallery (1-2000)
            "gallery_page_size": 200,   # Images per page for pagination
            "gallery_extension_filter": "All",  # Extension filter for gallery
            # Performance settings
            "thumbnail_cache_size": 500,  # Disk cache size in megabytes
            "thumbnail_workers": min(8, (os.cpu_count() or 1) + 4),  # Number of thumbnail generation threads
            "gallery_batch_size": 12  # Number of thumbnails to load per batch
        }
        
        # Load from settings.json
        settings_file = Path("settings.json")
        if settings_file.exists():
            try:
                with open(settings_file, 'r') as f:
                    loaded_settings = json.load(f)
                    default_settings.update(loaded_settings)
            except Exception as e:
                print(f"Error loading settings.json: {e}")
        
        # Migration: Load from legacy user_settings.config if settings.json doesn't have core settings
        if not settings_file.exists() or "booru_type" not in default_settings:
            legacy_settings = self.load_legacy_settings()
            if legacy_settings:
                default_settings.update(legacy_settings)
                print("🔄 Migrated settings from user_settings.config to settings.json")
                # Save migrated settings immediately
                self.settings = default_settings
                self.save_settings()
        
        return default_settings
    
    def load_legacy_settings(self):
        """Load settings from legacy user_settings.config file"""
        import configparser
        import multiprocessing
        
        config_file = Path("user_settings.config")
        if not config_file.exists():
            return None
            
        cpu_threads = multiprocessing.cpu_count()
        default_workers = max(1, cpu_threads // 2)
        
        config = configparser.ConfigParser()
        legacy_settings = {}
        
        try:
            config.read(config_file)
            
            if 'Settings' in config:
                legacy_settings['booru_type'] = config['Settings'].get('booru_type', 'rule34')
                legacy_settings['tag'] = config['Settings'].get('tag', '')
                legacy_settings['limit'] = config['Settings'].getint('limit', 10)
                legacy_settings['anti_ai'] = config['Settings'].getboolean('anti_ai', False)
                legacy_settings['multithread'] = config['Settings'].getboolean('multithread', False)
                legacy_settings['org_method'] = config['Settings'].get('org_method', 'By extension and first tag')
                legacy_settings['max_workers'] = config['Settings'].getint('max_workers', default_workers)
                legacy_settings['output_dir'] = config['Settings'].get('output_dir', 'images')
                
            if 'UI' in config:
                skin_value = config['UI'].get('skin', 'None')
                legacy_settings['skin'] = None if skin_value == 'None' else skin_value
                legacy_settings['window_width'] = config['UI'].getint('window_width', 1200)
                legacy_settings['window_height'] = config['UI'].getint('window_height', 800)
                
            return legacy_settings
            
        except Exception as e:
            print(f"Error loading legacy settings: {e}")
            return None
    
    def validate_int_entry(self, value, default=0, min_val=None, max_val=None):
        """Safely convert string to integer with validation"""
        try:
            if not value or value.strip() == "":
                return default
            int_val = int(value.strip())
            if min_val is not None and int_val < min_val:
                return min_val
            if max_val is not None and int_val > max_val:
                return max_val
            return int_val
        except (ValueError, AttributeError):
            return default
    
    def load_history(self):
        """Load download history from file"""
        # Ensure logs directory exists
        logs_dir = "logs"
        os.makedirs(logs_dir, exist_ok=True)
        
        history_file = Path(os.path.join(logs_dir, "download_history.json"))
        if history_file.exists():
            try:
                with open(history_file, 'r') as f:
                    self.download_history = json.load(f)
                print(f"Loaded {len(self.download_history)} history entries")
            except Exception as e:
                print(f"Error loading history: {e}")
                self.download_history = []
        else:
            self.download_history = []
    
    def save_history(self):
        """Save download history to file"""
        try:
            # Ensure logs directory exists
            logs_dir = "logs"
            os.makedirs(logs_dir, exist_ok=True)
            
            history_file = os.path.join(logs_dir, "download_history.json")
            with open(history_file, 'w') as f:
                json.dump(self.download_history, f, indent=2, default=str)
        except Exception as e:
            print(f"Error saving history: {e}")
    
    def migrate_history_file(self):
        """Migrate existing download_history.json from root to logs directory"""
        old_history_file = "download_history.json"
        logs_dir = "logs"
        new_history_file = os.path.join(logs_dir, "download_history.json")
        
        # If old file exists and new file doesn't exist, migrate it
        if os.path.exists(old_history_file) and not os.path.exists(new_history_file):
            try:
                os.makedirs(logs_dir, exist_ok=True)
                import shutil
                shutil.move(old_history_file, new_history_file)
                print(f"🔄 Migrated download_history.json to {new_history_file}")
            except Exception as e:
                print(f"Warning: Could not migrate download history file: {e}")
    
    def save_settings(self):
        try:
            # Save all settings to settings.json (no longer splitting between files)
            settings_to_save = {
                # Core rulescrape settings
                "booru_type": self.settings.get("booru_type", "rule34"),
                "tag": self.settings.get("tag", ""),
                "limit": self.settings.get("limit", 10),
                "anti_ai": self.settings.get("anti_ai", False),
                "multithread": self.settings.get("multithread", False),
                "org_method": self.settings.get("org_method", "By extension and first tag"),
                "max_workers": self.settings.get("max_workers", 4),
                "output_dir": self.settings.get("output_dir", "images"),
                "skin": self.settings.get("skin", None),
                "window_width": self.settings.get("window_width", 1200),
                "window_height": self.settings.get("window_height", 800),
                # GUI-specific settings
                "theme": self.settings.get("theme", "dark"),
                "animated_previews": self.settings.get("animated_previews", True),
                "confirm_exit": self.settings.get("confirm_exit", True),
                "download_history_limit": self.settings.get("download_history_limit", 100),
                "gallery_image_limit": self.settings.get("gallery_image_limit", 50),
                "gallery_extension_filter": self.settings.get("gallery_extension_filter", "All"),
                # Performance settings
                "thumbnail_cache_size": self.settings.get("thumbnail_cache_size", 500),
                "thumbnail_workers": self.settings.get("thumbnail_workers", min(8, (os.cpu_count() or 1) + 4)),
                "gallery_batch_size": self.settings.get("gallery_batch_size", 12)
            }
            
            with open("settings.json", 'w') as f:
                json.dump(settings_to_save, f, indent=2)
            
            # Save history as well
            self.save_history()
            
        except Exception as e:
            print(f"Error saving settings: {e}")
    
    def create_sidebar(self):
        self.sidebar = ctk.CTkFrame(self.root, width=250)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        self.sidebar.grid_propagate(False)
        
        title_label = ctk.CTkLabel(
            self.sidebar, 
            text="🎨 Rulescrape", 
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.grid(row=0, column=0, padx=20, pady=(20, 30))
        
        # Quick Download Section
        quick_frame = ctk.CTkFrame(self.sidebar)
        quick_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 20))
        
        ctk.CTkLabel(quick_frame, text="Quick Download", 
                    font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=10, pady=(10, 5))
        
        # Booru selection
        self.booru_var = ctk.StringVar(value=self.settings["booru_type"])
        booru_menu = ctk.CTkOptionMenu(
            quick_frame,
            variable=self.booru_var,
            values=["rule34", "safebooru", "danbooru", "yande.re", "paheal"],
            command=self.on_booru_change
        )
        booru_menu.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        
        # Tag entry
        self.tag_entry = ctk.CTkEntry(quick_frame, placeholder_text="Enter tags (optional)...")
        self.tag_entry.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        self.tag_entry.bind("<Return>", self.quick_download)
        
        # Add help text
        help_label = ctk.CTkLabel(quick_frame, text="💡 Leave empty to download recent images", 
                                 font=ctk.CTkFont(size=11), text_color="gray")
        help_label.grid(row=3, column=0, padx=10, pady=(0, 5), sticky="w")
        
        # Limit controls
        limit_frame = ctk.CTkFrame(quick_frame)
        limit_frame.grid(row=4, column=0, padx=10, pady=5, sticky="ew")
        
        ctk.CTkLabel(limit_frame, text="Limit:").grid(row=0, column=0, padx=5)
        self.limit_var = ctk.StringVar(value="10")
        limit_entry = ctk.CTkEntry(limit_frame, textvariable=self.limit_var, width=60)
        limit_entry.grid(row=0, column=1, padx=5)
        
        self.quick_dl_btn = ctk.CTkButton(
            quick_frame, 
            text="🚀 Quick Download",
            command=self.quick_download,
            height=40
        )
        self.quick_dl_btn.grid(row=5, column=0, padx=10, pady=10, sticky="ew")
        
        # Navigation buttons
        nav_frame = ctk.CTkFrame(self.sidebar)
        nav_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 20))
        nav_frame.grid_columnconfigure(0, weight=1)  # Center the buttons
        
        nav_buttons = [
            ("📥 Downloads", self.show_downloads_tab),
            ("📁 Gallery", self.show_gallery_tab),
            ("📊 History", self.show_history_tab),
            ("🔧 Settings", self.show_settings_tab),
        ]
        
        for i, (text, command) in enumerate(nav_buttons):
            btn = ctk.CTkButton(nav_frame, text=text, command=command, height=35)
            btn.grid(row=i, column=0, padx=10, pady=5, sticky="ew")
        
        # Theme toggle
        theme_frame = ctk.CTkFrame(self.sidebar)
        theme_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 20))
        
        ctk.CTkLabel(theme_frame, text="Appearance", 
                    font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=10, pady=(10, 5))
        
        self.theme_switch = ctk.CTkSwitch(
            theme_frame, 
            text="Dark Mode", 
            command=self.toggle_theme,
            onvalue="dark",
            offvalue="light"
        )
        self.theme_switch.grid(row=1, column=0, padx=10, pady=(0, 10))
        if self.settings["theme"] == "dark":
            self.theme_switch.select()
    
    def create_main_area(self):
        self.main_frame = ctk.CTkFrame(self.root)
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=1)
        
        self.tabview = ctk.CTkTabview(self.main_frame, command=self.on_tab_change)
        self.tabview.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        
        self.downloads_tab = self.tabview.add("Downloads")
        self.gallery_tab = self.tabview.add("Gallery")
        self.history_tab = self.tabview.add("History")
        self.settings_tab = self.tabview.add("Settings")
        
        self.setup_downloads_tab()
        self.setup_gallery_tab()
        self.setup_history_tab()
        self.setup_settings_tab()
    
    def setup_downloads_tab(self):
        self.downloads_tab.grid_columnconfigure((0, 1), weight=1)
        self.downloads_tab.grid_rowconfigure(2, weight=1)
        
        # Advanced search
        search_frame = ctk.CTkFrame(self.downloads_tab)
        search_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=10)
        search_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(search_frame, text="Advanced Search", 
                    font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, columnspan=3, pady=10)
        
        ctk.CTkLabel(search_frame, text="Tags (optional):").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.advanced_tags = ctk.CTkTextbox(search_frame, height=60)
        self.advanced_tags.grid(row=1, column=1, columnspan=2, padx=10, pady=5, sticky="ew")
        # Add helpful placeholder text
        self.advanced_tags.insert("0.0", "Enter tags separated by spaces (leave empty for recent images)...")
        self.advanced_tags.configure(text_color="gray")
        
        # Bind focus events to handle placeholder text
        def on_tags_focus_in(event):
            current_text = self.advanced_tags.get("1.0", "end-1c")
            if current_text == "Enter tags separated by spaces (leave empty for recent images)...":
                self.advanced_tags.delete("1.0", "end")
                self.advanced_tags.configure(text_color="white" if self.settings.get("theme", "dark") == "dark" else "black")
        
        def on_tags_focus_out(event):
            current_text = self.advanced_tags.get("1.0", "end-1c").strip()
            if not current_text:
                self.advanced_tags.insert("1.0", "Enter tags separated by spaces (leave empty for recent images)...")
                self.advanced_tags.configure(text_color="gray")
        
        self.advanced_tags.bind("<FocusIn>", on_tags_focus_in)
        self.advanced_tags.bind("<FocusOut>", on_tags_focus_out)
        
        ctk.CTkLabel(search_frame, text="Limit:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.advanced_limit_var = ctk.StringVar(value="20")
        advanced_limit_entry = ctk.CTkEntry(search_frame, textvariable=self.advanced_limit_var, width=100)
        advanced_limit_entry.grid(row=2, column=1, sticky="w", padx=10, pady=5)
        
        # Options
        options_frame = ctk.CTkFrame(search_frame)
        options_frame.grid(row=3, column=0, columnspan=3, sticky="ew", padx=10, pady=10)
        
        self.multithread_var = ctk.BooleanVar(value=self.settings.get("multithread", True))
        self.anti_ai_var = ctk.BooleanVar(value=self.settings.get("anti_ai", False))
        
        ctk.CTkCheckBox(options_frame, text="Multi-threaded download", 
                       variable=self.multithread_var).grid(row=0, column=0, padx=10, pady=5, sticky="w")
        ctk.CTkCheckBox(options_frame, text="Exclude AI content", 
                       variable=self.anti_ai_var).grid(row=0, column=1, padx=10, pady=5, sticky="w")
        
        # Download controls
        controls_frame = ctk.CTkFrame(self.downloads_tab)
        controls_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=10)
        
        self.download_btn = ctk.CTkButton(
            controls_frame, 
            text="🚀 Start Download", 
            command=self.start_advanced_download,
            height=50,
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.download_btn.grid(row=0, column=0, padx=10, pady=10)
        
        self.pause_btn = ctk.CTkButton(
            controls_frame, 
            text="⏸ Pause", 
            command=self.pause_download,
            state="disabled"
        )
        self.pause_btn.grid(row=0, column=1, padx=10, pady=10)
        
        self.stop_btn = ctk.CTkButton(
            controls_frame, 
            text="⏹ Stop", 
            command=self.stop_download,
            state="disabled"
        )
        self.stop_btn.grid(row=0, column=2, padx=10, pady=10)
        
        # Progress area
        progress_frame = ctk.CTkFrame(self.downloads_tab)
        progress_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=10, pady=10)
        progress_frame.grid_columnconfigure(0, weight=1)
        progress_frame.grid_rowconfigure(1, weight=1)
        
        ctk.CTkLabel(progress_frame, text="Download Progress", 
                    font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, pady=10)
        
        self.progress_var = ctk.DoubleVar()
        self.progress_bar = ctk.CTkProgressBar(progress_frame, variable=self.progress_var)
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=20, pady=5)
        
        self.progress_label = ctk.CTkLabel(progress_frame, text="Ready to download")
        self.progress_label.grid(row=2, column=0, pady=5)
        
        self.log_textbox = ctk.CTkTextbox(progress_frame, height=200)
        self.log_textbox.grid(row=3, column=0, sticky="nsew", padx=20, pady=10)
    
    def setup_gallery_tab(self):
        self.gallery_tab.grid_columnconfigure(0, weight=1)
        self.gallery_tab.grid_rowconfigure(1, weight=1)
        
        gallery_controls = ctk.CTkFrame(self.gallery_tab)
        gallery_controls.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        
        ctk.CTkLabel(gallery_controls, text="Image Gallery", 
                    font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, padx=10, pady=10)
        
        # Extension filter dropdown
        ctk.CTkLabel(gallery_controls, text="Filter:").grid(row=0, column=1, padx=(20, 5), pady=10)
        self.extension_filter_var = ctk.StringVar(value=self.settings.get("gallery_extension_filter", "All"))
        extension_filter_menu = ctk.CTkOptionMenu(
            gallery_controls,
            variable=self.extension_filter_var,
            values=["All", "Images", "Videos", ".jpg/.jpeg", ".png", ".gif", ".bmp", ".webp", ".mp4", ".webm"],
            command=self.on_extension_filter_change,
            width=100
        )
        extension_filter_menu.grid(row=0, column=2, padx=5, pady=10)
        
        refresh_btn = ctk.CTkButton(gallery_controls, text="🔄 Refresh", command=self.refresh_gallery)
        refresh_btn.grid(row=0, column=3, padx=10, pady=10)
        
        open_folder_btn = ctk.CTkButton(gallery_controls, text="📁 Open Folder", command=self.open_images_folder)
        open_folder_btn.grid(row=0, column=4, padx=10, pady=10)
        
        # Pagination controls (initially hidden)
        self.pagination_frame = ctk.CTkFrame(gallery_controls)
        self.pagination_frame.grid(row=0, column=5, columnspan=3, padx=20, pady=10)
        
        self.prev_page_btn = ctk.CTkButton(self.pagination_frame, text="◀ Prev", 
                                          command=self.prev_page, width=60)
        self.prev_page_btn.grid(row=0, column=0, padx=5)
        
        self.page_label = ctk.CTkLabel(self.pagination_frame, text="Page 1 of 1")
        self.page_label.grid(row=0, column=1, padx=10)
        
        self.next_page_btn = ctk.CTkButton(self.pagination_frame, text="Next ▶", 
                                          command=self.next_page, width=60)
        self.next_page_btn.grid(row=0, column=2, padx=5)
        
        # Initially hide pagination (will show when needed)
        self.pagination_frame.grid_remove()
        
        # Gallery state
        self.current_page = 0
        self.total_pages = 1
        self.all_media_files = []
        self.page_size = self.settings.get("gallery_page_size", 200)
        
        # Scrollable frame for images (3 columns) - improved scrolling
        self.gallery_scroll = ctk.CTkScrollableFrame(self.gallery_tab, height=500)
        self.gallery_scroll.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        
        # Configure grid columns for 3-column layout
        for i in range(3):
            self.gallery_scroll.grid_columnconfigure(i, weight=1)
        
        # Enable consistent mouse wheel scrolling - simplified approach
        self._setup_gallery_scrolling()
    
    def prev_page(self):
        """Go to previous page"""
        if self.current_page > 0:
            self.current_page -= 1
            self._load_current_page()
            self._scroll_gallery_to_top()
    
    def next_page(self):
        """Go to next page"""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self._load_current_page()
            self._scroll_gallery_to_top()
    
    def _load_current_page(self):
        """Load the current page of media files"""
        if not self.all_media_files:
            return
        
        # Calculate page bounds
        start_idx = self.current_page * self.page_size
        end_idx = min(start_idx + self.page_size, len(self.all_media_files))
        page_files = self.all_media_files[start_idx:end_idx]
        
        # Update pagination controls
        self.page_label.configure(text=f"Page {self.current_page + 1} of {self.total_pages}")
        self.prev_page_btn.configure(state="normal" if self.current_page > 0 else "disabled")
        self.next_page_btn.configure(state="normal" if self.current_page < self.total_pages - 1 else "disabled")
        
        # Clear existing gallery
        for widget in self.gallery_scroll.winfo_children():
            widget.destroy()
        
        # Scroll to top when loading new page
        self.root.after(50, self._scroll_gallery_to_top)  # Small delay to ensure widgets are cleared
        
        # Update status
        self.update_status(f"Loading page {self.current_page + 1}...")
        
        # Load thumbnails for current page
        self.gallery_total_files = len(page_files)
        self.gallery_loader.load_gallery_progressive(page_files, len(page_files))
        
        # Additional scroll-to-top after a short delay to ensure it works with loaded content
        self.root.after(200, self._scroll_gallery_to_top)
        
        self.log_message(f"📄 Loaded page {self.current_page + 1} ({len(page_files)} images)")
    
    def _update_pagination_controls(self):
        """Update pagination controls visibility and state"""
        if self.total_pages > 1:
            self.pagination_frame.grid()  # Show pagination
        else:
            self.pagination_frame.grid_remove()  # Hide pagination
    
    def _scroll_gallery_to_top(self):
        """Scroll the gallery scrollable frame to the top"""
        try:
            # Method 1: Try CustomTkinter's internal canvas access
            if hasattr(self.gallery_scroll, '_parent_canvas'):
                canvas = self.gallery_scroll._parent_canvas
                if canvas and hasattr(canvas, 'yview_moveto'):
                    canvas.yview_moveto(0.0)
                    return True
            
            # Method 2: Search for canvas in widget children
            def find_canvas(widget):
                """Recursively find Canvas widget"""
                try:
                    for child in widget.winfo_children():
                        if isinstance(child, tk.Canvas):
                            return child
                        elif hasattr(child, 'winfo_children'):
                            result = find_canvas(child)
                            if result:
                                return result
                except:
                    pass
                return None
            
            canvas = find_canvas(self.gallery_scroll)
            if canvas and hasattr(canvas, 'yview_moveto'):
                canvas.yview_moveto(0.0)
                return True
            
            # Method 3: Try accessing scrollbar directly
            if hasattr(self.gallery_scroll, '_scrollbar'):
                scrollbar = self.gallery_scroll._scrollbar
                if scrollbar and hasattr(scrollbar, 'set'):
                    scrollbar.set(0.0, 0.1)
                    return True
            
            # Method 4: Try the scrollable frame's configure method
            if hasattr(self.gallery_scroll, 'configure'):
                # Some scrollable frames support direct scrolling
                try:
                    self.gallery_scroll.configure(scrollregion=self.gallery_scroll.bbox("all"))
                    return True
                except:
                    pass
                    
        except Exception as e:
            # Silently handle any errors, scrolling is not critical
            self.log_message(f"⚠️ Could not scroll gallery to top: {e}")
        
        return False
    
    def _setup_settings_scrolling(self):
        """Set up consistent mouse wheel scrolling for the settings"""
        def scroll_settings(event):
            """Handle mouse wheel scrolling for settings"""
            try:
                # Calculate scroll amount with improved sensitivity
                if event.delta:
                    # Windows/Mac - event.delta is usually ±120
                    # Use 3 units per scroll for smoother experience
                    scroll_amount = -3 * (event.delta // 120)
                else:
                    # Linux - event.num is 4 (up) or 5 (down)
                    # Use 3 units for consistency
                    scroll_amount = -3 if event.num == 4 else 3
                
                # Get the internal canvas of the scrollable frame
                canvas = None
                
                # Try different ways to access the canvas
                if hasattr(self.settings_scroll, '_parent_canvas'):
                    canvas = self.settings_scroll._parent_canvas
                elif hasattr(self.settings_scroll, 'winfo_children'):
                    # Find canvas among children
                    for child in self.settings_scroll.winfo_children():
                        if isinstance(child, tk.Canvas):
                            canvas = child
                            break
                
                # Scroll the canvas if found
                if canvas and hasattr(canvas, 'yview_scroll'):
                    canvas.yview_scroll(scroll_amount, "units")
                    return "break"  # Prevent event propagation
                    
            except Exception:
                pass  # Silently handle any errors
            
            return "break"
        
        def linux_scroll_up(event):
            event.delta = 120
            return scroll_settings(event)
        
        def linux_scroll_down(event):
            event.delta = -120
            return scroll_settings(event)
        
        # Bind to the settings scroll frame directly for comprehensive coverage
        try:
            self.settings_scroll.bind("<MouseWheel>", scroll_settings, add="+")
            self.settings_scroll.bind("<Button-4>", linux_scroll_up, add="+")
            self.settings_scroll.bind("<Button-5>", linux_scroll_down, add="+")
        except Exception:
            pass
        
        # Also bind to the settings tab itself
        try:
            self.settings_tab.bind("<MouseWheel>", scroll_settings, add="+")
            self.settings_tab.bind("<Button-4>", linux_scroll_up, add="+")
            self.settings_tab.bind("<Button-5>", linux_scroll_down, add="+")
        except Exception:
            pass
    
    def _global_settings_scroll_handler(self, event):
        """Global scroll handler that only acts when mouse is over settings"""
        try:
            # Check if mouse is over the settings tab
            current_tab = self.tabview.get()
            if current_tab != "Settings":
                return
            
            # Get mouse position
            x, y = self.root.winfo_pointerxy()
            widget_under_mouse = self.root.winfo_containing(x, y)
            
            # Check if the widget under mouse is part of the settings scroll area
            settings_widgets = [self.settings_scroll]
            
            # Add all settings scroll children to the list
            def get_all_children(widget):
                children = [widget]
                for child in widget.winfo_children():
                    children.extend(get_all_children(child))
                return children
            
            settings_widgets.extend(get_all_children(self.settings_scroll))
            
            # If mouse is over settings area, handle scrolling
            if widget_under_mouse in settings_widgets:
                # Calculate scroll amount with improved sensitivity
                if hasattr(event, 'delta') and event.delta:
                    scroll_amount = -3 * (event.delta // 120)
                elif hasattr(event, 'num'):
                    scroll_amount = -3 if event.num == 4 else 3
                else:
                    return
                
                # Find and scroll the canvas
                canvas = None
                if hasattr(self.settings_scroll, '_parent_canvas'):
                    canvas = self.settings_scroll._parent_canvas
                elif hasattr(self.settings_scroll, 'winfo_children'):
                    for child in self.settings_scroll.winfo_children():
                        if isinstance(child, tk.Canvas):
                            canvas = child
                            break
                
                if canvas and hasattr(canvas, 'yview_scroll'):
                    canvas.yview_scroll(scroll_amount, "units")
                    return "break"
                    
        except Exception:
            pass  # Handle errors silently
        
        return None

    def _setup_gallery_scrolling(self):
        """Set up consistent mouse wheel scrolling for the gallery"""
        def scroll_gallery(event):
            """Handle mouse wheel scrolling for gallery"""
            try:
                # Calculate scroll amount with improved sensitivity
                if event.delta:
                    # Windows/Mac - event.delta is usually ±120
                    # Use 3 units per scroll for smoother experience
                    scroll_amount = -3 * (event.delta // 120)
                else:
                    # Linux - event.num is 4 (up) or 5 (down)
                    # Use 3 units for consistency
                    scroll_amount = -3 if event.num == 4 else 3
                
                # Get the internal canvas of the scrollable frame
                canvas = None
                
                # Try different ways to access the canvas
                if hasattr(self.gallery_scroll, '_parent_canvas'):
                    canvas = self.gallery_scroll._parent_canvas
                elif hasattr(self.gallery_scroll, 'winfo_children'):
                    # Find canvas among children
                    for child in self.gallery_scroll.winfo_children():
                        if isinstance(child, tk.Canvas):
                            canvas = child
                            break
                
                # Scroll the canvas if found
                if canvas and hasattr(canvas, 'yview_scroll'):
                    canvas.yview_scroll(scroll_amount, "units")
                    return "break"  # Prevent event propagation
                    
            except Exception:
                pass  # Silently handle any errors
            
            return "break"
        
        def linux_scroll_up(event):
            event.delta = 120
            return scroll_gallery(event)
        
        def linux_scroll_down(event):
            event.delta = -120
            return scroll_gallery(event)
        
        # Bind to multiple widgets to catch scroll events consistently
        widgets_to_bind = [self.gallery_scroll, self.gallery_tab]
        
        for widget in widgets_to_bind:
            # Windows/Mac mouse wheel
            widget.bind("<MouseWheel>", scroll_gallery, add="+")
            # Linux mouse wheel
            widget.bind("<Button-4>", linux_scroll_up, add="+")
            widget.bind("<Button-5>", linux_scroll_down, add="+")
        
        # Also bind to the root window to catch events when mouse is anywhere in gallery area
        self.root.bind("<MouseWheel>", self._global_scroll_handler, add="+")
        self.root.bind("<Button-4>", self._global_scroll_handler, add="+")
        self.root.bind("<Button-5>", self._global_scroll_handler, add="+")
    
    def _bind_settings_scroll_events(self, widget):
        """Bind scroll events to a settings widget to enable scrolling when hovering over it"""
        def scroll_handler(event):
            """Handle scroll events on individual settings widgets"""
            try:
                # Calculate scroll amount
                if hasattr(event, 'delta') and event.delta:
                    scroll_amount = -3 * (event.delta // 120)
                elif hasattr(event, 'num'):
                    scroll_amount = -3 if event.num == 4 else 3
                else:
                    return
                
                # Find and scroll the canvas
                canvas = None
                if hasattr(self.settings_scroll, '_parent_canvas'):
                    canvas = self.settings_scroll._parent_canvas
                elif hasattr(self.settings_scroll, 'winfo_children'):
                    for child in self.settings_scroll.winfo_children():
                        if isinstance(child, tk.Canvas):
                            canvas = child
                            break
                
                if canvas and hasattr(canvas, 'yview_scroll'):
                    canvas.yview_scroll(scroll_amount, "units")
                    return "break"
                    
            except Exception:
                pass
            
            return "break"
        
        def linux_scroll_up(event):
            event.delta = 120
            return scroll_handler(event)
        
        def linux_scroll_down(event):
            event.delta = -120
            return scroll_handler(event)
        
        try:
            # Bind scroll events to the widget with improved error handling
            if hasattr(widget, 'bind'):
                widget.bind("<MouseWheel>", scroll_handler, add="+")
                widget.bind("<Button-4>", linux_scroll_up, add="+")
                widget.bind("<Button-5>", linux_scroll_down, add="+")
        except Exception:
            # Some widgets might not support binding, silently ignore
            pass

    def _bind_scroll_events(self, widget):
        """Bind scroll events to a widget to enable scrolling when hovering over it"""
        def scroll_handler(event):
            """Handle scroll events on individual widgets"""
            try:
                # Calculate scroll amount
                if hasattr(event, 'delta') and event.delta:
                    scroll_amount = -3 * (event.delta // 120)
                elif hasattr(event, 'num'):
                    scroll_amount = -3 if event.num == 4 else 3
                else:
                    return
                
                # Find and scroll the canvas
                canvas = None
                if hasattr(self.gallery_scroll, '_parent_canvas'):
                    canvas = self.gallery_scroll._parent_canvas
                elif hasattr(self.gallery_scroll, 'winfo_children'):
                    for child in self.gallery_scroll.winfo_children():
                        if isinstance(child, tk.Canvas):
                            canvas = child
                            break
                
                if canvas and hasattr(canvas, 'yview_scroll'):
                    canvas.yview_scroll(scroll_amount, "units")
                    return "break"
                    
            except Exception:
                pass
            
            return "break"
        
        def linux_scroll_up(event):
            event.delta = 120
            return scroll_handler(event)
        
        def linux_scroll_down(event):
            event.delta = -120
            return scroll_handler(event)
        
        try:
            # Bind scroll events to the widget
            widget.bind("<MouseWheel>", scroll_handler, add="+")
            widget.bind("<Button-4>", linux_scroll_up, add="+")
            widget.bind("<Button-5>", linux_scroll_down, add="+")
        except Exception:
            # Some widgets might not support binding, silently ignore
            pass
    
    def _global_scroll_handler(self, event):
        """Global scroll handler that only acts when mouse is over gallery"""
        try:
            # Check if mouse is over the gallery tab
            current_tab = self.tabview.get()
            if current_tab != "Gallery":
                return
            
            # Get mouse position
            x, y = self.root.winfo_pointerxy()
            widget_under_mouse = self.root.winfo_containing(x, y)
            
            # Check if the widget under mouse is part of the gallery scroll area
            gallery_widgets = [self.gallery_scroll]
            
            # Add all gallery scroll children to the list
            def get_all_children(widget):
                children = [widget]
                for child in widget.winfo_children():
                    children.extend(get_all_children(child))
                return children
            
            gallery_widgets.extend(get_all_children(self.gallery_scroll))
            
            # If mouse is over gallery area, handle scrolling
            if widget_under_mouse in gallery_widgets:
                # Calculate scroll amount with improved sensitivity
                if hasattr(event, 'delta') and event.delta:
                    scroll_amount = -3 * (event.delta // 120)
                elif hasattr(event, 'num'):
                    scroll_amount = -3 if event.num == 4 else 3
                else:
                    return
                
                # Find and scroll the canvas
                canvas = None
                if hasattr(self.gallery_scroll, '_parent_canvas'):
                    canvas = self.gallery_scroll._parent_canvas
                elif hasattr(self.gallery_scroll, 'winfo_children'):
                    for child in self.gallery_scroll.winfo_children():
                        if isinstance(child, tk.Canvas):
                            canvas = child
                            break
                
                if canvas and hasattr(canvas, 'yview_scroll'):
                    canvas.yview_scroll(scroll_amount, "units")
                    return "break"
                    
        except Exception:
            pass  # Handle errors silently
        
        return None
    
    def setup_history_tab(self):
        self.history_tab.grid_columnconfigure(0, weight=1)
        self.history_tab.grid_rowconfigure(1, weight=1)
        
        history_controls = ctk.CTkFrame(self.history_tab)
        history_controls.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        
        ctk.CTkLabel(history_controls, text="Download History", 
                    font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, padx=10, pady=10)
        
        clear_btn = ctk.CTkButton(history_controls, text="Clear History", command=self.clear_history)
        clear_btn.grid(row=0, column=1, padx=10, pady=10)
        
        export_btn = ctk.CTkButton(history_controls, text="Export", command=self.export_history)
        export_btn.grid(row=0, column=2, padx=10, pady=10)
        
        # History list using Treeview
        history_frame = ctk.CTkFrame(self.history_tab)
        history_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        history_frame.grid_columnconfigure(0, weight=1)
        history_frame.grid_rowconfigure(0, weight=1)
        
        columns = ("Date", "Booru", "Tags", "Count", "Status")
        self.history_tree = ttk.Treeview(history_frame, columns=columns, show="headings", height=15)
        
        for col in columns:
            self.history_tree.heading(col, text=col)
            self.history_tree.column(col, width=120)
        
        v_scrollbar = ttk.Scrollbar(history_frame, orient="vertical", command=self.history_tree.yview)
        h_scrollbar = ttk.Scrollbar(history_frame, orient="horizontal", command=self.history_tree.xview)
        self.history_tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        self.history_tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
    
    def setup_settings_tab(self):
        self.settings_tab.grid_columnconfigure(0, weight=1)
        self.settings_tab.grid_rowconfigure(0, weight=1)
        
        # Create scrollable frame for settings
        self.settings_scroll = ctk.CTkScrollableFrame(self.settings_tab, height=500)
        self.settings_scroll.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.settings_scroll.grid_columnconfigure(0, weight=1)
        
        # Enable mouse wheel scrolling for settings
        self._setup_settings_scrolling()
        
        sections = [
            ("Download Settings", self.create_download_settings),
            ("Blacklist Settings", self.create_blacklist_settings),
            ("Interface Settings", self.create_interface_settings),
            ("Advanced Settings", self.create_advanced_settings),
        ]
        
        row = 0
        for title, creator in sections:
            frame = ctk.CTkFrame(self.settings_scroll)
            frame.grid(row=row, column=0, sticky="ew", padx=10, pady=10)
            frame.grid_columnconfigure(1, weight=1)
            
            ctk.CTkLabel(frame, text=title, 
                        font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, columnspan=2, pady=10)
            
            creator(frame)
            
            # Recursively bind scroll events to all widgets in this section
            self._bind_scroll_to_all_children(frame)
            
            row += 1
    
    def _bind_scroll_to_all_children(self, parent_widget):
        """Recursively bind scroll events to all child widgets"""
        try:
            # Bind to the parent first
            self._bind_settings_scroll_events(parent_widget)
            
            # Recursively bind to all children
            for child in parent_widget.winfo_children():
                self._bind_settings_scroll_events(child)
                # Recursively process grandchildren
                self._bind_scroll_to_all_children(child)
        except Exception:
            # Handle any widget traversal errors silently
            pass
    
    def create_download_settings(self, parent):
        # Output directory
        ctk.CTkLabel(parent, text="Output Directory:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        
        dir_frame = ctk.CTkFrame(parent)
        dir_frame.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        dir_frame.grid_columnconfigure(0, weight=1)
        
        self.output_dir_var = ctk.StringVar(value=self.settings["output_dir"])
        dir_entry = ctk.CTkEntry(dir_frame, textvariable=self.output_dir_var)
        dir_entry.grid(row=0, column=0, sticky="ew", padx=5)
        
        browse_btn = ctk.CTkButton(dir_frame, text="Browse", command=self.browse_output_dir, width=80)
        browse_btn.grid(row=0, column=1, padx=5)
        
        # Max workers
        ctk.CTkLabel(parent, text="Max Workers:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.max_workers_var = ctk.IntVar(value=self.settings["max_workers"])
        workers_slider = ctk.CTkSlider(parent, from_=1, to=16, variable=self.max_workers_var, number_of_steps=15)
        workers_slider.grid(row=2, column=1, sticky="ew", padx=10, pady=5)
        
        # Organization method
        ctk.CTkLabel(parent, text="Organization:").grid(row=3, column=0, padx=10, pady=5, sticky="w")
        self.org_method_var = ctk.StringVar(value=self.settings["org_method"])
        org_menu = ctk.CTkOptionMenu(
            parent, 
            variable=self.org_method_var,
            values=["By extension and first tag", "By extension only", "By tag only", "Flat (no folders)"]
        )
        org_menu.grid(row=3, column=1, sticky="ew", padx=10, pady=5)
    
    def create_blacklist_settings(self, parent):
        """Create blacklist management settings section"""
        # Import blacklist manager
        from .blacklist import get_blacklist_manager
        
        # Initialize blacklist manager
        self.blacklist_manager = get_blacklist_manager()
        
        # Blacklist enable/disable
        blacklist_stats = self.blacklist_manager.get_blacklist_stats()
        self.blacklist_enabled_var = ctk.BooleanVar(value=blacklist_stats['enabled'])
        
        enable_checkbox = ctk.CTkCheckBox(
            parent, 
            text="Enable Blacklist Filtering", 
            variable=self.blacklist_enabled_var,
            command=self.on_blacklist_toggle
        )
        enable_checkbox.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="w")
        
        # Case sensitivity
        self.blacklist_case_var = ctk.BooleanVar(value=blacklist_stats['case_sensitive'])
        case_checkbox = ctk.CTkCheckBox(
            parent,
            text="Case Sensitive Matching",
            variable=self.blacklist_case_var,
            command=self.on_blacklist_case_toggle
        )
        case_checkbox.grid(row=2, column=0, columnspan=2, padx=10, pady=5, sticky="w")
        
        # Blacklist stats display
        stats_frame = ctk.CTkFrame(parent)
        stats_frame.grid(row=3, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        
        self.blacklist_stats_label = ctk.CTkLabel(
            stats_frame,
            text=f"📊 {blacklist_stats['total_tags']} blacklisted tags ({blacklist_stats['tag_groups']} groups)",
            font=ctk.CTkFont(size=12)
        )
        self.blacklist_stats_label.grid(row=0, column=0, padx=10, pady=5, sticky="w")
        
        # Tag management section
        tag_frame = ctk.CTkFrame(parent)
        tag_frame.grid(row=4, column=0, columnspan=2, padx=10, pady=10, sticky="ew")
        tag_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(tag_frame, text="Add Tag:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=10, pady=5, sticky="w")
        
        self.blacklist_tag_entry = ctk.CTkEntry(tag_frame, placeholder_text="Enter tag to blacklist...")
        self.blacklist_tag_entry.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        self.blacklist_tag_entry.bind("<Return>", self.on_add_blacklist_tag)
        
        add_tag_btn = ctk.CTkButton(tag_frame, text="Add", command=self.on_add_blacklist_tag, width=60)
        add_tag_btn.grid(row=0, column=2, padx=5, pady=5)
        
        # Blacklist management buttons
        button_frame = ctk.CTkFrame(parent)
        button_frame.grid(row=5, column=0, columnspan=2, padx=10, pady=10)
        
        view_btn = ctk.CTkButton(button_frame, text="📋 View Blacklist", command=self.show_blacklist_viewer)
        view_btn.grid(row=0, column=0, padx=5)
        
        edit_btn = ctk.CTkButton(button_frame, text="📝 Edit File", command=self.edit_blacklist_file)
        edit_btn.grid(row=0, column=1, padx=5)
        
        import_btn = ctk.CTkButton(button_frame, text="📥 Import", command=self.import_blacklist)
        import_btn.grid(row=0, column=2, padx=5)
        
        export_btn = ctk.CTkButton(button_frame, text="📤 Export", command=self.export_blacklist)
        export_btn.grid(row=0, column=3, padx=5)
    
    def create_interface_settings(self, parent):
        self.confirm_exit_var = ctk.BooleanVar(value=self.settings["confirm_exit"])
        confirm_checkbox = ctk.CTkCheckBox(parent, text="Confirm before exit", 
                       variable=self.confirm_exit_var)
        confirm_checkbox.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="w")
        
        ctk.CTkLabel(parent, text="History Limit:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.history_limit_var = ctk.StringVar(value=str(self.settings["download_history_limit"]))
        history_entry = ctk.CTkEntry(parent, textvariable=self.history_limit_var, width=100)
        history_entry.grid(row=2, column=1, sticky="w", padx=10, pady=5)
        
        ctk.CTkLabel(parent, text="Gallery Image Limit:").grid(row=3, column=0, padx=10, pady=5, sticky="w")
        self.gallery_limit_var = ctk.StringVar(value=str(self.settings["gallery_image_limit"]))
        gallery_entry = ctk.CTkEntry(parent, textvariable=self.gallery_limit_var, width=100)
        gallery_entry.grid(row=3, column=1, sticky="w", padx=10, pady=5)
        
        # Add tooltip for gallery limit
        gallery_tip = ctk.CTkLabel(parent, text="(1-2000, >500 uses pagination)", 
                                  font=("Arial", 10), text_color="gray")
        gallery_tip.grid(row=3, column=2, padx=5, pady=5, sticky="w")
        
        # Gallery pagination settings
        ctk.CTkLabel(parent, text="Images per page:").grid(row=4, column=0, padx=10, pady=5, sticky="w")
        self.gallery_page_size_var = ctk.StringVar(value=str(self.settings.get("gallery_page_size", 200)))
        page_size_entry = ctk.CTkEntry(parent, textvariable=self.gallery_page_size_var, width=100)
        page_size_entry.grid(row=4, column=1, sticky="w", padx=10, pady=5)
        
        page_tip = ctk.CTkLabel(parent, text="(50-500, for large galleries)", 
                               font=("Arial", 10), text_color="gray")
        page_tip.grid(row=4, column=2, padx=5, pady=5, sticky="w")
        
        # Performance Settings Section
        perf_frame = ctk.CTkFrame(parent)
        perf_frame.grid(row=5, column=0, columnspan=2, padx=10, pady=10, sticky="ew")
        
        ctk.CTkLabel(perf_frame, text="Performance Settings", 
                    font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, columnspan=2, padx=10, pady=5)
        
        ctk.CTkLabel(perf_frame, text="Disk Cache Size (MB):").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.cache_size_var = ctk.StringVar(value=str(self.settings["thumbnail_cache_size"]))
        cache_entry = ctk.CTkEntry(perf_frame, textvariable=self.cache_size_var, width=100)
        cache_entry.grid(row=1, column=1, sticky="w", padx=10, pady=5)
        
        ctk.CTkLabel(perf_frame, text="Thumbnail Workers:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.workers_var = ctk.StringVar(value=str(self.settings["thumbnail_workers"]))
        workers_entry = ctk.CTkEntry(perf_frame, textvariable=self.workers_var, width=100)
        workers_entry.grid(row=2, column=1, sticky="w", padx=10, pady=5)
        
        ctk.CTkLabel(perf_frame, text="Gallery Batch Size:").grid(row=3, column=0, padx=10, pady=5, sticky="w")
        self.batch_size_var = ctk.StringVar(value=str(self.settings["gallery_batch_size"]))
        batch_entry = ctk.CTkEntry(perf_frame, textvariable=self.batch_size_var, width=100)
        batch_entry.grid(row=3, column=1, sticky="w", padx=10, pady=5)
        
        # Cache management buttons
        cache_btn_frame = ctk.CTkFrame(perf_frame)
        cache_btn_frame.grid(row=4, column=0, columnspan=2, pady=10)
        
        clear_cache_btn = ctk.CTkButton(cache_btn_frame, text="Clear Cache", 
                                       command=self.clear_thumbnail_cache)
        clear_cache_btn.grid(row=0, column=0, padx=5)
        
        cache_stats_btn = ctk.CTkButton(cache_btn_frame, text="Cache Stats", 
                                       command=self.show_cache_stats)
        cache_stats_btn.grid(row=0, column=1, padx=5)
        
        optimize_cache_btn = ctk.CTkButton(cache_btn_frame, text="Optimize Cache", 
                                          command=self.optimize_cache)
        optimize_cache_btn.grid(row=0, column=2, padx=5)
    
    def create_advanced_settings(self, parent):
        button_frame = ctk.CTkFrame(parent)
        button_frame.grid(row=1, column=0, columnspan=2, pady=10)
        
        save_btn = ctk.CTkButton(button_frame, text="💾 Save Settings", command=self.save_all_settings)
        save_btn.grid(row=0, column=0, padx=10)
        
        reset_btn = ctk.CTkButton(button_frame, text="🔄 Reset to Defaults", command=self.reset_settings)
        reset_btn.grid(row=0, column=1, padx=10)
        
        export_settings_btn = ctk.CTkButton(button_frame, text="📤 Export Settings", command=self.export_settings)
        export_settings_btn.grid(row=0, column=2, padx=10)
        
        import_settings_btn = ctk.CTkButton(button_frame, text="📥 Import Settings", command=self.import_settings)
        import_settings_btn.grid(row=0, column=3, padx=10)
    
    def create_status_bar(self):
        self.status_frame = ctk.CTkFrame(self.root, height=30)
        self.status_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        self.status_frame.grid_columnconfigure(0, weight=1)
        
        self.status_label = ctk.CTkLabel(self.status_frame, text="Ready")
        self.status_label.grid(row=0, column=0, padx=10, sticky="w")
        
        # Connection indicator
        self.connection_label = ctk.CTkLabel(self.status_frame, text="🟢 Online")
        self.connection_label.grid(row=0, column=1, padx=10)
    
    # Event handlers and methods
    def on_booru_change(self, value):
        """Handle booru selection change"""
        self.settings["booru_type"] = value
        self.update_status(f"Selected booru: {value}")
        
        # Test connection to selected booru
        self.test_booru_connection(value)
    
    def test_booru_connection(self, booru_type):
        """Test connection to selected booru"""
        def test_connection():
            try:
                if booru_type in BOORU_APIS:
                    # Try a simple test request
                    api_info = BOORU_APIS[booru_type]
                    test_url = api_info.get('url', '')
                    
                    if test_url:
                        response = requests.head(test_url, timeout=5)
                        if response.status_code < 400:
                            self._safe_update_connection("🟢 Online", f"🌐 Connection to {booru_type} OK")
                        else:
                            self._safe_update_connection("🟡 Limited", f"⚠️ {booru_type} connection issues")
                    else:
                        self._safe_update_connection("🔴 Unknown")
                else:
                    self._safe_update_connection("🔴 Unknown")
            except Exception as e:
                self._safe_update_connection("🔴 Offline", f"❌ Connection test failed: {e}")
        
        # Run connection test in background
        threading.Thread(target=test_connection, daemon=True).start()
    
    def toggle_theme(self):
        """Toggle between dark and light themes"""
        if self.theme_switch.get() == "dark":
            ctk.set_appearance_mode("dark")
            self.settings["theme"] = "dark"
        else:
            ctk.set_appearance_mode("light")
            self.settings["theme"] = "light"
        self.save_settings()
    
    def quick_download(self, event=None):
        """Handle quick download"""
        tags = self.tag_entry.get().strip()
        # Allow empty tags to download recent images without filtering
        # if not tags:
        #     messagebox.showwarning("Warning", "Please enter at least one tag")
        #     return
        
        # Get and validate limit
        limit = self.validate_int_entry(self.limit_var.get(), default=10, min_val=1, max_val=1000)
        if limit != int(self.limit_var.get() or "10"):
            self.limit_var.set(str(limit))  # Update UI if value was corrected
        
        # Disable download button during download
        self.quick_dl_btn.configure(state="disabled", text="Downloading...")
        
        # Start download in separate thread
        self.download_thread = threading.Thread(
            target=self._perform_download,
            args=(self.booru_var.get(), tags, limit, "quick"),
            daemon=True
        )
        self.download_thread.start()
    
    def _perform_download(self, booru_type, tags, limit, download_type="quick"):
        """Perform the actual download in a separate thread"""
        try:
            self.is_downloading = True
            # Create descriptive download message
            tag_description = tags if tags else "recent images (no tags)"
            self.log_message(f"🚀 Starting {download_type} download: {tag_description} from {booru_type}")
            self.update_status(f"Starting download from {booru_type}...")
            
            # Update progress to show starting
            self._safe_update_progress(0, "Initializing download...")
            
            # Create progress callback function
            def progress_callback(progress_value):
                """Update progress bar from download thread"""
                if 0 <= progress_value <= 1:
                    downloaded_count = int(progress_value * limit)
                    progress_text = f"Downloaded: {downloaded_count}/{limit} images ({progress_value:.1%})"
                    # Schedule GUI updates on main thread safely
                    self._safe_update_progress(progress_value, progress_text)
            
            # Load user settings and set up download
            # Import from parent directory (rulescrape.py)
            import sys
            import os
            sys.path.append(os.path.dirname(os.path.dirname(__file__)))
            from rulescrape import load_user_settings
            from .dupe_check import get_dupe_checker
            from .download import DownloadManager
            
            user_settings = load_user_settings()
            output_dir = os.path.join(user_settings.get('output_dir', 'images'), booru_type)
            os.makedirs(output_dir, exist_ok=True)
            
            # Get organization method from user settings
            org_method = user_settings.get('org_method', 'By extension and first tag')
            
            # Initialize duplication checker and scan existing images
            dupe_checker = get_dupe_checker(user_settings.get('output_dir', 'images'))
            dupe_checker.reset_duplicate_count()
            scanned_count = dupe_checker.scan_existing_images()
            
            # Create download manager instance
            self.current_download_manager = DownloadManager(
                booru_type=booru_type,
                tag=tags,
                limit=limit,
                output_dir=output_dir,
                org_method=org_method,
                dupe_checker=dupe_checker,
                multithread=self.settings.get('multithread', True),
                max_workers=self.settings.get('max_workers', 4),
                progress_callback=progress_callback
            )
            
            # Run the download
            success = self.current_download_manager.run_download()
            
            if success:
                self.log_message(f"✅ Download completed successfully")
                downloaded_count = int(self.progress_var.get() * limit)  # Use actual progress
                self.update_status("Download completed successfully")
            else:
                if self.current_download_manager and self.current_download_manager.is_cancelled():
                    self.log_message(f"⏹️ Download was cancelled")
                    self.update_status("Download cancelled")
                else:
                    self.log_message(f"❌ Download failed or was interrupted")
                    self.update_status("Download failed")
                downloaded_count = 0
            
            # Ensure progress shows completion
            final_text = f"Completed: {downloaded_count} images" if success else ("Cancelled" if self.current_download_manager and self.current_download_manager.is_cancelled() else "Download failed")
            self._safe_update_progress(1.0 if success else 0.0, final_text)
            
            # Add to history
            history_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "booru": booru_type,
                "tags": tags if tags else "(no tags - recent images)",
                "count": downloaded_count,
                "status": "Completed" if success else ("Cancelled" if self.current_download_manager and self.current_download_manager.is_cancelled() else "Failed")
            }
            self.download_history.append(history_entry)
            
            # Keep history within limit
            if len(self.download_history) > self.settings["download_history_limit"]:
                self.download_history = self.download_history[-self.settings["download_history_limit"]:]
            
            # Save history and refresh display
            self.save_history()
            self._safe_refresh_history()
            
            self.log_message(f"✅ Download session completed")
            
        except Exception as e:
            self.log_message(f"❌ Download error: {str(e)}")
            self.update_status(f"Download error: {str(e)}")
            
        finally:
            self.is_downloading = False
            self.current_download_manager = None
            self.download_thread = None
            # Re-enable download button on main thread
            self.root.after(0, lambda: self.quick_dl_btn.configure(state="normal", text="🚀 Quick Download"))
            self.root.after(0, lambda: self.download_btn.configure(state="normal", text="🚀 Start Download"))
            self.root.after(0, lambda: self.pause_btn.configure(state="disabled", text="⏸ Pause"))
            self.root.after(0, lambda: self.stop_btn.configure(state="disabled", text="⏹ Stop"))
    
    def start_advanced_download(self):
        """Start advanced download with all options"""
        tags = self.advanced_tags.get("1.0", "end").strip()
        # Remove placeholder text if present
        if tags == "Enter tags separated by spaces (leave empty for recent images)...":
            tags = ""
        # Allow empty tags to download recent images without filtering
        # if not tags:
        #     messagebox.showwarning("Warning", "Please enter at least one tag")
        #     return
        
        if self.is_downloading:
            messagebox.showwarning("Warning", "A download is already in progress")
            return
        
        # Get and validate limit from advanced settings
        limit = self.validate_int_entry(self.advanced_limit_var.get(), default=20, min_val=1, max_val=1000)
        if limit != int(self.advanced_limit_var.get() or "20"):
            self.advanced_limit_var.set(str(limit))  # Update UI if value was corrected
        
        # Disable download buttons
        self.download_btn.configure(state="disabled", text="Downloading...")
        self.pause_btn.configure(state="normal")
        self.stop_btn.configure(state="normal")
        
        # Start download in separate thread
        self.download_thread = threading.Thread(
            target=self._perform_download,
            args=(self.booru_var.get(), tags, limit, "advanced"),
            daemon=True
        )
        self.download_thread.start()
    
    def pause_download(self):
        """Pause current download"""
        if self.is_downloading and self.current_download_manager:
            if self.current_download_manager.is_paused():
                # Resume download
                self.current_download_manager.resume()
                self.log_message("▶️ Download resumed")
                self.update_status("Download resumed")
                self.pause_btn.configure(text="⏸ Pause")
                self.download_btn.configure(state="disabled", text="Downloading...")
            else:
                # Pause download
                self.current_download_manager.pause()
                self.log_message("⏸️ Download paused")
                self.update_status("Download paused")
                self.pause_btn.configure(text="▶ Resume")
                self.download_btn.configure(state="disabled", text="Paused...")
        else:
            self.log_message("⏸️ No active download to pause")
    
    def stop_download(self):
        """Stop current download"""
        if self.is_downloading and self.current_download_manager:
            self.current_download_manager.cancel()
            self.log_message("⏹️ Download stop requested...")
            self.update_status("Stopping download...")
            self.stop_btn.configure(state="disabled", text="Stopping...")
            self.pause_btn.configure(state="disabled")
        else:
            self.log_message("⏹️ No active download to stop")
    
    def on_extension_filter_change(self, value):
        """Handle extension filter change"""
        self.settings["gallery_extension_filter"] = value
        self.save_settings()
        
        # Add a small delay to prevent rapid successive calls
        if hasattr(self, '_filter_change_after_id'):
            try:
                self.root.after_cancel(self._filter_change_after_id)
            except:
                pass
        
        # Schedule refresh with a small delay to debounce rapid changes
        self._filter_change_after_id = self.root.after(100, self._delayed_refresh_gallery)
    
    def _delayed_refresh_gallery(self):
        """Delayed gallery refresh to debounce rapid filter changes"""
        try:
            self.refresh_gallery()
        except Exception as e:
            self.log_message(f"❌ Error refreshing gallery: {e}")
    
    def get_filtered_extensions(self):
        """Get file extensions based on current filter setting"""
        filter_value = self.extension_filter_var.get()
        
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
        video_extensions = {'.mp4', '.webm'}
        
        if filter_value == "All":
            return image_extensions | video_extensions
        elif filter_value == "Images":
            return image_extensions
        elif filter_value == "Videos":
            return video_extensions
        elif filter_value == ".jpg/.jpeg":
            return {'.jpg', '.jpeg'}
        elif filter_value == ".png":
            return {'.png'}
        elif filter_value == ".gif":
            return {'.gif'}
        elif filter_value == ".bmp":
            return {'.bmp'}
        elif filter_value == ".webp":
            return {'.webp'}
        elif filter_value == ".mp4":
            return {'.mp4'}
        elif filter_value == ".webm":
            return {'.webm'}
        else:
            # Default to all if unknown filter
            return image_extensions | video_extensions

    def refresh_gallery(self):
        """Optimized gallery refresh with multithreaded thumbnail loading"""
        # Prevent concurrent refresh operations
        if hasattr(self, '_refreshing_gallery') and self._refreshing_gallery:
            self.log_message("⚠️ Gallery refresh already in progress, skipping...")
            return
        
        self._refreshing_gallery = True
        
        # Stop any current loading process immediately
        if hasattr(self, 'gallery_loader'):
            self.gallery_loader.stop()
        
        # Only stop animations if there are active ones
        if hasattr(self, 'animation_manager') and self.animation_manager.active_animations:
            self.animation_manager.stop_all_animations()
        
        # Clear existing images immediately
        for widget in self.gallery_scroll.winfo_children():
            widget.destroy()
        
        # Scroll to top when refreshing gallery (e.g., when filter changes)
        self.root.after(50, self._scroll_gallery_to_top)  # Small delay to ensure widgets are cleared
        
        # Update status immediately
        self.update_status("Scanning media files...")
        
        # Run the heavy file scanning in a background thread
        def scan_and_load():
            try:
                self._scan_and_load_gallery()
            except KeyboardInterrupt:
                self.root.after(0, lambda: self.log_message("⚠️ Gallery refresh interrupted by user"))
                self.root.after(0, lambda: self.update_status("Ready"))
            except Exception as e:
                self.root.after(0, lambda: self.log_message(f"❌ Error in gallery refresh: {e}"))
                self.root.after(0, lambda: self.update_status("Ready"))
            finally:
                # Always reset the refreshing flag on main thread
                self.root.after(0, lambda: setattr(self, '_refreshing_gallery', False))
        
        # Start background thread
        import threading
        threading.Thread(target=scan_and_load, daemon=True).start()
    
    def _scan_and_load_gallery(self):
        """Internal method to scan files and load gallery (runs in background thread)"""
        # Load media from output directory
        output_path = Path(self.settings["output_dir"])
        if not output_path.exists():
            self.root.after(0, lambda: self.log_message(f"📁 Output directory does not exist: {output_path}"))
            self.root.after(0, lambda: self.update_status("Ready"))
            return
        
        # Enhanced file extensions - use filtered extensions
        all_extensions = self.get_filtered_extensions()
        
        media_files = []
        # Simplified directory scanning with fallback
        executor = None
        try:
            # Use concurrent scanning for large directories with proper interruption handling
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
            future_to_ext = {
                executor.submit(list, output_path.rglob(f"*{ext}")): ext
                for ext in all_extensions
            }
            
            try:
                for future in concurrent.futures.as_completed(future_to_ext, timeout=30):
                    try:
                        files = future.result(timeout=5)
                        media_files.extend(files)
                    except concurrent.futures.TimeoutError:
                        self.root.after(0, lambda: self.log_message(f"⏰ Timeout scanning for {future_to_ext[future]} files"))
                    except Exception as e:
                        self.root.after(0, lambda: self.log_message(f"❌ Error scanning for {future_to_ext[future]} files: {e}"))
            except (KeyboardInterrupt, concurrent.futures.TimeoutError):
                # If interrupted or timeout, cancel remaining futures and fall back to simple scanning
                self.root.after(0, lambda: self.log_message("⚠️ Concurrent scanning interrupted, falling back to simple scan..."))
                for future in future_to_ext:
                    future.cancel()
                # Fall back to simple directory scanning
                media_files = []
                for ext in all_extensions:
                    try:
                        media_files.extend(list(output_path.rglob(f"*{ext}")))
                    except Exception as e:
                        self.root.after(0, lambda: self.log_message(f"❌ Error in fallback scan for {ext}: {e}"))
                            
        except Exception as e:
            self.root.after(0, lambda: self.log_message(f"❌ Error scanning directory: {e}"))
            self.root.after(0, lambda: self.update_status("Ready"))
            return
        finally:
            # Shutdown executor without blocking
            if executor is not None:
                try:
                    executor.shutdown(wait=False)
                except Exception:
                    pass  # Ignore shutdown errors
        
        if not media_files:
            filter_text = self.extension_filter_var.get()
            def create_no_images_label():
                no_images_label = ctk.CTkLabel(
                    self.gallery_scroll, 
                    text=f"No {filter_text.lower()} files found in output directory"
                )
                no_images_label.grid(row=0, column=0, columnspan=3, padx=20, pady=20)
                self.update_status("Ready")
            self.root.after(0, create_no_images_label)
            return
        
        # Sort by modification time (newest first)
        media_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        # Get gallery image limit from settings
        gallery_limit = self.settings.get("gallery_image_limit", 50)
        self.all_media_files = media_files[:gallery_limit]  # Store all files for pagination
        
        # Update page size from settings
        self.page_size = self.settings.get("gallery_page_size", 200)
        
        # Check if we need pagination
        if len(self.all_media_files) > self.page_size:
            # Use pagination for large galleries
            self.total_pages = (len(self.all_media_files) + self.page_size - 1) // self.page_size
            self.current_page = 0
            def update_pagination():
                self._update_pagination_controls()
                self.log_message(f"📄 Gallery has {len(self.all_media_files)} {self.extension_filter_var.get().lower()} files, using {self.total_pages} pages ({self.page_size} per page)")
                # Load first page
                self._load_current_page()
            self.root.after(0, update_pagination)
        else:
            # Small gallery, load all at once (traditional method)
            self.total_pages = 1
            self.current_page = 0
            def load_gallery():
                self._update_pagination_controls()
                # Store total for progress tracking
                self.gallery_total_files = len(self.all_media_files)
                # Use traditional loading for smaller galleries
                self.log_message(f"🖼️ Loading {len(self.all_media_files)} {self.extension_filter_var.get().lower()} files to gallery using disk cache...")
                self.update_status(f"Loading thumbnails: 0/{len(self.all_media_files)}")
                # Use progressive gallery loader for better performance
                self.gallery_loader.load_gallery_progressive(self.all_media_files, len(self.all_media_files))
                # Additional scroll-to-top after a short delay to ensure it works
                self.root.after(200, self._scroll_gallery_to_top)
            self.root.after(0, load_gallery)
    
    def create_media_frame_optimized(self, media_path: Path, thumbnail, row: int, col: int):
        """Create media frame with pre-generated thumbnail (optimized version)"""
        try:
            # Create media frame
            media_frame = ctk.CTkFrame(self.gallery_scroll)
            media_frame.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
            
            # Media label with pre-generated thumbnail
            media_label = tk.Label(media_frame, image=thumbnail, bg='gray20')
            media_label.image = thumbnail  # Keep reference
            media_label.grid(row=0, column=0, padx=5, pady=5)
            
            # Check if file is animated and add preview functionality
            is_animated = AnimatedPreview.is_animated_file(media_path)
            
            if is_animated and self.settings.get("animated_previews", True):
                # Add animation indicator overlay
                indicator_frame = tk.Frame(media_label, bg='gray20')
                indicator_frame.place(relx=0.05, rely=0.05)
                
                # Use emoji or text indicator
                if media_path.suffix.lower() == '.gif':
                    indicator_text = "🎞️"  # GIF indicator
                else:
                    indicator_text = "▶️"  # Video indicator
                    
                indicator_label = tk.Label(indicator_frame, text=indicator_text, 
                                         font=('Arial', 10), fg='white', bg='black',
                                         padx=2, pady=1)
                indicator_label.pack()
                
                # Bind scroll events to indicator elements
                self._bind_scroll_events(indicator_frame)
                self._bind_scroll_events(indicator_label)
                
                # Bind hover events for animation
                media_label.bind("<Enter>", lambda e: self.animation_manager.start_animation(
                    media_label, media_path, thumbnail))
                media_label.bind("<Leave>", lambda e: self.animation_manager.stop_animation(media_label))
            elif is_animated:
                # Show indicator but no animation (if disabled)
                indicator_frame = tk.Frame(media_label, bg='gray20')
                indicator_frame.place(relx=0.05, rely=0.05)
                
                indicator_text = "🎞️" if media_path.suffix.lower() == '.gif' else "▶️"
                indicator_label = tk.Label(indicator_frame, text=indicator_text, 
                                         font=('Arial', 10), fg='gray', bg='black',
                                         padx=2, pady=1)
                indicator_label.pack()
                
                # Bind scroll events to indicator elements
                self._bind_scroll_events(indicator_frame)
                self._bind_scroll_events(indicator_label)
            
            # Filename label
            display_name = media_path.name
            if len(display_name) > 25:
                display_name = display_name[:22] + "..."
            name_label = ctk.CTkLabel(media_frame, text=display_name)
            name_label.grid(row=1, column=0, padx=5, pady=(0, 5))
            
            # Bind click event to open media
            media_label.bind("<Button-1>", lambda e, path=media_path: self.open_image(path))
            
            # Bind scroll events to media label for consistent scrolling
            self._bind_scroll_events(media_label)
            # Also bind to media frame and name label for complete coverage
            self._bind_scroll_events(media_frame)
            self._bind_scroll_events(name_label)
            
        except Exception as e:
            self.log_message(f"❌ Error creating media frame for {media_path.name}: {e}")
    
    def create_media_frame(self, media_path, row, col):
        """Create enhanced media frame with animation support (legacy method for compatibility)"""
        # Load static thumbnail first
        if media_path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}:
            # Regular image
            img = Image.open(media_path)
            img.thumbnail((200, 200), Image.Resampling.LANCZOS)
            static_photo = ImageTk.PhotoImage(img)
        elif media_path.suffix.lower() == '.gif':
            # GIF - load first frame as static
            img = Image.open(media_path)
            img.thumbnail((200, 200), Image.Resampling.LANCZOS)
            static_photo = ImageTk.PhotoImage(img)
        elif media_path.suffix.lower() in {'.mp4', '.webm'}:
            # Video - create thumbnail or use placeholder
            static_photo = AnimatedPreview.create_video_thumbnail(media_path, (200, 200))
            if not static_photo:
                # Create placeholder for video
                placeholder = Image.new('RGB', (200, 150), color='gray')
                static_photo = ImageTk.PhotoImage(placeholder)
        else:
            # Fallback placeholder
            placeholder = Image.new('RGB', (200, 150), color='lightgray')
            static_photo = ImageTk.PhotoImage(placeholder)
        
        # Create media frame
        media_frame = ctk.CTkFrame(self.gallery_scroll)
        media_frame.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
        
        # Media label
        media_label = tk.Label(media_frame, image=static_photo, bg='gray20')
        media_label.image = static_photo  # Keep reference
        media_label.grid(row=0, column=0, padx=5, pady=5)
        
        # Check if file is animated and add preview functionality
        is_animated = AnimatedPreview.is_animated_file(media_path)
        
        if is_animated and self.settings.get("animated_previews", True):
            # Add animation indicator overlay
            indicator_frame = tk.Frame(media_label, bg='gray20')
            indicator_frame.place(relx=0.05, rely=0.05)
            
            # Use emoji or text indicator
            if media_path.suffix.lower() == '.gif':
                indicator_text = "🎞️"  # GIF indicator
            else:
                indicator_text = "▶️"  # Video indicator
                
            indicator_label = tk.Label(indicator_frame, text=indicator_text, 
                                     font=('Arial', 10), fg='white', bg='black',
                                     padx=2, pady=1)
            indicator_label.pack()
            
            # Bind scroll events to indicator elements
            self._bind_scroll_events(indicator_frame)
            self._bind_scroll_events(indicator_label)
            
            # Bind hover events for animation
            media_label.bind("<Enter>", lambda e: self.animation_manager.start_animation(
                media_label, media_path, static_photo))
            media_label.bind("<Leave>", lambda e: self.animation_manager.stop_animation(media_label))
        elif is_animated:
            # Show indicator but no animation (if disabled)
            indicator_frame = tk.Frame(media_label, bg='gray20')
            indicator_frame.place(relx=0.05, rely=0.05)
            
            indicator_text = "🎞️" if media_path.suffix.lower() == '.gif' else "▶️"
            indicator_label = tk.Label(indicator_frame, text=indicator_text, 
                                     font=('Arial', 10), fg='gray', bg='black',
                                     padx=2, pady=1)
            indicator_label.pack()
            
            # Bind scroll events to indicator elements
            self._bind_scroll_events(indicator_frame)
            self._bind_scroll_events(indicator_label)
        
        # Filename label
        display_name = media_path.name
        if len(display_name) > 25:
            display_name = display_name[:22] + "..."
        name_label = ctk.CTkLabel(media_frame, text=display_name)
        name_label.grid(row=1, column=0, padx=5, pady=(0, 5))
        
        # Bind click event to open media
        media_label.bind("<Button-1>", lambda e, path=media_path: self.open_image(path))
        
        # Bind scroll events to media label for consistent scrolling
        self._bind_scroll_events(media_label)
        # Also bind to media frame for complete coverage
        self._bind_scroll_events(media_frame)
    
    def open_image(self, path):
        """Open image in default viewer"""
        try:
            path_str = str(path)
            if os.name == 'nt':  # Windows
                os.startfile(path_str)
            elif os.name == 'posix':  # macOS and Linux
                if sys.platform == 'darwin':  # macOS
                    os.system(f'open "{path_str}"')
                else:  # Linux
                    os.system(f'xdg-open "{path_str}"')
            self.log_message(f"📱 Opened image: {path.name}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not open image: {e}")
            self.log_message(f"❌ Failed to open image: {e}")
    
    def open_images_folder(self):
        """Open the images folder in file explorer"""
        output_path = Path(self.settings["output_dir"])
        if output_path.exists():
            self.open_image(output_path)
            self.log_message(f"📁 Opened folder: {output_path}")
        else:
            messagebox.showwarning("Warning", f"Output directory does not exist: {output_path}")
            self.log_message(f"❌ Output directory not found: {output_path}")
    
    def clear_history(self):
        """Clear download history"""
        if messagebox.askyesno("Confirm", "Are you sure you want to clear the download history?"):
            self.download_history.clear()
            self.save_history()
            self.refresh_history()
            self.log_message("🗑️ Download history cleared")
    
    def export_history(self):
        """Export download history to file"""
        if not self.download_history:
            messagebox.showinfo("Info", "No history to export")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filename:
            try:
                with open(filename, 'w') as f:
                    json.dump(self.download_history, f, indent=2, default=str)
                messagebox.showinfo("Success", f"History exported to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Could not export history: {e}")
    
    def refresh_history(self):
        """Refresh the history display"""
        # Clear existing items
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        
        # Add history items
        for entry in self.download_history:
            self.history_tree.insert("", "end", values=(
                entry.get("timestamp", ""),
                entry.get("booru", ""),
                entry.get("tags", ""),
                entry.get("count", 0),
                entry.get("status", "")
            ))
    
    def browse_output_dir(self):
        """Browse for output directory"""
        directory = filedialog.askdirectory(initialdir=self.settings["output_dir"])
        if directory:
            self.output_dir_var.set(directory)
            self.settings["output_dir"] = directory
    
    def save_all_settings(self):
        """Save all settings"""
        try:
            # Update settings from UI with safe integer conversion
            history_limit = self.validate_int_entry(self.history_limit_var.get(), default=100, min_val=1, max_val=10000)
            if history_limit != int(self.history_limit_var.get() or "100"):
                self.history_limit_var.set(str(history_limit))  # Update UI if value was corrected
            
            gallery_limit = self.validate_int_entry(self.gallery_limit_var.get(), default=50, min_val=1, max_val=2000)
            if gallery_limit != int(self.gallery_limit_var.get() or "50"):
                self.gallery_limit_var.set(str(gallery_limit))  # Update UI if value was corrected
            
            # Show performance warning for very large galleries
            if gallery_limit > 1000 and not hasattr(self, '_large_gallery_warned'):
                self.log_message("⚠️ Large gallery size may impact performance. Consider using batches or filtering.")
                self._large_gallery_warned = True
            
            # Gallery pagination settings
            page_size = self.validate_int_entry(self.gallery_page_size_var.get(), default=200, min_val=50, max_val=500)
            if page_size != int(self.gallery_page_size_var.get() or "200"):
                self.gallery_page_size_var.set(str(page_size))  # Update UI if value was corrected
            
            # Performance settings validation
            cache_size = self.validate_int_entry(self.cache_size_var.get(), default=200, min_val=10, max_val=1000)
            if cache_size != int(self.cache_size_var.get() or "200"):
                self.cache_size_var.set(str(cache_size))
            
            workers = self.validate_int_entry(self.workers_var.get(), default=8, min_val=1, max_val=16)
            if workers != int(self.workers_var.get() or "8"):
                self.workers_var.set(str(workers))
            
            batch_size = self.validate_int_entry(self.batch_size_var.get(), default=12, min_val=3, max_val=30)
            if batch_size != int(self.batch_size_var.get() or "12"):
                self.batch_size_var.set(str(batch_size))
            
            self.settings.update({
                "booru_type": self.booru_var.get(),
                "output_dir": self.output_dir_var.get(),
                "org_method": self.org_method_var.get(),
                "max_workers": self.max_workers_var.get(),
                "confirm_exit": self.confirm_exit_var.get(),
                "download_history_limit": history_limit,
                "gallery_image_limit": gallery_limit,
                "gallery_page_size": page_size,
                "multithread": self.multithread_var.get() if hasattr(self, 'multithread_var') else True,
                "anti_ai": self.anti_ai_var.get() if hasattr(self, 'anti_ai_var') else False,
                # Performance settings
                "thumbnail_cache_size": cache_size,
                "thumbnail_workers": workers,
                "gallery_batch_size": batch_size,
            })
            
            # Update thumbnail cache settings if they changed
            if hasattr(self, 'thumbnail_cache'):
                current_stats = self.thumbnail_cache.get_cache_stats()
                if (current_stats['max_size_mb'] != cache_size or 
                    current_stats['workers'] != workers):
                    # Recreate cache with new settings
                    cache_dir = os.path.join(self.settings.get("output_dir", "images"), "..", "cache", "thumbnails")
                    self.thumbnail_cache = DiskThumbnailCache(cache_dir, cache_size, workers)
                    self.log_message(f"🔧 Updated thumbnail cache: {cache_size}MB disk cache, {workers} workers")
            
            # Update gallery loader batch size
            if hasattr(self, 'gallery_loader'):
                self.gallery_loader.batch_size = batch_size
            
            self.save_settings()
            messagebox.showinfo("Success", "Settings saved successfully!")
            self.log_message("💾 Settings saved successfully")
        except Exception as e:
            messagebox.showerror("Error", f"Could not save settings: {e}")
    
    def reset_settings(self):
        """Reset settings to defaults"""
        if messagebox.askyesno("Confirm", "Reset all settings to defaults?"):
            try:
                # Reset to default values
                default_settings = {
                    "theme": "dark",
                    "booru_type": "rule34",
                    "output_dir": "images",
                    "org_method": "By extension and first tag",
                    "max_workers": 4,
                    "confirm_exit": True,
                    "download_history_limit": 100,
                    "gallery_image_limit": 50,
                    # Performance settings
                    "thumbnail_cache_size": 500,
                    "thumbnail_workers": min(8, (os.cpu_count() or 1) + 4),
                    "gallery_batch_size": 12
                }
                
                self.settings.update(default_settings)
                
                # Update UI elements
                self.booru_var.set(default_settings["booru_type"])
                self.output_dir_var.set(default_settings["output_dir"])
                self.org_method_var.set(default_settings["org_method"])
                self.max_workers_var.set(default_settings["max_workers"])
                self.confirm_exit_var.set(default_settings["confirm_exit"])
                self.history_limit_var.set(str(default_settings["download_history_limit"]))
                self.gallery_limit_var.set(str(default_settings["gallery_image_limit"]))
                # Update performance settings UI
                self.cache_size_var.set(str(default_settings["thumbnail_cache_size"]))
                self.workers_var.set(str(default_settings["thumbnail_workers"]))
                self.batch_size_var.set(str(default_settings["gallery_batch_size"]))
                
                self.save_settings()
                messagebox.showinfo("Success", "Settings reset to defaults!")
                self.log_message("🔄 Settings reset to defaults")
            except Exception as e:
                messagebox.showerror("Error", f"Could not reset settings: {e}")
                self.log_message(f"❌ Error resetting settings: {e}")
    
    def export_settings(self):
        """Export settings to file"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filename:
            try:
                with open(filename, 'w') as f:
                    json.dump(self.settings, f, indent=2)
                messagebox.showinfo("Success", f"Settings exported to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Could not export settings: {e}")
    
    def import_settings(self):
        """Import settings from file"""
        filename = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filename:
            try:
                with open(filename, 'r') as f:
                    imported_settings = json.load(f)
                    self.settings.update(imported_settings)
                    self.save_settings()
                messagebox.showinfo("Success", "Settings imported successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Could not import settings: {e}")
    
    def clear_thumbnail_cache(self):
        """Clear the thumbnail cache"""
        if hasattr(self, 'thumbnail_cache'):
            self.thumbnail_cache.clear_cache()
            self.log_message("🗑️ Thumbnail cache cleared")
            messagebox.showinfo("Cache Cleared", "Thumbnail cache has been cleared successfully!")
        else:
            messagebox.showwarning("No Cache", "Thumbnail cache is not initialized")
    
    def optimize_cache(self):
        """Optimize the disk thumbnail cache"""
        if hasattr(self, 'thumbnail_cache'):
            self.thumbnail_cache.optimize_cache()
            self.log_message("🔧 Thumbnail cache optimized")
            messagebox.showinfo("Cache Optimized", "Thumbnail cache has been optimized successfully!")
        else:
            messagebox.showwarning("No Cache", "Thumbnail cache is not initialized")
    
    def show_cache_stats(self):
        """Show thumbnail cache statistics"""
        if hasattr(self, 'thumbnail_cache'):
            stats = self.thumbnail_cache.get_cache_stats()
            usage_percent = (stats['cache_size_mb'] / stats['max_size_mb'] * 100) if stats['max_size_mb'] > 0 else 0
            message = (
                f"Disk Thumbnail Cache Statistics:\n\n"
                f"Cached Items: {stats['cached_items']}\n"
                f"Cache Size: {stats['cache_size_mb']:.1f} MB\n"
                f"Max Cache Size: {stats['max_size_mb']:.0f} MB\n"
                f"Cache Directory: {stats['cache_dir']}\n"
                f"Worker Threads: {stats['workers']}\n"
                f"Cache Usage: {usage_percent:.1f}%"
            )
            messagebox.showinfo("Cache Statistics", message)
            self.log_message(f"📊 Disk cache stats: {stats['cached_items']} items, {stats['cache_size_mb']:.1f}MB used of {stats['max_size_mb']:.0f}MB")
        else:
            messagebox.showwarning("No Cache", "Thumbnail cache is not initialized")
    
    # Blacklist management methods
    def on_blacklist_toggle(self):
        """Handle blacklist enable/disable toggle"""
        if self.blacklist_enabled_var.get():
            self.blacklist_manager.enable_blacklist()
            self.log_message("✅ Blacklist filtering enabled")
        else:
            self.blacklist_manager.disable_blacklist()
            self.log_message("🚫 Blacklist filtering disabled")
        
        self.blacklist_manager.save_blacklist()
        self.update_blacklist_stats()
    
    def on_blacklist_case_toggle(self):
        """Handle case sensitivity toggle"""
        case_sensitive = self.blacklist_case_var.get()
        self.blacklist_manager.set_case_sensitive(case_sensitive)
        self.blacklist_manager.save_blacklist()
        self.log_message(f"🔤 Case sensitive matching: {'enabled' if case_sensitive else 'disabled'}")
        self.update_blacklist_stats()
    
    def on_add_blacklist_tag(self, event=None):
        """Add a tag to the blacklist"""
        tag = self.blacklist_tag_entry.get().strip()
        if not tag:
            return
        
        if self.blacklist_manager.add_tag(tag):
            self.blacklist_manager.save_blacklist()
            self.blacklist_tag_entry.delete(0, 'end')
            self.log_message(f"✅ Added tag to blacklist: {tag}")
            self.update_blacklist_stats()
        else:
            messagebox.showwarning("Warning", f"Tag '{tag}' is already in blacklist or invalid")
    
    def update_blacklist_stats(self):
        """Update blacklist statistics display"""
        stats = self.blacklist_manager.get_blacklist_stats()
        status = "Enabled" if stats['enabled'] else "Disabled"
        self.blacklist_stats_label.configure(
            text=f"📊 {stats['total_tags']} blacklisted tags ({stats['tag_groups']} groups) - {status}"
        )
    
    def show_blacklist_viewer(self):
        """Show blacklist viewer window"""
        BlacklistViewerWindow(self.root, self.blacklist_manager, self)
    
    def edit_blacklist_file(self):
        """Open blacklist file in default editor"""
        try:
            blacklist_file = self.blacklist_manager.blacklist_file
            if os.name == 'nt':  # Windows
                os.startfile(blacklist_file)
            elif os.name == 'posix':  # macOS and Linux
                if sys.platform == 'darwin':  # macOS
                    os.system(f'open "{blacklist_file}"')
                else:  # Linux
                    os.system(f'xdg-open "{blacklist_file}"')
            self.log_message(f"📝 Opened blacklist file: {blacklist_file}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not open blacklist file: {e}")
    
    def import_blacklist(self):
        """Import blacklist from file"""
        file_path = filedialog.askopenfilename(
            title="Import Blacklist",
            filetypes=[("JSON files", "*.json"), ("Text files", "*.txt"), ("All files", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            if file_path.endswith('.json'):
                # Import from JSON
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                imported_count = 0
                if 'tags' in data and isinstance(data['tags'], list):
                    for tag in data['tags']:
                        if self.blacklist_manager.add_tag(tag):
                            imported_count += 1
                
                if 'tag_groups' in data and isinstance(data['tag_groups'], dict):
                    for group_name, group_tags in data['tag_groups'].items():
                        if isinstance(group_tags, list):
                            self.blacklist_manager.add_tag_group(group_name, group_tags)
                            imported_count += len(group_tags)
            
            else:
                # Import from text file (one tag per line)
                with open(file_path, 'r', encoding='utf-8') as f:
                    imported_count = 0
                    for line in f:
                        tag = line.strip()
                        if tag and not tag.startswith('#'):  # Skip empty lines and comments
                            if self.blacklist_manager.add_tag(tag):
                                imported_count += 1
            
            self.blacklist_manager.save_blacklist()
            self.update_blacklist_stats()
            messagebox.showinfo("Success", f"Imported {imported_count} tags to blacklist")
            self.log_message(f"📥 Imported {imported_count} tags from {os.path.basename(file_path)}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Could not import blacklist: {e}")
    
    def export_blacklist(self):
        """Export blacklist to file"""
        file_path = filedialog.asksaveasfilename(
            title="Export Blacklist",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("Text files", "*.txt"), ("All files", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            if file_path.endswith('.json'):
                # Export as JSON
                stats = self.blacklist_manager.get_blacklist_stats()
                export_data = {
                    "description": "Exported blacklist from Rulescrape",
                    "exported_on": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "enabled": stats['enabled'],
                    "case_sensitive": stats['case_sensitive'],
                    "tags": sorted([tag for tag in self.blacklist_manager.get_blacklisted_tags() 
                                   if tag not in self.blacklist_manager._get_group_tags()]),
                    "tag_groups": self.blacklist_manager.get_tag_groups()
                }
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            else:
                # Export as text file
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("# Rulescrape Blacklist Export\n")
                    f.write(f"# Exported on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                    
                    tags = self.blacklist_manager.get_blacklisted_tags()
                    for tag in tags:
                        f.write(f"{tag}\n")
            
            messagebox.showinfo("Success", f"Exported blacklist to {os.path.basename(file_path)}")
            self.log_message(f"📤 Exported blacklist to {os.path.basename(file_path)}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Could not export blacklist: {e}")

    def show_downloads_tab(self):
        """Show downloads tab"""
        self.tabview.set("Downloads")
    
    def show_gallery_tab(self):
        """Show gallery tab"""
        self.tabview.set("Gallery")
        self.refresh_gallery()
    
    def show_history_tab(self):
        """Show history tab"""
        self.tabview.set("History")
        self.refresh_history()
    
    def show_settings_tab(self):
        """Show settings tab"""
        self.tabview.set("Settings")
    
    def on_tab_change(self):
        """Handle tab change events"""
        try:
            current_tab = self.tabview.get()
            if current_tab == "History":
                self.refresh_history()
            elif current_tab == "Gallery":
                self.refresh_gallery()
        except KeyboardInterrupt:
            # Handle keyboard interrupts gracefully during tab changes
            self.log_message("⚠️ Tab change interrupted, continuing...")
        except Exception as e:
            # Handle any other exceptions during tab changes
            self.log_message(f"❌ Error during tab change: {e}")
            import traceback
            traceback.print_exc()
    
    def log_message(self, message):
        """Add message to download log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        self.log_textbox.insert("end", log_entry)
        self.log_textbox.see("end")
    
    def update_status(self, message):
        """Update status bar"""
        self.status_label.configure(text=message)
    
    def _safe_update_progress(self, progress_value, progress_text):
        """Safely update progress bar with error handling"""
        if getattr(self, 'is_closing', False):
            return
            
        def update_progress():
            try:
                if not self.is_closing and self.root and self.root.winfo_exists():
                    self.progress_var.set(progress_value)
                    self.progress_label.configure(text=progress_text)
            except:
                pass  # Widget destroyed, ignore
        
        try:
            if self.root:
                self.root.after(0, update_progress)
        except:
            pass  # Root destroyed, ignore
    
    def _safe_update_status(self, message):
        """Safely update status with error handling"""
        if getattr(self, 'is_closing', False):
            return
            
        def update_status():
            try:
                if not self.is_closing and self.root and self.root.winfo_exists():
                    self.status_label.configure(text=message)
            except:
                pass  # Widget destroyed, ignore
        
        try:
            if self.root:
                self.root.after(0, update_status)
        except:
            pass  # Root destroyed, ignore
    
    def _safe_refresh_history(self):
        """Safely refresh history with error handling"""
        if getattr(self, 'is_closing', False):
            return
            
        def refresh_history():
            try:
                if not self.is_closing and self.root and self.root.winfo_exists():
                    self.refresh_history()
            except:
                pass  # Widget destroyed, ignore
        
        try:
            if self.root:
                self.root.after(0, refresh_history)
        except:
            pass  # Root destroyed, ignore
    
    def _safe_update_connection(self, status_text, log_message=None):
        """Safely update connection status with error handling"""
        if getattr(self, 'is_closing', False):
            return
            
        def update_connection():
            try:
                if not self.is_closing and self.root and self.root.winfo_exists():
                    self.connection_label.configure(text=status_text)
                    if log_message:
                        self.log_message(log_message)
            except:
                pass  # Widget destroyed, ignore
        
        try:
            if self.root:
                self.root.after(0, update_connection)
        except:
            pass  # Root destroyed, ignore
    
    def process_queue(self):
        """Process download queue - simplified for functional version"""
        # Check if GUI is shutting down or no longer valid
        if getattr(self, 'is_closing', False):
            return
            
        try:
            if not self.root or not self.root.winfo_exists():
                return
        except:
            return
        
        # This method now mainly handles UI updates
        # Actual downloads are handled by threading in the download methods
        
        # Check if we need to save settings periodically
        try:
            current_time = time.time()
            if not hasattr(self, '_last_save_time'):
                self._last_save_time = current_time
            
            # Auto-save settings every 5 minutes
            if current_time - self._last_save_time > 300:
                self.save_settings()
                self._last_save_time = current_time
        except Exception as e:
            pass  # Ignore save errors
        
        # Schedule next check only if not closing and root still exists
        if not getattr(self, 'is_closing', False):
            try:
                if self.root and self.root.winfo_exists():
                    self.root.after(5000, self.process_queue)  # Check every 5 seconds
            except:
                pass  # Widget destroyed, stop scheduling
    
    def on_closing(self):
        """Handle application closing"""
        global _error_queue_stopping
        
        # Set closing flags to prevent new scheduled callbacks
        self.is_closing = True
        _error_queue_stopping = True
        
        if self.is_downloading:
            if messagebox.askyesno("Download in Progress", 
                                 "A download is currently in progress. Stop download and exit?"):
                self.is_downloading = False
            else:
                # Reset flags if user cancels
                self.is_closing = False
                _error_queue_stopping = False
                return
        
        # Clean up animations before closing
        if hasattr(self, 'animation_manager'):
            self.animation_manager.stop_all_animations()
        
        # Clear preview cache to free memory
        PreviewCache.clear_cache()
        
        if self.settings["confirm_exit"]:
            if messagebox.askokcancel("Quit", "Do you want to quit Rulescrape?"):
                self.save_settings()
                self.log_message("👋 Goodbye!")
                
                # Final cleanup before destroying
                try:
                    # Cancel any remaining scheduled callbacks
                    # Note: Individual callbacks should handle their own cleanup
                    pass
                except:
                    pass
                
                self.root.destroy()
            else:
                # Reset flags if user cancels
                self.is_closing = False
                _error_queue_stopping = False
        else:
            self.save_settings()
            self.root.destroy()
    
    def run(self):
        """Start the application"""
        try:
            self.log_message("🚀 Starting Rulescrape GUI...")
            self.log_message(f"📁 Output directory: {self.settings['output_dir']}")
            self.log_message(f"🎯 Default booru: {self.settings['booru_type']}")
            self.log_message("✅ Ready for downloads!")
            
            self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
            self.root.mainloop()
        except Exception as e:
            print(f"Error starting application: {e}")
            messagebox.showerror("Startup Error", f"Could not start application: {e}")

# Additional utility classes

class BlacklistViewerWindow:
    """Window for viewing and managing blacklisted tags"""
    
    def __init__(self, parent, blacklist_manager, main_gui):
        self.blacklist_manager = blacklist_manager
        self.main_gui = main_gui
        self.group_names = []  # Initialize group names list for removal functionality
        
        self.window = ctk.CTkToplevel(parent)
        self.window.title("Blacklist Manager")
        self.window.geometry("600x500")
        self.window.transient(parent)
        
        self.create_interface()
        self.refresh_lists()
    
    def create_interface(self):
        """Create the blacklist viewer interface"""
        # Main frame
        main_frame = ctk.CTkFrame(self.window)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(1, weight=1)
        
        # Title
        title_label = ctk.CTkLabel(main_frame, text="🚫 Blacklist Manager", 
                                  font=ctk.CTkFont(size=18, weight="bold"))
        title_label.grid(row=0, column=0, pady=10)
        
        # Notebook for tabs
        notebook = ctk.CTkTabview(main_frame)
        notebook.grid(row=1, column=0, sticky="nsew", pady=10)
        
        # Individual tags tab
        tags_tab = notebook.add("Individual Tags")
        self.create_tags_tab(tags_tab)
        
        # Tag groups tab
        groups_tab = notebook.add("Tag Groups")
        self.create_groups_tab(groups_tab)
        
        # Control buttons
        button_frame = ctk.CTkFrame(main_frame)
        button_frame.grid(row=2, column=0, pady=10)
        
        refresh_btn = ctk.CTkButton(button_frame, text="🔄 Refresh", command=self.refresh_lists)
        refresh_btn.grid(row=0, column=0, padx=5)
        
        save_btn = ctk.CTkButton(button_frame, text="💾 Save", command=self.save_changes)
        save_btn.grid(row=0, column=1, padx=5)
        
        close_btn = ctk.CTkButton(button_frame, text="❌ Close", command=self.window.destroy)
        close_btn.grid(row=0, column=2, padx=5)
    
    def create_tags_tab(self, parent):
        """Create individual tags management tab"""
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)
        
        # Add tag section
        add_frame = ctk.CTkFrame(parent)
        add_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=5)
        add_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(add_frame, text="Add Tag:").grid(row=0, column=0, padx=10, pady=5)
        self.new_tag_entry = ctk.CTkEntry(add_frame, placeholder_text="Enter tag to blacklist...")
        self.new_tag_entry.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        self.new_tag_entry.bind("<Return>", self.add_individual_tag)
        
        add_btn = ctk.CTkButton(add_frame, text="Add", command=self.add_individual_tag, width=60)
        add_btn.grid(row=0, column=2, padx=5, pady=5)
        
        # Tags list
        list_frame = ctk.CTkFrame(parent)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)
        
        # Use Listbox for better performance with many items
        self.tags_listbox = tk.Listbox(list_frame, selectmode=tk.MULTIPLE)
        self.tags_listbox.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        # Scrollbar for tags list
        tags_scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tags_listbox.yview)
        tags_scrollbar.grid(row=0, column=1, sticky="ns", pady=5)
        self.tags_listbox.configure(yscrollcommand=tags_scrollbar.set)
        
        # Remove button
        remove_btn = ctk.CTkButton(list_frame, text="Remove Selected", 
                                  command=self.remove_selected_tags)
        remove_btn.grid(row=1, column=0, columnspan=2, pady=5)
    
    def create_groups_tab(self, parent):
        """Create tag groups management tab"""
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)
        
        # Add group section
        add_frame = ctk.CTkFrame(parent)
        add_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=5)
        add_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(add_frame, text="Group Name:").grid(row=0, column=0, padx=10, pady=5)
        self.group_name_entry = ctk.CTkEntry(add_frame, placeholder_text="Enter group name...")
        self.group_name_entry.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        
        ctk.CTkLabel(add_frame, text="Tags:").grid(row=1, column=0, padx=10, pady=5)
        self.group_tags_entry = ctk.CTkEntry(add_frame, placeholder_text="Enter tags separated by spaces...")
        self.group_tags_entry.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
        
        add_group_btn = ctk.CTkButton(add_frame, text="Add Group", command=self.add_tag_group, width=80)
        add_group_btn.grid(row=0, column=2, rowspan=2, padx=5, pady=5)
        
        # Groups display
        groups_frame = ctk.CTkFrame(parent)
        groups_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        groups_frame.grid_columnconfigure(0, weight=1)
        groups_frame.grid_rowconfigure(0, weight=1)
        
        # Use Listbox for better interaction with groups
        self.groups_listbox = tk.Listbox(groups_frame, selectmode=tk.MULTIPLE)
        self.groups_listbox.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        # Scrollbar for groups list
        groups_scrollbar = ttk.Scrollbar(groups_frame, orient="vertical", command=self.groups_listbox.yview)
        groups_scrollbar.grid(row=0, column=1, sticky="ns", pady=5)
        self.groups_listbox.configure(yscrollcommand=groups_scrollbar.set)
        
        # Remove group button
        remove_group_btn = ctk.CTkButton(groups_frame, text="Remove Selected Groups", 
                                        command=self.remove_selected_groups)
        remove_group_btn.grid(row=1, column=0, columnspan=2, pady=5)
    
    def refresh_lists(self):
        """Refresh the display of tags and groups"""
        # Refresh individual tags
        self.tags_listbox.delete(0, tk.END)
        individual_tags = sorted([tag for tag in self.blacklist_manager.get_blacklisted_tags() 
                                 if tag not in self.blacklist_manager._get_group_tags()])
        for tag in individual_tags:
            self.tags_listbox.insert(tk.END, tag)
        
        # Refresh tag groups
        self.groups_listbox.delete(0, tk.END)
        groups = self.blacklist_manager.get_tag_groups()
        if groups:
            for group_name, group_tags in sorted(groups.items()):
                # Display group with tag count for better readability
                group_display = f"📁 {group_name} ({len(group_tags)} tags)"
                self.groups_listbox.insert(tk.END, group_display)
        
        # Store group names for removal (without the display formatting)
        self.group_names = list(sorted(groups.keys())) if groups else []
    
    def add_individual_tag(self, event=None):
        """Add an individual tag to the blacklist"""
        tag = self.new_tag_entry.get().strip()
        if not tag:
            return
        
        if self.blacklist_manager.add_tag(tag):
            self.new_tag_entry.delete(0, tk.END)
            self.refresh_lists()
            self.main_gui.update_blacklist_stats()
        else:
            messagebox.showwarning("Warning", f"Tag '{tag}' is already in blacklist or invalid")
    
    def add_tag_group(self):
        """Add a tag group to the blacklist"""
        group_name = self.group_name_entry.get().strip()
        tags_text = self.group_tags_entry.get().strip()
        
        if not group_name or not tags_text:
            messagebox.showwarning("Warning", "Please enter both group name and tags")
            return
        
        tags = [tag.strip() for tag in tags_text.split() if tag.strip()]
        if not tags:
            messagebox.showwarning("Warning", "Please enter at least one tag")
            return
        
        if self.blacklist_manager.add_tag_group(group_name, tags):
            self.group_name_entry.delete(0, tk.END)
            self.group_tags_entry.delete(0, tk.END)
            self.refresh_lists()
            self.main_gui.update_blacklist_stats()
            messagebox.showinfo("Success", f"Added group '{group_name}' with {len(tags)} tags")
        else:
            messagebox.showerror("Error", "Failed to add tag group")
    
    def remove_selected_tags(self):
        """Remove selected tags from the blacklist"""
        selected_indices = self.tags_listbox.curselection()
        if not selected_indices:
            return
        
        selected_tags = [self.tags_listbox.get(i) for i in selected_indices]
        
        if messagebox.askyesno("Confirm", f"Remove {len(selected_tags)} selected tag(s)?"):
            removed_count = 0
            for tag in selected_tags:
                if self.blacklist_manager.remove_tag(tag):
                    removed_count += 1
            
            self.refresh_lists()
            self.main_gui.update_blacklist_stats()
            messagebox.showinfo("Success", f"Removed {removed_count} tag(s)")
    
    def remove_selected_groups(self):
        """Remove selected tag groups from the blacklist"""
        selected_indices = self.groups_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("Warning", "Please select one or more groups to remove")
            return
        
        # Get the actual group names using the stored indices
        selected_groups = []
        for i in selected_indices:
            if i < len(self.group_names):
                selected_groups.append(self.group_names[i])
        
        if not selected_groups:
            messagebox.showwarning("Warning", "No valid groups selected")
            return
        
        # Show confirmation with group details
        group_details = []
        total_tags = 0
        for group_name in selected_groups:
            group_tags = self.blacklist_manager.get_tag_groups().get(group_name, [])
            group_details.append(f"• {group_name} ({len(group_tags)} tags)")
            total_tags += len(group_tags)
        
        confirmation_msg = f"Remove {len(selected_groups)} group(s) and {total_tags} associated tags?\n\n"
        confirmation_msg += "\n".join(group_details)
        
        if messagebox.askyesno("Confirm Group Removal", confirmation_msg):
            removed_count = 0
            for group_name in selected_groups:
                if self.blacklist_manager.remove_tag_group(group_name):
                    removed_count += 1
            
            self.refresh_lists()
            self.main_gui.update_blacklist_stats()
            
            if removed_count > 0:
                messagebox.showinfo("Success", f"Removed {removed_count} group(s) successfully")
            else:
                messagebox.showerror("Error", "Failed to remove selected groups")
    
    def save_changes(self):
        """Save changes to blacklist file"""
        if self.blacklist_manager.save_blacklist():
            messagebox.showinfo("Success", "Blacklist saved successfully")
            self.main_gui.log_message("💾 Blacklist saved from manager window")
        else:
            messagebox.showerror("Error", "Failed to save blacklist")


class ImagePreviewWindow:
    """Separate window for image preview with editing capabilities"""
    
    def __init__(self, parent, image_path):
        self.window = ctk.CTkToplevel(parent)
        self.window.title(f"Preview - {image_path.name}")
        self.window.geometry("800x600")
        
        self.original_image = Image.open(image_path)
        self.display_image = self.original_image.copy()
        
        self.create_interface()
        self.update_display()
    
    def create_interface(self):
        self.image_label = tk.Label(self.window)
        self.image_label.pack(expand=True, fill="both", padx=10, pady=10)
        
        controls = ctk.CTkFrame(self.window)
        controls.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkButton(controls, text="Zoom In", command=self.zoom_in).pack(side="left", padx=5)
        ctk.CTkButton(controls, text="Zoom Out", command=self.zoom_out).pack(side="left", padx=5)
        ctk.CTkButton(controls, text="Fit to Window", command=self.fit_to_window).pack(side="left", padx=5)
        ctk.CTkButton(controls, text="Rotate 90°", command=self.rotate_image).pack(side="right", padx=5)
        ctk.CTkButton(controls, text="Delete", command=self.delete_image).pack(side="right", padx=5)
    
    def update_display(self): pass
    def zoom_in(self): pass
    def zoom_out(self): pass
    def fit_to_window(self): pass
    def rotate_image(self): pass
    def delete_image(self): pass


class DownloadProgressDialog:
    """Modal dialog for showing download progress"""
    
    def __init__(self, parent):
        self.dialog = ctk.CTkToplevel(parent)
        self.dialog.title("Download Progress")
        self.dialog.geometry("500x300")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self.create_interface()
    
    def create_interface(self):
        main_frame = ctk.CTkFrame(self.dialog)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(main_frame, text="Downloading Images", 
                    font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)
        
        self.overall_progress = ctk.CTkProgressBar(main_frame)
        self.overall_progress.pack(fill="x", padx=20, pady=10)
        
        self.overall_label = ctk.CTkLabel(main_frame, text="0 / 0 images")
        self.overall_label.pack(pady=5)
        
        ctk.CTkLabel(main_frame, text="Current File:").pack(pady=(20, 5))
        
        self.file_progress = ctk.CTkProgressBar(main_frame)
        self.file_progress.pack(fill="x", padx=20, pady=5)
        
        self.file_label = ctk.CTkLabel(main_frame, text="Ready...")
        self.file_label.pack(pady=5)
        
        stats_frame = ctk.CTkFrame(main_frame)
        stats_frame.pack(fill="x", padx=20, pady=10)
        
        self.speed_label = ctk.CTkLabel(stats_frame, text="Speed: 0 KB/s")
        self.speed_label.pack(side="left", padx=10)
        
        self.eta_label = ctk.CTkLabel(stats_frame, text="ETA: --:--")
        self.eta_label.pack(side="right", padx=10)
        
        ctk.CTkButton(main_frame, text="Cancel", command=self.cancel_download).pack(pady=10)
    
    def update_progress(self, current, total, filename="", file_progress=0.0, speed=0, eta=""):
        if total > 0:
            self.overall_progress.set(current / total)
            self.overall_label.configure(text=f"{current} / {total} images")
        
        self.file_progress.set(file_progress)
        self.file_label.configure(text=filename)
        
        self.speed_label.configure(text=f"Speed: {speed/1024:.1f} KB/s" if speed > 0 else "Speed: 0 KB/s")
        self.eta_label.configure(text=f"ETA: {eta}" if eta else "ETA: --:--")
    
    def cancel_download(self):
        self.dialog.destroy()


def main_gui():
    """
    Main function to launch the modern GUI.
    This can be called from rulescrape.py instead of the old GUI.
    """
    if not GUI_DEPENDENCIES_AVAILABLE:
        print("❌ GUI dependencies not available. Please install required packages:")
        print("pip install customtkinter pillow requests")
        return False
        
    if not MODULES_AVAILABLE:
        print("❌ Rulescrape modules not available. Please ensure all required files are present.")
        return False
    
    print("🎨 Starting Rulescrape Modern GUI...")
    
    app = RulescrapGUI()
    app.run()
    return True


if __name__ == "__main__":
    if not main_gui():
        sys.exit(1)
