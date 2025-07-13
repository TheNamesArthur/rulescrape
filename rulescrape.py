import os
import tkinter as tk
from tkinter import ttk, messagebox
import logging
from logging.handlers import TimedRotatingFileHandler
import gzip
import shutil
from booru_api import fetch_booru_posts, download_image
import configparser
import sys

def get_base_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

script_dir = get_base_path()
log_dir = os.path.join("logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "rulescrape.log")

# Config file for user settings
CONFIG_FILE = os.path.join('user_settings.config')


# Skins support: create skins folder if not exists
skins_dir = os.path.join("skins")
os.makedirs(skins_dir, exist_ok=True)

# Skins loader: returns a dict with color/layout overrides if a skin is found
import json
def load_skin():
    # Look for any .json file in skins_dir
    for fname in os.listdir(skins_dir):
        if fname.endswith('.json'):
            skin_path = os.path.join(skins_dir, fname)
            try:
                with open(skin_path, 'r', encoding='utf-8') as f:
                    skin = json.load(f)
                logging.info(f"Loaded skin: {fname}")
                return skin
            except Exception as e:
                logging.warning(f"Failed to load skin {fname}: {e}")
    return None

class GzTimedRotatingFileHandler(TimedRotatingFileHandler):
    def doRollover(self):
        super().doRollover()
        # Compress the most recent rotated log file
        if self.backupCount > 0:
            old_log = f"{self.baseFilename}.{self.rolloverAt - self.interval:%Y-%m-%d_%H-%M-%S}"
            # Find the most recent rotated log file
            import glob
            rotated_logs = sorted(glob.glob(f"{self.baseFilename}.*"), reverse=True)
            for rotated_log in rotated_logs:
                if not rotated_log.endswith('.gz') and rotated_log != self.baseFilename:
                    with open(rotated_log, 'rb') as f_in, gzip.open(rotated_log + '.gz', 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                    os.remove(rotated_log)
                    break

handler = GzTimedRotatingFileHandler(log_file, when='midnight', backupCount=7, encoding='utf-8', delay=True)
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger = logging.getLogger()
logger.setLevel(logging.INFO)
# Remove all existing handlers (if any)
for h in logger.handlers[:]:
    logger.removeHandler(h)
logger.addHandler(handler)

def run_script(booru_type, tag, limit):
    output_dir = os.path.join("images", booru_type)
    os.makedirs(output_dir, exist_ok=True)

    posts = fetch_booru_posts(booru_type, tags=tag, limit=limit)

    valid_images_processed = 0

    for post in posts:
        image_url = post.get('file_url')
        if not image_url or not image_url.startswith(('http://', 'https://')):
            logging.warning(f"Skipping invalid post: {post}")
            continue

        download_image(post, image_url, output_dir)

        valid_images_processed += 1
        if valid_images_processed >= limit:
            logging.info(f"Reached limit of {limit} valid images. Stopping.")
            break

    messagebox.showinfo("Done", f"Downloaded {valid_images_processed} images from {booru_type}.")

def load_user_settings():
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)
        settings = {}
        if 'Settings' in config:
            settings['booru_type'] = config['Settings'].get('booru_type', 'rule34')
            settings['tag'] = config['Settings'].get('tag', '')
            settings['limit'] = config['Settings'].getint('limit', 10)
            settings['anti_ai'] = config['Settings'].getboolean('anti_ai', False)
            settings['multithread'] = config['Settings'].getboolean('multithread', False)
        if 'UI' in config:
            settings['skin'] = config['UI'].get('skin', None)
            settings['window_width'] = config['UI'].getint('window_width', 400)
            settings['window_height'] = config['UI'].getint('window_height', 320)
        return settings
    # Defaults
    return {
        'booru_type': 'rule34',
        'tag': '',
        'limit': 10,
        'anti_ai': False,
        'multithread': False,
        'skin': None,
        'window_width': 400,
        'window_height': 320
    }


def save_user_settings(booru_type, tag, limit, anti_ai, multithread, skin=None, window_width=400, window_height=320):
    if os.path.exists(CONFIG_FILE):
        # Do not overwrite existing config
        return
    import configparser
    config = configparser.ConfigParser()
    config['Settings'] = {
        'booru_type': booru_type,
        'tag': tag,
        'limit': str(limit),
        'anti_ai': str(anti_ai),
        'multithread': str(multithread)
    }
    config['UI'] = {
        'skin': skin or 'custom_skin_here.json',
        'window_width': str(window_width),
        'window_height': str(window_height)
    }
    with open(CONFIG_FILE, 'w') as configfile:
        config.write(configfile)


def main_gui():
    global root, progress_var, progress_bar, progress_label, booru_var, tag_entry, limit_entry, anti_ai_var, start_button

    user_settings = load_user_settings()
    # Set window size from config if present
    root = tk.Tk()
    root.title("Rulescrape")
    win_w = user_settings.get('window_width', 400)
    win_h = user_settings.get('window_height', 320)
    root.geometry(f"{win_w}x{win_h}")

    # --- Skins support ---
    skin = None
    if user_settings.get('skin'):
        skin_path = os.path.join(skins_dir, user_settings['skin'])
        if os.path.exists(skin_path):
            try:
                with open(skin_path, 'r', encoding='utf-8') as f:
                    skin = json.load(f)
                root.skin_file = user_settings['skin']
                logging.info(f"Loaded skin from config: {user_settings['skin']}")
            except Exception as e:
                logging.warning(f"Failed to load skin {user_settings['skin']}: {e}")
                skin = None
        else:
            logging.warning(f"Skin file {user_settings['skin']} not found. Falling back to default skin.")
            skin = None
    if not skin:
        skin = load_skin()

    # Default theme and layout
    bg_color = "#23272e"
    fg_color = "#f8f8f2"
    entry_bg = "#282c34"
    entry_fg = "#f8f8f2"
    button_bg = "#44475a"
    button_fg = "#f8f8f2"
    highlight_color = "#6272a4"
    font_family = "TkDefaultFont"
    font_size = 9
    # Default layout positions (row, column, columnspan, sticky)
    layout = {
        "booru_label": {"row": 0, "column": 0, "padx": 10, "pady": 5, "sticky": "e"},
        "booru_var": {"row": 0, "column": 1, "padx": 10, "pady": 5, "sticky": "w"},
        "tag_label": {"row": 1, "column": 0, "padx": 10, "pady": 5, "sticky": "e"},
        "tag_entry": {"row": 1, "column": 1, "padx": 10, "pady": 5, "sticky": "w"},
        "limit_label": {"row": 2, "column": 0, "padx": 10, "pady": 5, "sticky": "e"},
        "limit_entry": {"row": 2, "column": 1, "padx": 10, "pady": 5, "sticky": "w"},
        "anti_ai_checkbox": {"row": 3, "column": 0, "columnspan": 2, "padx": 10, "pady": (10, 0), "sticky": "n"},
        "multithread_checkbox": {"row": 4, "column": 0, "columnspan": 2, "padx": 10, "pady": (2, 0), "sticky": "n"},
        "start_button": {"row": 5, "column": 0, "columnspan": 2, "pady": 10, "sticky": "ew"},
        "progress_bar": {"row": 6, "column": 0, "columnspan": 2, "padx": 10, "pady": 5, "sticky": "ew"},
        "progress_label": {"row": 7, "column": 0, "columnspan": 2, "pady": 2}
    }
    # Override with skin if present
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
    style.configure("TCombobox", fieldbackground=entry_bg, background=entry_bg, foreground=entry_fg, font=(font_family, font_size))
    style.map("TButton", background=[("active", highlight_color)])

    root.configure(bg=bg_color)


    # Dropdown for booru type
    booru_var = ttk.Combobox(root, values=["rule34", "safebooru"], state="readonly", font=(font_family, font_size))
    booru_var.set(user_settings.get('booru_type', 'rule34'))
    booru_var.configure(background=entry_bg, foreground=entry_fg)

    # Entry for tag with placeholder
    tag_label = ttk.Label(root, text="Tag:", font=(font_family, font_size))
    tag_entry = tk.Entry(root, bg=entry_bg, fg=entry_fg, insertbackground=fg_color, font=(font_family, font_size))
    tag_entry.insert(0, user_settings.get('tag', 'Enter tag...') or 'Enter tag...')

    # Checkbox for anti-ai tags (centered, smaller, above start button)
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

    # Checkbox for multi-threading option
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

    # Entry for limit with placeholder and validation
    limit_label = ttk.Label(root, text="Limit:", font=(font_family, font_size))
    limit_entry = tk.Entry(root, bg=entry_bg, fg=entry_fg, insertbackground=fg_color, font=(font_family, font_size))
    limit_entry.insert(0, str(user_settings.get('limit', 10)))


    # Progress bar (initially hidden)
    progress_var = tk.DoubleVar()
    progress_bar = ttk.Progressbar(root, variable=progress_var, maximum=100)
    progress_label = ttk.Label(root, text="Progress: 0%", font=(font_family, font_size))
    # Layout using skin/layout if present
    progress_bar.grid(**layout["progress_bar"])
    progress_label.grid(**layout["progress_label"])
    progress_bar.grid_remove()
    progress_label.grid_remove()

    # Button to start the process
    def on_entry_click(event):
        widget = event.widget
        if widget == tag_entry and tag_entry.get() == "Enter tag...":
            tag_entry.delete(0, tk.END)
        elif widget == limit_entry and limit_entry.get() == "Enter limit...":
            limit_entry.delete(0, tk.END)

    tag_entry.bind("<FocusIn>", on_entry_click)
    limit_entry.bind("<FocusIn>", on_entry_click)

    def run_script_with_progress(booru_type, tag, limit):
        progress_bar.grid()
        progress_label.grid()


        # Create main output dir and subfolders for each file type
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join("images", booru_type)
        os.makedirs(output_dir, exist_ok=True)
        file_types = ["jpg", "jpeg", "png", "gif", "webm", "mp4", "bmp", "svg", "other"]
        # No need to pre-create type_dirs, will create as needed per tag

        import time
        start_time = time.time()
        logging.info(f"--- Download session started: booru_type={booru_type}, tag='{tag}', limit={limit}, multithreaded={multithread_var.get()} ---")

        posts = fetch_booru_posts(booru_type, tags=tag, limit=limit)
        if not posts:
            logging.warning(f"No posts returned for booru_type={booru_type}, tag='{tag}', limit={limit}")
        total = min(len(posts), limit)
        valid_images_processed = 0

        # Update progress immediately on start
        percent = int((valid_images_processed / total) * 100) if total else 10
        progress_var.set(percent)
        progress_label.config(text=f"Progress: {percent}%")
        root.update_idletasks()

        if multithread_var.get():
            # Multi-threaded (experimental)
            from queue import Queue
            update_queue = Queue()
            import threading
            def worker(post, image_url):
                try:
                    ext = os.path.splitext(image_url)[1].lower().replace('.', '')
                    if ext not in file_types:
                        ext = "other"
                    tags = post.get('tags')
                    if isinstance(tags, str):
                        tag_list = tags.split()
                    elif isinstance(tags, list):
                        tag_list = tags
                    else:
                        tag_list = []
                    first_tag = tag_list[0] if tag_list else "untagged"
                    dest_dir = os.path.join(output_dir, ext, first_tag)
                    if not os.path.exists(dest_dir):
                        os.makedirs(dest_dir, exist_ok=True)
                        logging.info(f"Created directory: {dest_dir}")
                    logging.info(f"[Thread-{threading.get_ident()}] Downloading post {post.get('id')} to {dest_dir}")
                    download_image(post, image_url, dest_dir)
                    update_queue.put('progress')
                except Exception as e:
                    logging.error(f"Error downloading image: {e}")
                    update_queue.put('progress')
            from concurrent.futures import ThreadPoolExecutor
            logging.info("Starting ThreadPoolExecutor for downloads.")
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = []
                for post in posts:
                    image_url = post.get('file_url')
                    if not image_url or not image_url.startswith(('http://', 'https://')):
                        logging.warning(f"Skipping invalid post: {post}")
                        continue
                    futures.append(executor.submit(worker, post, image_url))
                while valid_images_processed < limit and (not all(f.done() for f in futures) or not update_queue.empty()):
                    try:
                        action = update_queue.get(timeout=0.1)
                    except Exception:
                        root.update_idletasks()
                        continue
                    if action == 'progress':
                        valid_images_processed += 1
                        percent = int((valid_images_processed / total) * 100) if total else 10
                        progress_var.set(percent)
                        progress_label.config(text=f"Progress: {percent}%")
                        root.update_idletasks()
                        if valid_images_processed >= limit:
                            logging.info(f"Reached limit of {limit} valid images. Stopping.")
                            break
                for f in futures:
                    f.result()
            logging.info("All threads finished.")
            elapsed = time.time() - start_time
            logging.info(f"--- Download session ended: {valid_images_processed} images downloaded in {elapsed:.2f} seconds ---")
            try:
                messagebox.showinfo("Done", f"Downloaded {valid_images_processed} images from {booru_type}.")
            except tk.TclError:
                logging.warning("Tkinter root window destroyed before showing completion message.")
            progress_var.set(0)
            progress_label.config(text="Progress: 0%")
            progress_bar.grid_remove()
            progress_label.grid_remove()
        else:
            # Single-threaded
            logging.info("Starting single-threaded download loop.")
            for post in posts:
                image_url = post.get('file_url')
                if not image_url or not image_url.startswith(('http://', 'https://')):
                    logging.warning(f"Skipping invalid post: {post}")
                    continue
                ext = os.path.splitext(image_url)[1].lower().replace('.', '')
                if ext not in file_types:
                    ext = "other"
                tags = post.get('tags')
                if isinstance(tags, str):
                    tag_list = tags.split()
                elif isinstance(tags, list):
                    tag_list = tags
                else:
                    tag_list = []
                first_tag = tag_list[0] if tag_list else "untagged"
                dest_dir = os.path.join(output_dir, ext, first_tag)
                if not os.path.exists(dest_dir):
                    os.makedirs(dest_dir, exist_ok=True)
                    logging.info(f"Created directory: {dest_dir}")
                logging.info(f"Downloading post {post.get('id')} to {dest_dir}")
                download_image(post, image_url, dest_dir)
                valid_images_processed += 1
                percent = int((valid_images_processed / total) * 100) if total else 10
                progress_var.set(percent)
                progress_label.config(text=f"Progress: {percent}%")
                root.update_idletasks()
                if valid_images_processed >= limit:
                    logging.info(f"Reached limit of {limit} valid images. Stopping.")
                    break
            elapsed = time.time() - start_time
            logging.info(f"--- Download session ended: {valid_images_processed} images downloaded in {elapsed:.2f} seconds ---")
            try:
                messagebox.showinfo("Done", f"Downloaded {valid_images_processed} images from {booru_type}.")
            except tk.TclError:
                logging.warning("Tkinter root window destroyed before showing completion message.")
            progress_var.set(0)
            progress_label.config(text="Progress: 0%")
            progress_bar.grid_remove()
            progress_label.grid_remove()

    def start_download():
        try:
            limit = int(limit_entry.get()) if limit_entry.get().isdigit() else 10
        except Exception:
            logging.warning("Invalid input for limit. Defaulting to 10.")
            limit = 10

        tag_text = tag_entry.get()
        if tag_text == "Enter tag...":
            tag_text = ""

        # Apply anti-AI tags filter
        if anti_ai_var.get():
            tag_text = (tag_text + " -ai -ai_generated -ai_assisted").strip()

        logging.info(f"User started download: booru_type={booru_var.get()}, tag='{tag_text}', limit={limit}, multithreaded={multithread_var.get()}")
        # Get current skin and window size
        current_skin = None
        if hasattr(root, 'skin_file'):
            current_skin = root.skin_file
        elif 'skin' in user_settings:
            current_skin = user_settings['skin']
        w = root.winfo_width() if root.winfo_exists() else 400
        h = root.winfo_height() if root.winfo_exists() else 320
        save_user_settings(booru_var.get(), tag_text, limit, anti_ai_var.get(), multithread_var.get(), current_skin, w, h)
        start_button.config(state="disabled")
        root.after(100, lambda: run_script_with_progress(
            booru_var.get(),
            tag_text,
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

    # Layout
    root.grid_rowconfigure((0, 1, 2, 3, 4, 5, 6, 7), weight=1)
    root.grid_columnconfigure((0, 1), weight=1)


    booru_label = ttk.Label(root, text="Booru Type:", font=(font_family, font_size))
    booru_label.grid(**layout["booru_label"])
    booru_var.grid(**layout["booru_var"])

    tag_label.grid(**layout["tag_label"])
    tag_entry.grid(**layout["tag_entry"])

    limit_label.grid(**layout["limit_label"])
    limit_entry.grid(**layout["limit_entry"])

    anti_ai_checkbox.grid(**layout["anti_ai_checkbox"])
    multithread_checkbox.grid(**layout["multithread_checkbox"])

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
    # progress_bar and progress_label are managed dynamically

    def on_closing():
        current_skin = None
        if hasattr(root, 'skin_file'):
            current_skin = root.skin_file
        elif 'skin' in user_settings:
            current_skin = user_settings['skin']
        w = root.winfo_width() if root.winfo_exists() else 400
        h = root.winfo_height() if root.winfo_exists() else 320
        save_user_settings(booru_var.get(), tag_entry.get(), int(limit_entry.get()) if limit_entry.get().isdigit() else 10, anti_ai_var.get(), multithread_var.get(), current_skin, w, h)
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)

    root.mainloop()

if __name__ == "__main__":
    main_gui()
