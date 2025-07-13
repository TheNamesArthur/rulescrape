import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import logging
import json
from booru_api import fetch_booru_posts, download_image
import configparser
import sys

# These should be imported from rulescrape.py if needed
from rulescrape import load_user_settings, save_user_settings, skins_dir

def main_gui():
    global root, progress_var, progress_bar, progress_label, booru_var, tag_entry, limit_entry, anti_ai_var, start_button

    logger = logging.getLogger("gui")
    user_settings = load_user_settings()
    def reload_user_settings():
        nonlocal user_settings, max_workers
        user_settings = load_user_settings()
        max_workers = user_settings.get('max_workers', 8)

    max_workers = user_settings.get('max_workers', 8)
    root = tk.Tk()
    root.title("Rulescrape")
    win_w = user_settings.get('window_width', 400)
    win_h = user_settings.get('window_height', 320)
    root.geometry(f"{win_w}x{win_h}")

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

    bg_color = "#23272e"
    fg_color = "#f8f8f2"
    entry_bg = "#282c34"
    entry_fg = "#f8f8f2"
    button_bg = "#44475a"
    button_fg = "#f8f8f2"
    highlight_color = "#6272a4"
    font_family = "TkDefaultFont"
    font_size = 9
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

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TLabel", background=bg_color, foreground=fg_color, font=(font_family, font_size))
    style.configure("TButton", background=button_bg, foreground=button_fg, borderwidth=0, focusthickness=3, focuscolor=highlight_color, font=(font_family, font_size))
    contrasting_highlight = "#ffb86c"
    style.configure("TCombobox", fieldbackground=entry_bg, background=entry_bg, foreground=entry_fg, font=(font_family, font_size), selectbackground=contrasting_highlight, selectforeground=entry_fg, highlightbackground=contrasting_highlight, highlightcolor=contrasting_highlight)
    style.map("TCombobox", fieldbackground=[("active", contrasting_highlight)], background=[("active", contrasting_highlight)])
    style.map("TButton", background=[("active", highlight_color)])
    root.configure(bg=bg_color)

    # Define progress_var and progress_bar before use
    progress_var = tk.IntVar(value=0)
    progress_bar = ttk.Progressbar(root, variable=progress_var, maximum=100, style="TProgressbar")

    booru_var = ttk.Combobox(root, values=["rule34", "safebooru", "danbooru"], state="readonly", font=(font_family, font_size))
    booru_var.set(user_settings.get('booru_type', 'rule34'))
    booru_var.configure(background=entry_bg, foreground=entry_fg)

    def show_danbooru_rate_limit_alert():
        messagebox.showinfo(
            "Danbooru Rate Limits",
            "Danbooru enforces a global rate limit of 10 read requests per second for all users and endpoints.\n\nUpdate actions are rate limited by user level:\n- Basic users: 1 update/second\n- Gold users and above: 4 updates/second\n\nEach endpoint has a burst pool allowing several consecutive updates before rate limiting applies. Most endpoints recharge at the rates above."
        )

    def on_booru_selected(event=None):
        if booru_var.get() == "danbooru":
            show_danbooru_rate_limit_alert()
        save_config_live()

    booru_var.bind("<<ComboboxSelected>>", on_booru_selected)
    tag_label = ttk.Label(root, text="Tag:", font=(font_family, font_size))
    tag_entry = tk.Entry(root, bg=entry_bg, fg=entry_fg, insertbackground=fg_color, font=(font_family, font_size))
    tag_entry.insert(0, user_settings.get('tag', 'Enter tag...') or 'Enter tag...')
    anti_ai_var = tk.BooleanVar(value=user_settings.get('anti_ai', False))
    anti_ai_checkbox = tk.Checkbutton(
        root,
        text="Anti-AI tags",
        variable=anti_ai_var,
        bg=bg_color,
        fg=fg_color,
        activebackground=bg_color,
        activeforeground=fg_color,
        selectcolor=bg_color,
        font=(font_family, font_size)
    )
    multithread_var = tk.BooleanVar(value=user_settings.get('multithread', False))
    def show_multithread_warning():
        messagebox.showwarning(
            "Multi-threading Warning",
            "Enabling multi-threaded downloads will make downloads faster, but the progress bar may be less accurate."
        )
    multithread_checkbox = tk.Checkbutton(
        root,
        text="Enable multi-threaded downloads (experimental)",
        variable=multithread_var,
        bg=bg_color,
        fg=fg_color,
        activebackground=bg_color,
        activeforeground=fg_color,
        selectcolor=bg_color,
        font=(font_family, font_size),
        command=lambda: show_multithread_warning() if multithread_var.get() else None
    )
    limit_label = ttk.Label(root, text="Limit:", font=(font_family, font_size))
    limit_entry = tk.Entry(root, bg=entry_bg, fg=entry_fg, insertbackground=fg_color, font=(font_family, font_size))
    org_methods = [
        "By extension and first tag",
        "By extension only",
        "Flat (no folders)",
        "By tag only"
    ]
    org_method_var = tk.StringVar(value=user_settings.get('org_method', org_methods[0]))
    org_method_label = ttk.Label(root, text="Organization Method:", font=(font_family, font_size))
    org_method_dropdown = ttk.Combobox(root, values=org_methods, textvariable=org_method_var, state="readonly", font=(font_family, font_size))
    org_method_dropdown.configure(background=entry_bg, foreground=entry_fg)
    limit_entry.insert(0, str(user_settings.get('limit', 10)))
    progress_label = ttk.Label(root, text="Progress: 0%", font=(font_family, font_size))
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
    progress_bar_color = skin.get("progress_bar_color", highlight_color) if skin else highlight_color
    style.configure("TProgressbar", troughcolor=bg_color, background=progress_bar_color)
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
        import concurrent.futures
        from threading import Lock
        download_in_progress[0] = True
        progress_bar.grid()
        progress_label.grid()
        if progress_animation_colors:
            start_progress_animation()
        output_dir = os.path.join("images", booru_type)
        os.makedirs(output_dir, exist_ok=True)
        org_method = org_method_var.get() if 'org_method_var' in locals() else "By extension and first tag"
        use_multithread = multithread_var.get() if 'multithread_var' in locals() else False
        def get_dest_dir(post):
            image_url = post.get('file_url')
            ext = os.path.splitext(image_url.split('?')[0])[1].lower().replace('.', '')
            if ext not in ["jpg", "jpeg", "png", "gif", "webm", "mp4", "bmp", "svg", "other"]:
                ext = "other"
            # Use correct tag field for Danbooru
            if booru_var.get() == "danbooru":
                tags = post.get('tag_string', '')
                tag_list = tags.split() if isinstance(tags, str) else []
            else:
                tags = post.get('tags', '')
                tag_list = tags.split() if isinstance(tags, str) else []
            if org_method == "By extension and first tag":
                return os.path.join(output_dir, ext, tag_list[0] if tag_list else "untagged")
            elif org_method == "By extension only":
                return os.path.join(output_dir, ext)
            elif org_method == "Flat (no folders)":
                return output_dir
            elif org_method == "By tag only":
                return os.path.join(output_dir, tag_list[0] if tag_list else "untagged")
            else:
                return os.path.join(output_dir, ext, tag_list[0] if tag_list else "untagged")
        progress_lock = Lock()
        valid_images_processed = [0]  # Use list for mutability in threads
        def download_one(post, total_arg=None):
            image_url = post.get('file_url')
            if not image_url or not image_url.startswith(('http://', 'https://')):
                logger.warning(f"[gui.download_one] Skipping invalid post: {post}")
                return False
            dest_dir = get_dest_dir(post)
            os.makedirs(dest_dir, exist_ok=True)
            logger.info(f"[gui.download_one] Downloading {image_url} to {dest_dir}")
            try:
                download_image(post, image_url, dest_dir)
                with progress_lock:
                    valid_images_processed[0] += 1
                    root.after(0, lambda vp=valid_images_processed[0]: update_progress(vp, total_arg))
                return True
            except Exception as e:
                logger.error(f"[gui.download_one] Error downloading {image_url}: {e}")
                return False
        def thread_target():
            import time
            start_time = time.time()
            try:
                posts = fetch_booru_posts(booru_type, tags=tag, limit=limit)
                total = min(len(posts), limit)
                root.after(100, lambda: update_progress(0, total))
                if use_multithread:
                    logger.info(f"[gui.thread_target] Starting multi-threaded download with {max_workers} workers.")
                    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                        futures = [executor.submit(download_one, post, total) for post in posts]
                        for future in concurrent.futures.as_completed(futures):
                            # Progress is updated in download_one via lock
                            if valid_images_processed[0] >= limit:
                                break
                else:
                    for post in posts:
                        if download_one(post, total):
                            pass  # Progress updated in download_one
                        if valid_images_processed[0] >= limit:
                            break
            except Exception as e:
                logger.error(f"[gui.thread_target] Error during download: {e}")
                root.after(100, lambda: update_progress(0, 0))
                root.after(100, lambda: show_completion_message(0))
            finally:
                elapsed = time.time() - start_time
                logger.info(f"[gui.thread_target] Download task finished in {elapsed:.2f} seconds.")
                root.after(100, lambda: show_completion_message(valid_images_processed[0]))
                root.after(100, stop_progress_animation)
        threading.Thread(target=thread_target).start()
    def show_completion_message(valid_images_processed):
        try:
            messagebox.showinfo("Done", f"Downloaded {valid_images_processed} images from {booru_var.get()}.")
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
        save_user_settings(
            booru_var.get(),
            tag_val,
            limit_val,
            anti_ai_var.get(),
            multithread_var.get(),
            org_method_var.get(),
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
    start_button = tk.Button(
        root,
        text="Start Download",
        bg=button_bg,
        fg=button_fg,
        activebackground=highlight_color,
        activeforeground=fg_color,
        command=start_download
    )
    root.grid_rowconfigure((0, 1, 2, 3, 4, 5, 6, 7), weight=1)
    root.grid_columnconfigure((0, 1), weight=1)
    booru_label = ttk.Label(root, text="Booru Type:", font=(font_family, font_size))
    booru_label.grid(**layout["booru_label"])
    booru_var.grid(**layout["booru_var"])
    tag_label.grid(**layout["tag_label"])
    tag_entry.grid(**layout["tag_entry"])
    limit_label.grid(**layout["limit_label"])
    limit_entry.grid(**layout["limit_entry"])
    start_button = tk.Button(
        root,
        text="Start Download",
        bg=button_bg,
        fg=button_fg,
        activebackground=highlight_color,
        activeforeground=fg_color,
        font=(font_family, font_size),
        command=start_download
    )
    start_button.grid(**layout["start_button"])
    def on_closing():
        current_skin = None
        if hasattr(root, 'skin_file'):
            current_skin = root.skin_file
        elif 'skin' in user_settings:
            current_skin = user_settings['skin']
        w = root.winfo_width() if root.winfo_exists() else 400
        h = root.winfo_height() if root.winfo_exists() else 320
        save_user_settings(
            booru_var.get(),
            tag_entry.get(),
            int(limit_entry.get()) if limit_entry.get().isdigit() else 10,
            anti_ai_var.get(),
            multithread_var.get(),
            org_method_var.get(),
            current_skin,
            w,
            h
        )
        root.destroy()
    skin_files = [f for f in os.listdir(skins_dir) if f.endswith('.json')]
    current_skin_index = 0
    if hasattr(root, 'skin_file') and root.skin_file in skin_files:
        current_skin_index = skin_files.index(root.skin_file)
    def apply_skin_by_index(idx):
        nonlocal skin, bg_color, fg_color, entry_bg, entry_fg, button_bg, button_fg, highlight_color, font_family, font_size, layout, progress_animation_colors, progress_animation_speed, progress_bar_color
        skin_path = os.path.join(skins_dir, skin_files[idx])
        try:
            with open(skin_path, 'r', encoding='utf-8') as f:
                skin_obj = json.load(f)
            skin = skin_obj
            root.skin_file = skin_files[idx]
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
            progress_animation_colors = skin.get("progress_bar_animation", [])
            progress_animation_speed = skin.get("progress_bar_animation_speed", 100)
            progress_bar_color = skin.get("progress_bar_color", highlight_color)
            style.configure("TProgressbar", troughcolor=bg_color, background=progress_bar_color)
            style.configure("TLabel", background=bg_color, foreground=fg_color, font=(font_family, font_size))
            style.configure("TButton", background=button_bg, foreground=button_fg, borderwidth=0, focusthickness=3, focuscolor=highlight_color, font=(font_family, font_size))
            style.configure("TCombobox", fieldbackground=entry_bg, background=entry_bg, foreground=entry_fg, font=(font_family, font_size))
            root.configure(bg=bg_color)
            tag_entry.config(bg=entry_bg, fg=entry_fg, insertbackground=fg_color, font=(font_family, font_size))
            limit_entry.config(bg=entry_bg, fg=entry_fg, insertbackground=fg_color, font=(font_family, font_size))
            anti_ai_checkbox.config(bg=bg_color, fg=fg_color, activebackground=bg_color, activeforeground=fg_color, selectcolor=bg_color, font=(font_family, font_size))
            multithread_checkbox.config(bg=bg_color, fg=fg_color, activebackground=bg_color, activeforeground=fg_color, selectcolor=bg_color, font=(font_family, font_size))
            start_button.config(bg=button_bg, fg=button_fg, activebackground=highlight_color, activeforeground=fg_color, font=(font_family, font_size))
            booru_var.config(background=entry_bg, foreground=entry_fg, font=(font_family, font_size))
            org_method_dropdown.config(background=entry_bg, foreground=entry_fg, font=(font_family, font_size))
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
