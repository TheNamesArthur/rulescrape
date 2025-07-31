import os
import json
import queue
import logging
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

from rulescrape import load_user_settings, save_user_settings, skins_dir


def _load_skin_configuration(user_settings, logger):
    """
    Load skin configuration from user settings or fallback to default.
    
    Args:
        user_settings: Dictionary of user settings
        logger: Logger instance
        
    Returns:
        dict or None: Skin configuration dictionary or None if no skin found
    """
    skin = None
    if user_settings.get('skin'):
        skin_path = os.path.join(skins_dir, user_settings['skin'])
        if os.path.exists(skin_path):
            try:
                with open(skin_path, 'r', encoding='utf-8') as f:
                    skin = json.load(f)
                logger.info(f"[gui._load_skin_configuration] Loaded skin from config: {user_settings['skin']}")
            except Exception as e:
                logger.warning(f"[gui._load_skin_configuration] Failed to load skin {user_settings['skin']}: {e}")
                skin = None
        else:
            logger.warning(f"[gui._load_skin_configuration] Skin file {user_settings['skin']} not found. Falling back to default skin.")
            skin = None
    
    if not skin:
        from rulescrape import load_skin
        skin = load_skin()
    
    return skin


def _get_default_theme_config():
    """
    Get default theme configuration values.
    
    Returns:
        tuple: (colors_dict, layout_dict) containing default theme values
    """
    colors = {
        'bg_color': "#23272e",
        'fg_color': "#f8f8f2",
        'entry_bg': "#282c34",
        'entry_fg': "#f8f8f2",
        'button_bg': "#44475a",
        'button_fg': "#f8f8f2",
        'highlight_color': "#6272a4",
        'font_family': "TkDefaultFont",
        'font_size': 9
    }
    
    layout = {
        "booru_label": {"row": 0, "column": 0, "padx": 3, "pady": 1, "sticky": "e"},
        "booru_var": {"row": 0, "column": 1, "padx": 3, "pady": 1, "sticky": "w"},
        "tag_label": {"row": 1, "column": 0, "padx": 3, "pady": 1, "sticky": "e"},
        "tag_entry": {"row": 1, "column": 1, "padx": 3, "pady": 1, "sticky": "w"},
        "limit_label": {"row": 2, "column": 0, "padx": 3, "pady": 1, "sticky": "e"},
        "limit_entry": {"row": 2, "column": 1, "padx": 3, "pady": 1, "sticky": "w"},
        "anti_ai_checkbox": {"row": 4, "column": 0, "columnspan": 2, "padx": 3, "pady": (2, 0), "sticky": "n"},
        "multithread_checkbox": {"row": 5, "column": 0, "columnspan": 2, "padx": 3, "pady": (1, 0), "sticky": "n"},
        "start_button": {"row": 6, "column": 0, "columnspan": 2, "pady": 3, "sticky": "ew"},
        "progress_bar": {"row": 7, "column": 0, "columnspan": 2, "padx": 3, "pady": 1, "sticky": "ew"},
        "progress_label": {"row": 8, "column": 0, "columnspan": 2, "pady": 1}
    }
    
    return colors, layout


def _apply_skin_overrides(skin, colors, layout):
    """
    Apply skin overrides to default configuration.
    
    Args:
        skin: Skin configuration dictionary
        colors: Default colors dictionary
        layout: Default layout dictionary
        
    Returns:
        tuple: Updated (colors, layout) dictionaries
    """
    if not skin:
        return colors, layout
        
    # Apply color overrides
    for key in colors:
        if key in skin:
            colors[key] = skin[key]
    
    # Apply layout overrides
    if "layout" in skin:
        layout.update(skin["layout"])
    
    return colors, layout


def _configure_ttk_styles(style, colors):
    """
    Configure TTK widget styles using color configuration.
    
    Args:
        style: TTK Style instance
        colors: Colors configuration dictionary
    """
    style.theme_use("clam")
    
    # Configure label style
    style.configure("TLabel", 
                   background=colors['bg_color'], 
                   foreground=colors['fg_color'], 
                   font=(colors['font_family'], colors['font_size']))
    
    # Configure button style
    style.configure("TButton", 
                   background=colors['button_bg'], 
                   foreground=colors['button_fg'], 
                   borderwidth=0, 
                   focusthickness=3, 
                   focuscolor=colors['highlight_color'], 
                   font=(colors['font_family'], colors['font_size']))
    style.map("TButton", background=[("active", colors['highlight_color'])])
    
    # Configure combobox style
    contrasting_highlight = "#ffb86c"
    style.configure("TCombobox", 
                   fieldbackground=colors['entry_bg'], 
                   background=colors['entry_bg'], 
                   foreground=colors['entry_fg'], 
                   font=(colors['font_family'], colors['font_size']), 
                   selectbackground=contrasting_highlight, 
                   selectforeground=colors['entry_fg'], 
                   highlightbackground=contrasting_highlight, 
                   highlightcolor=contrasting_highlight)
    style.map("TCombobox", 
              fieldbackground=[("active", contrasting_highlight)], 
              background=[("active", contrasting_highlight)])

def main_gui():
    """Main GUI application entry point."""
    global root, progress_var, progress_bar, progress_label, booru_var, tag_entry, limit_entry, anti_ai_var, start_button

    logger = logging.getLogger("gui")
    user_settings = load_user_settings()
    max_workers = user_settings.get('max_workers', 8)

    def reload_user_settings():
        """Reload user settings from configuration file."""
        nonlocal user_settings, max_workers
        user_settings = load_user_settings()
        max_workers = user_settings.get('max_workers', 8)
    # Initialize root window
    root = tk.Tk()
    root.title("Rulescrape")
    win_w = user_settings.get('window_width', 400)
    win_h = user_settings.get('window_height', 320)
    root.geometry(f"{win_w}x{win_h}")

    # Setup error queue handler for GUI popups
    error_queue = queue.Queue()
    
    def poll_error_queue():
        """Poll for error messages and display them as popups."""
        try:
            while True:
                msg = error_queue.get_nowait()
                try:
                    messagebox.showerror("Error", msg)
                except Exception:
                    logger.warning(f"[gui.poll_error_queue] Could not show error popup: {msg}")
        except queue.Empty:
            pass
        root.after(500, poll_error_queue)
    
    # Start polling for error messages
    root.after(500, poll_error_queue)

    # Load skin configuration and apply theme
    skin = _load_skin_configuration(user_settings, logger)
    if skin:
        root.skin_file = user_settings['skin']
    
    # Get theme configuration
    colors, layout = _get_default_theme_config()
    colors, layout = _apply_skin_overrides(skin, colors, layout)
    
    # Configure TTK styles
    style = ttk.Style(root)
    _configure_ttk_styles(style, colors)
    
    # Configure root window
    root.configure(bg=colors['bg_color'])

    # Load skin configuration
    skin = None
    if user_settings.get('skin'):
        skin_path = os.path.join(skins_dir, user_settings['skin'])
        if os.path.exists(skin_path):
            try:
                with open(skin_path, 'r', encoding='utf-8') as f:
                    skin = json.load(f)
                root.skin_file = user_settings['skin']
                logger.info(f"[gui.main_gui] Loaded skin from config: {user_settings['skin']}")
            except Exception as e:
                logger.warning(f"[gui.main_gui] Failed to load skin {user_settings['skin']}: {e}")
                skin = None
        else:
            logger.warning(f"[gui.main_gui] Skin file {user_settings['skin']} not found. Falling back to default skin.")
            skin = None
    
    if not skin:
        from rulescrape import load_skin
        skin = load_skin()

    # Default theme configuration
    bg_color = "#23272e"
    fg_color = "#f8f8f2"
    entry_bg = "#282c34"
    entry_fg = "#f8f8f2"
    button_bg = "#44475a"
    button_fg = "#f8f8f2"
    highlight_color = "#6272a4"
    font_family = "TkDefaultFont"
    font_size = 9
    
    # Default layout configuration
    layout = {
        "booru_label": {"row": 0, "column": 0, "padx": 3, "pady": 1, "sticky": "e"},
        "booru_var": {"row": 0, "column": 1, "padx": 3, "pady": 1, "sticky": "w"},
        "tag_label": {"row": 1, "column": 0, "padx": 3, "pady": 1, "sticky": "e"},
        "tag_entry": {"row": 1, "column": 1, "padx": 3, "pady": 1, "sticky": "w"},
        "limit_label": {"row": 2, "column": 0, "padx": 3, "pady": 1, "sticky": "e"},
        "limit_entry": {"row": 2, "column": 1, "padx": 3, "pady": 1, "sticky": "w"},
        "anti_ai_checkbox": {"row": 4, "column": 0, "columnspan": 2, "padx": 3, "pady": (2, 0), "sticky": "n"},
        "multithread_checkbox": {"row": 5, "column": 0, "columnspan": 2, "padx": 3, "pady": (1, 0), "sticky": "n"},
        "start_button": {"row": 6, "column": 0, "columnspan": 2, "pady": 3, "sticky": "ew"},
        "progress_bar": {"row": 7, "column": 0, "columnspan": 2, "padx": 3, "pady": 1, "sticky": "ew"},
        "progress_label": {"row": 8, "column": 0, "columnspan": 2, "pady": 1}
    }
    
    # Apply skin overrides if available
    if skin:
        bg_color = skin.get("bg_color", bg_color)
        fg_color = skin.get("fg_color", fg_color)
        entry_bg = skin.get("entry_bg", entry_bg)
        entry_fg = skin.get("entry_fg", entry_fg)
        button_bg = skin.get("button_bg", button_bg)
        button_fg = skin.get("button_fg", button_fg)
        highlight_color = skin.get("highlight_color", highlight_color)
        font_family = skin.get("font_family", font_family)
        font_size = skin.get("font_size", font_size)
        if "layout" in skin:
            layout.update(skin["layout"])

    # Configure ttk styles
    style = ttk.Style(root)
    style.theme_use("clam")
    
    # Configure label style
    style.configure("TLabel", 
                   background=bg_color, 
                   foreground=fg_color, 
                   font=(font_family, font_size))
    
    # Configure button style
    style.configure("TButton", 
                   background=button_bg, 
                   foreground=button_fg, 
                   borderwidth=0, 
                   focusthickness=3, 
                   focuscolor=highlight_color, 
                   font=(font_family, font_size))
    style.map("TButton", background=[("active", highlight_color)])
    
    # Configure combobox style
    contrasting_highlight = "#ffb86c"
    style.configure("TCombobox", 
                   fieldbackground=entry_bg, 
                   background=entry_bg, 
                   foreground=entry_fg, 
                   font=(font_family, font_size), 
                   selectbackground=contrasting_highlight, 
                   selectforeground=entry_fg, 
                   highlightbackground=contrasting_highlight, 
                   highlightcolor=contrasting_highlight)
    style.map("TCombobox", 
              fieldbackground=[("active", contrasting_highlight)], 
              background=[("active", contrasting_highlight)])
    
    # Configure root window
    root.configure(bg=bg_color)

    # Initialize progress tracking variables
    progress_var = tk.IntVar(value=0)
    progress_bar = ttk.Progressbar(root, variable=progress_var, maximum=100, style="TProgressbar")
    progress_label = ttk.Label(root, text="Progress: 0%", font=(colors['font_family'], colors['font_size']))

    # Create main input widgets
    booru_label = ttk.Label(root, text="Booru Type:", font=(colors['font_family'], colors['font_size']))
    booru_var = ttk.Combobox(root, 
                            values=["rule34", "safebooru", "danbooru", "yande.re", "paheal"], 
                            state="readonly", 
                            font=(colors['font_family'], colors['font_size']))
    booru_var.set(user_settings.get('booru_type', 'rule34'))
    booru_var.configure(background=colors['entry_bg'], foreground=colors['entry_fg'])

    tag_label = ttk.Label(root, text="Tag:", font=(colors['font_family'], colors['font_size']))
    tag_entry = tk.Entry(root, 
                        bg=colors['entry_bg'], 
                        fg=colors['entry_fg'], 
                        insertbackground=colors['fg_color'], 
                        font=(colors['font_family'], colors['font_size']))
    tag_entry.insert(0, user_settings.get('tag', 'Enter tag...') or 'Enter tag...')

    limit_label = ttk.Label(root, text="Limit:", font=(colors['font_family'], colors['font_size']))
    limit_entry = tk.Entry(root, 
                          bg=colors['entry_bg'], 
                          fg=colors['entry_fg'], 
                          insertbackground=colors['fg_color'], 
                          font=(colors['font_family'], colors['font_size']))
    limit_entry.insert(0, str(user_settings.get('limit', 10)))

    # Create organization method dropdown
    org_methods = [
        "By extension and first tag",
        "By extension only",
        "Flat (no folders)",
        "By tag only"
    ]
    org_method_var = tk.StringVar(value=user_settings.get('org_method', org_methods[0]))
    org_method_label = ttk.Label(root, text="Organization Method:", font=(colors['font_family'], colors['font_size']))
    org_method_dropdown = ttk.Combobox(root, 
                                      values=org_methods, 
                                      textvariable=org_method_var, 
                                      state="readonly", 
                                      font=(colors['font_family'], colors['font_size']))
    org_method_dropdown.configure(background=colors['entry_bg'], foreground=colors['entry_fg'])

    # Create option checkboxes
    anti_ai_var = tk.BooleanVar(value=user_settings.get('anti_ai', False))
    anti_ai_checkbox = tk.Checkbutton(
        root,
        text="Anti-AI tags",
        variable=anti_ai_var,
        bg=colors['bg_color'],
        fg=colors['fg_color'],
        activebackground=colors['bg_color'],
        activeforeground=colors['fg_color'],
        selectcolor=colors['bg_color'],
        font=(colors['font_family'], colors['font_size'])
    )

    multithread_var = tk.BooleanVar(value=user_settings.get('multithread', False))

    # Helper functions for GUI callbacks
    def show_danbooru_rate_limit_alert():
        messagebox.showinfo(
            "Danbooru Rate Limits",
            "Danbooru enforces a global rate limit of 10 read requests per second for all users and endpoints.\n\n"
            "Update actions are rate limited by user level:\n"
            "- Basic users: 1 update/second\n"
            "- Gold users and above: 4 updates/second\n\n"
            "Each endpoint has a burst pool allowing several consecutive updates before rate limiting applies. "
            "Most endpoints recharge at the rates above."
        )

    def show_multithread_warning():
        messagebox.showwarning(
            "Multi-threading Warning",
            "Enabling multi-threaded downloads will make downloads faster, but the progress bar may be less accurate."
        )

    def on_booru_selected(event=None):
        if booru_var.get() == "danbooru":
            show_danbooru_rate_limit_alert()
        save_config_live()

    # Bind event handlers
    booru_var.bind("<<ComboboxSelected>>", on_booru_selected)
    # Create multithread checkbox with warning
    multithread_checkbox = tk.Checkbutton(
        root,
        text="Enable multi-threaded downloads (experimental)",
        variable=multithread_var,
        bg=colors['bg_color'],
        fg=colors['fg_color'],
        activebackground=colors['bg_color'],
        activeforeground=colors['fg_color'],
        selectcolor=colors['bg_color'],
        font=(colors['font_family'], colors['font_size']),
        command=lambda: show_multithread_warning() if multithread_var.get() else None
    )
    # Widget grid placement
    org_method_label.grid(row=3, column=0, padx=3, pady=1, sticky="e")
    org_method_dropdown.grid(row=3, column=1, padx=3, pady=1, sticky="w")
    anti_ai_checkbox.grid(row=4, column=0, columnspan=2, padx=3, pady=(2, 0), sticky="n")
    multithread_checkbox.grid(row=5, column=0, columnspan=2, padx=3, pady=(1, 0), sticky="n")
    progress_bar.grid(**layout["progress_bar"])
    progress_label.grid(**layout["progress_label"])
    progress_bar.grid_remove()
    progress_label.grid_remove()
    progress_animation_colors = []
    if skin:
        progress_animation_colors = skin.get("progress_bar_animation", [])
    progress_animation_speed = skin.get("progress_bar_animation_speed", 100) if skin else 100
    progress_bar_color = skin.get("progress_bar_color", colors['highlight_color']) if skin else colors['highlight_color']
    style.configure("TProgressbar", troughcolor=colors['bg_color'], background=progress_bar_color)
    animation_running = False
    animation_index = 0
    def start_progress_animation():
        nonlocal animation_running, animation_index
        if not progress_animation_colors:
            return
        animation_running = True
        def animate():
            nonlocal animation_index
            if not animation_running:
                return
            color = progress_animation_colors[animation_index % len(progress_animation_colors)]
            style.configure("TProgressbar", background=color)
            animation_index += 1
            root.after(progress_animation_speed, animate)
        animate()
    def stop_progress_animation():
        nonlocal animation_running
        animation_running = False
        style.configure("TProgressbar", background=progress_bar_color)
    def update_progress(processed, total):
        if total == 0:
            progress_var.set(0)
            progress_label.config(text="Progress: 0%")
        else:
            percent = int((processed / total) * 100)
            progress_var.set(percent)
            progress_label.config(text=f"Progress: {percent}%")
    download_in_progress = [False]
    def run_script_with_progress(booru_type, tag, limit):
        """Use the unified download module for GUI downloads."""
        download_in_progress[0] = True
        progress_bar.grid()
        progress_label.grid()
        if progress_animation_colors:
            start_progress_animation()
            
        # Get settings
        user_settings = load_user_settings()
        output_dir = os.path.join(user_settings.get('output_dir', 'images'), booru_type)
        os.makedirs(output_dir, exist_ok=True)
        org_method = org_method_var.get() if 'org_method_var' in locals() else "By extension and first tag"
        use_multithread = multithread_var.get() if 'multithread_var' in locals() else False

        # Initialize duplication checker
        from dupe_check import get_dupe_checker
        dupe_checker = get_dupe_checker(user_settings.get('output_dir', 'images'))
        dupe_checker.reset_duplicate_count()
        scanned_count = dupe_checker.scan_existing_images()
        logger.info(f"[gui.run_script_with_progress] Scanned {scanned_count} existing images")

        def thread_target():
            """Execute download in background thread."""
            import time
            start_time = time.time()
            valid_images_processed = 0
            
            try:
                # Use the unified download module
                from download import run_download
                
                # Create a custom progress callback for GUI integration
                class GUIProgressManager:
                    def __init__(self):
                        self.processed = 0
                        self.duplicates = 0
                        
                    def update_progress(self, processed, duplicates_found):
                        self.processed = processed
                        self.duplicates = duplicates_found
                        
                        # Update GUI progress
                        if limit > 0:
                            percent = min(100, int((processed / limit) * 100))
                            root.after(0, lambda: progress_var.set(percent))
                            root.after(0, lambda: progress_label.config(
                                text=f"Progress: {percent}% ({processed}/{limit} images, {duplicates_found} duplicates skipped)"
                            ))
                
                # Create a simplified progress manager for this download
                progress_mgr = GUIProgressManager()
                
                # Override the download manager's log_message to provide progress updates
                original_log_message = None
                
                def gui_log_message_wrapper(original_method):
                    def wrapper(self, level, message):
                        # Call original logging
                        original_method(self, level, message)
                        
                        # Extract progress information from log messages
                        if "Downloaded " in message and "/" in message:
                            try:
                                # Parse "Downloaded X/Y unique images" messages
                                parts = message.split("Downloaded ")[1].split("/")
                                if len(parts) >= 2:
                                    current = int(parts[0])
                                    duplicates = dupe_checker.get_duplicate_count()
                                    progress_mgr.update_progress(current, duplicates)
                            except (ValueError, IndexError) as e:
                                # Ignore parsing errors for log messages
                                logger.debug(f"[gui.gui_log_message_wrapper] Failed to parse progress from log message: {e}")
                    return wrapper
                
                # Monkey patch the download manager's log_message method
                from download import DownloadManager
                original_log_method = DownloadManager.log_message
                DownloadManager.log_message = lambda self, level, msg: gui_log_message_wrapper(original_log_method)(self, level, msg)
                
                try:
                    # Run the unified download
                    success = run_download(
                        booru_type=booru_type,
                        tag=tag,
                        limit=limit,
                        output_dir=output_dir,
                        org_method=org_method,
                        dupe_checker=dupe_checker,
                        multithread=use_multithread,
                        max_workers=max_workers,
                        error_queue=error_queue
                    )
                    
                    valid_images_processed = progress_mgr.processed
                    
                    if success:
                        logger.info(f"[gui.thread_target] Download completed successfully: {valid_images_processed} images")
                    else:
                        logger.warning(f"[gui.thread_target] Download completed with issues: {valid_images_processed} images")
                        
                finally:
                    # Restore original method
                    DownloadManager.log_message = original_log_method
                    
            except Exception as e:
                logger.error(f"[gui.thread_target] Error during download: {e}")
                valid_images_processed = progress_mgr.processed if 'progress_mgr' in locals() else 0
            finally:
                elapsed = time.time() - start_time
                logger.info(f"[gui.thread_target] Download task finished in {elapsed:.2f} seconds.")
                root.after(100, lambda: show_completion_message(valid_images_processed))
                root.after(100, stop_progress_animation)
        
        t = threading.Thread(target=thread_target)
        t.daemon = True
        t.start()
    def show_completion_message(valid_images_processed):
        try:
            # Get duplicate count from the duplication checker
            from dupe_check import get_dupe_checker
            dupe_checker = get_dupe_checker("images")
            duplicates_found = dupe_checker.get_duplicate_count()
            
            if duplicates_found > 0:
                message = f"Downloaded {valid_images_processed} new images from {booru_var.get()}.\n{duplicates_found} duplicates were skipped."
            else:
                message = f"Downloaded {valid_images_processed} images from {booru_var.get()}."
            
            messagebox.showinfo("Done", message)
        except tk.TclError:
            logger.warning("[gui.show_completion_message] Tkinter root window destroyed before showing completion message.")
        finally:
            progress_var.set(0)
            progress_label.config(text="Progress: 0%")
            progress_bar.grid_remove()
            progress_label.grid_remove()
            stop_progress_animation()
            download_in_progress[0] = False
    def save_config_live(*args):
        try:
            limit_val = int(limit_entry.get()) if limit_entry.get().isdigit() else 10
        except Exception:
            logger.warning("[gui.save_config_live] Invalid limit value, defaulting to 10.")
            limit_val = 10
        tag_val = tag_entry.get()
        if tag_val == "Enter tag...":
            tag_val = ""
        current_skin = None
        if hasattr(root, 'skin_file'):
            current_skin = root.skin_file
        elif 'skin' in user_settings:
            current_skin = user_settings['skin']
        w = root.winfo_width() if root.winfo_exists() else 400
        h = root.winfo_height() if root.winfo_exists() else 320
        # Reload user settings to get current output_dir from config
        current_settings = load_user_settings()
        save_user_settings(
            booru_var.get(),
            tag_val,
            limit_val,
            anti_ai_var.get(),
            multithread_var.get(),
            org_method_var.get(),
            current_settings.get('output_dir', 'images'),
            current_skin,
            w,
            h
        )
        logger.info(f"[gui.save_config_live] User settings/config file changed: booru={booru_var.get()}, tag='{tag_val}', limit={limit_val}, anti_ai={anti_ai_var.get()}, multithread={multithread_var.get()}, org_method={org_method_var.get()}, skin={current_skin}, window=({w}x{h})")
    # booru_var.bind("<<ComboboxSelected>>", save_config_live)  # replaced by on_booru_selected
    tag_entry.bind("<KeyRelease>", save_config_live)
    limit_entry.bind("<KeyRelease>", save_config_live)
    anti_ai_var.trace_add("write", lambda *args: save_config_live())
    multithread_var.trace_add("write", lambda *args: save_config_live())
    org_method_var.trace_add("write", lambda *args: save_config_live())
    def start_download():
        try:
            limit = int(limit_entry.get()) if limit_entry.get().isdigit() else 10
        except Exception:
            logger.warning("[gui.start_download] Invalid input for limit. Defaulting to 10.")
            limit = 10
        tag_text_raw = tag_entry.get()
        if tag_text_raw == "Enter tag...":
            tag_text_raw = ""
        tag_text_for_download = tag_text_raw
        if anti_ai_var.get():
            tag_text_for_download = (tag_text_raw + " -ai -ai_generated -ai_assisted").strip()
        logger.info(f"[gui.start_download] User started download: booru_type={booru_var.get()}, tag='{tag_text_for_download}', limit={limit}, multithreaded={multithread_var.get()}")
        if download_in_progress[0]:
            messagebox.showinfo("Download in Progress", "Please wait for the current download to finish before starting a new one.")
            return
        start_button.config(state="disabled")
        root.after(100, lambda: run_script_with_progress(
            booru_var.get(),
            tag_text_for_download,
            limit
        ))
        start_button.config(state="normal")
    # Only create start_button once, and grid it once
    start_button = tk.Button(
        root,
        text="Start Download",
        bg=colors['button_bg'],
        fg=colors['button_fg'],
        activebackground=colors['highlight_color'],
        activeforeground=colors['fg_color'],
        font=(colors['font_family'], colors['font_size']),
        command=start_download
    )
    root.grid_rowconfigure((0, 1, 2, 3, 4, 5, 6, 7), weight=1)
    root.grid_columnconfigure((0, 1), weight=1)
    booru_label = ttk.Label(root, text="Booru Type:", font=(colors['font_family'], colors['font_size']))
    booru_label.grid(**layout["booru_label"])
    booru_var.grid(**layout["booru_var"])
    tag_label.grid(**layout["tag_label"])
    tag_entry.grid(**layout["tag_entry"])
    limit_label.grid(**layout["limit_label"])
    limit_entry.grid(**layout["limit_entry"])
    start_button.grid(**layout["start_button"])
    def on_closing():
        current_skin = None
        if hasattr(root, 'skin_file'):
            current_skin = root.skin_file
        elif 'skin' in user_settings:
            current_skin = user_settings['skin']
        w = root.winfo_width() if root.winfo_exists() else 400
        h = root.winfo_height() if root.winfo_exists() else 320
        # Reload user settings to get current output_dir from config
        current_settings = load_user_settings()
        save_user_settings(
            booru_var.get(),
            tag_entry.get(),
            int(limit_entry.get()) if limit_entry.get().isdigit() else 10,
            anti_ai_var.get(),
            multithread_var.get(),
            org_method_var.get(),
            current_settings.get('output_dir', 'images'),
            current_skin,
            w,
            h
        )
        try:
            root.quit()
        except Exception:
            pass
        root.destroy()
    skin_files = [f for f in os.listdir(skins_dir) if f.endswith('.json')]
    current_skin_index = 0
    if hasattr(root, 'skin_file') and root.skin_file in skin_files:
        current_skin_index = skin_files.index(root.skin_file)
    def apply_skin_by_index(idx):
        """Apply a skin configuration by index from the available skin files."""
        nonlocal skin, colors, layout, progress_animation_colors, progress_animation_speed, progress_bar_color
        skin_path = os.path.join(skins_dir, skin_files[idx])
        try:
            with open(skin_path, 'r', encoding='utf-8') as f:
                skin_obj = json.load(f)
            skin = skin_obj
            root.skin_file = skin_files[idx]
            
            # Update colors from skin
            for key in colors:
                if key in skin:
                    colors[key] = skin[key]
            
            # Update layout from skin
            if "layout" in skin:
                layout.update(skin["layout"])
                
            # Update progress bar configuration
            progress_animation_colors = skin.get("progress_bar_animation", [])
            progress_animation_speed = skin.get("progress_bar_animation_speed", 100)
            progress_bar_color = skin.get("progress_bar_color", colors['highlight_color'])
            
            # Reconfigure styles with new colors
            style.configure("TProgressbar", troughcolor=colors['bg_color'], background=progress_bar_color)
            style.configure("TLabel", background=colors['bg_color'], foreground=colors['fg_color'], font=(colors['font_family'], colors['font_size']))
            style.configure("TButton", background=colors['button_bg'], foreground=colors['button_fg'], borderwidth=0, focusthickness=3, focuscolor=colors['highlight_color'], font=(colors['font_family'], colors['font_size']))
            style.configure("TCombobox", fieldbackground=colors['entry_bg'], background=colors['entry_bg'], foreground=colors['entry_fg'], font=(colors['font_family'], colors['font_size']))
            
            # Update root window and widgets
            root.configure(bg=colors['bg_color'])
            tag_entry.config(bg=colors['entry_bg'], fg=colors['entry_fg'], insertbackground=colors['fg_color'], font=(colors['font_family'], colors['font_size']))
            limit_entry.config(bg=colors['entry_bg'], fg=colors['entry_fg'], insertbackground=colors['fg_color'], font=(colors['font_family'], colors['font_size']))
            anti_ai_checkbox.config(bg=colors['bg_color'], fg=colors['fg_color'], activebackground=colors['bg_color'], activeforeground=colors['fg_color'], selectcolor=colors['bg_color'], font=(colors['font_family'], colors['font_size']))
            multithread_checkbox.config(bg=colors['bg_color'], fg=colors['fg_color'], activebackground=colors['bg_color'], activeforeground=colors['fg_color'], selectcolor=colors['bg_color'], font=(colors['font_family'], colors['font_size']))
            start_button.config(bg=colors['button_bg'], fg=colors['button_fg'], activebackground=colors['highlight_color'], activeforeground=colors['fg_color'], font=(colors['font_family'], colors['font_size']))
            booru_var.config(background=colors['entry_bg'], foreground=colors['entry_fg'], font=(colors['font_family'], colors['font_size']))
            org_method_dropdown.config(background=colors['entry_bg'], foreground=colors['entry_fg'], font=(colors['font_family'], colors['font_size']))
            
            # Regrid all widgets with new layout
            booru_label.grid(**layout["booru_label"])
            booru_var.grid(**layout["booru_var"])
            tag_label.grid(**layout["tag_label"])
            tag_entry.grid(**layout["tag_entry"])
            limit_label.grid(**layout["limit_label"])
            limit_entry.grid(**layout["limit_entry"])
            org_method_label.grid(**layout.get("org_method_label", {"row":3, "column":0, "padx":3, "pady":1, "sticky":"e"}))
            org_method_dropdown.grid(**layout.get("org_method_dropdown", {"row":3, "column":1, "padx":3, "pady":1, "sticky":"w"}))
            anti_ai_checkbox.grid(**layout["anti_ai_checkbox"])
            multithread_checkbox.grid(**layout["multithread_checkbox"])
            progress_bar.grid(**layout["progress_bar"])
            progress_label.grid(**layout["progress_label"])
            start_button.grid(**layout["start_button"])
            if not download_in_progress[0]:
                progress_bar.grid_remove()
                progress_label.grid_remove()
        except Exception as e:
            logger.warning(f"[gui.apply_skin_by_index] Failed to apply skin {skin_files[idx]}: {e}")
    def cycle_skin(event=None):
        nonlocal current_skin_index
        if not skin_files:
            return
        current_skin_index = (current_skin_index + 1) % len(skin_files)
        apply_skin_by_index(current_skin_index)
        logger.info(f"[gui.cycle_skin] Cycled to skin: {skin_files[current_skin_index]}")
    root.bind('<Control-s>', cycle_skin)
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
