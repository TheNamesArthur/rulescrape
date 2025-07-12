import argparse
import requests
import os
import logging
import gzip
from logging.handlers import RotatingFileHandler
from datetime import datetime
from urllib.parse import urljoin
from tqdm import tqdm
import tkinter as tk
from tkinter import ttk, messagebox
from concurrent.futures import ThreadPoolExecutor
import threading

# --- Logging Setup ---
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)
log_filename = os.path.join(log_dir, f"rulescrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log.gz")

class GzipRotatingFileHandler(logging.Handler):
    def __init__(self, filename):
        super().__init__()
        self.filename = filename
        self.file = gzip.open(self.filename, 'at', encoding='utf-8')
    def emit(self, record):
        msg = self.format(record)
        self.file.write(msg + '\n')
        self.file.flush()
    def close(self):
        self.file.close()
        super().close()

logger = logging.getLogger("rulescrape")
logger.setLevel(logging.INFO)
gzip_handler = GzipRotatingFileHandler(log_filename)
gzip_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
logger.addHandler(gzip_handler)

def fetch_booru_posts(booru_type, tags=None, limit=10):
    logger.info(f"Fetching posts from {booru_type} with tags='{tags}' and limit={limit}")
    if booru_type == 'rule34':
        url = "https://api.rule34.xxx/index.php?page=dapi&s=post&q=index"
    elif booru_type == 'safebooru':
        url = "https://safebooru.org/index.php?page=dapi&s=post&q=index"
    else:
        logger.error(f"Unsupported booru type: {booru_type}")
        raise ValueError(f"Unsupported booru type: {booru_type}")

    params = {
        'tags': tags,
        'limit': limit,
        'json': 1
    }

    headers = {'Accept': 'application/json'}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Error fetching data from {booru_type} API: {e}")
        print(f"Error fetching data from {booru_type} API: {e}")
        return []

    try:
        data = response.json()
    except ValueError as e:
        logger.error(f"Invalid JSON response from {booru_type} API. Error: {e}")
        print(f"Invalid JSON response from {booru_type} API. Error: {e}")
        return []

    logger.info(f"Fetched {len(data)} posts from {booru_type}")
    return data

def download_image(post, image_url, output_dir):
    try:
        if not image_url or not image_url.startswith(('http://', 'https://')):
            logger.warning(f"Invalid image URL for post {post.get('id', '?')}: {image_url}")
            print(f"Invalid image URL for post {post['id']}: {image_url}")
            return

        response = requests.get(image_url, stream=True, timeout=10)
        response.raise_for_status()

        content_type = response.headers.get('Content-Type', '')
        extension = ''

        if '.' in image_url.split('/')[-1]:
            filename_part = image_url.split('/')[-1]
            _, ext = os.path.splitext(filename_part)
            extension = ext
        else:
            if 'image/jpeg' in content_type:
                extension = '.jpg'
            elif 'image/png' in content_type:
                extension = '.png'
            elif 'image/gif' in content_type:
                extension = '.gif'
            elif 'video/mp4' in content_type:
                extension = '.mp4'
            else:
                extension = '.jpg'

        filename = os.path.join(output_dir, f"post_{post['id']}{extension}")

        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024

        with open(filename, 'wb') as f:
            with tqdm(total=total_size, unit='B', unit_scale=True, unit_divisor=1024, desc=f"Downloading {filename}") as pbar:
                for chunk in response.iter_content(chunk_size=block_size):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))

        logger.info(f"Downloaded image for post ID {post['id']} -> {filename}")
        print(f"Downloaded image for post ID {post['id']} -> {filename}")

    except requests.RequestException as e:
        logger.error(f"Failed to download image for post ID {post.get('id', '?')}: {e}")
        print(f"Failed to download image for post ID {post['id']}: {e}")
    except Exception as e:
        logger.error(f"Error saving image for post ID {post.get('id', '?')}: {e}")
        print(f"Error saving image for post ID {post['id']}: {e}")

def run_script(booru_type, tag, limit):
    logger.info(f"Script started for booru_type={booru_type}, tag='{tag}', limit={limit}")
    output_dir = os.path.join("images", booru_type)
    os.makedirs(output_dir, exist_ok=True)

    posts = fetch_booru_posts(booru_type, tags=tag, limit=limit)

    valid_images_processed = 0

    for post in posts:
        image_url = post.get('file_url')
        if not image_url or not image_url.startswith(('http://', 'https://')):
            logger.warning(f"Skipping invalid post: {post}")
            print(f"Skipping invalid post: {post}")
            continue

        download_image(post, image_url, output_dir)

        valid_images_processed += 1
        if valid_images_processed >= limit:
            logger.info(f"Reached limit of {limit} valid images. Stopping.")
            print(f"Reached limit of {limit} valid images. Stopping.")
            break

    logger.info(f"Script finished. Downloaded {valid_images_processed} images from {booru_type}.")
    messagebox.showinfo("Done", f"Downloaded {valid_images_processed} images from {booru_type}.")

def main_gui():
    logger.info("Application started (main_gui)")
    root = tk.Tk()
    root.title("Rulescrape")
    root.geometry("400x320")

    # --- Dark Theme Colors ---
    bg_color = "#23272e"
    fg_color = "#f8f8f2"
    entry_bg = "#282c34"
    entry_fg = "#f8f8f2"
    button_bg = "#44475a"
    button_fg = "#f8f8f2"
    highlight_color = "#6272a4"

    # --- Tooltip Helper ---
    tooltip_label = None
    def show_tooltip(widget, text):
        nonlocal tooltip_label
        if tooltip_label:
            tooltip_label.destroy()
        # Place tooltip below the widget, aligned to left edge
        x = widget.winfo_rootx() - root.winfo_rootx()
        y = widget.winfo_rooty() - root.winfo_rooty() + widget.winfo_height() + 4
        tooltip_label = tk.Label(root, text=text, bg="#44475a", fg="#f8f8f2", relief="solid", borderwidth=1, font=("TkDefaultFont", 9), wraplength=250, justify="left")
        tooltip_label.place(x=x, y=y)
    def hide_tooltip(event=None):
        nonlocal tooltip_label
        if tooltip_label:
            tooltip_label.destroy()
            tooltip_label = None

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TLabel", background=bg_color, foreground=fg_color)
    style.configure("TButton", background=button_bg, foreground=button_fg, borderwidth=0, focusthickness=3, focuscolor=highlight_color)
    style.configure("TCombobox", fieldbackground=entry_bg, background=entry_bg, foreground=entry_fg)
    style.map("TButton", background=[("active", highlight_color)])

    root.configure(bg=bg_color)

    # Dropdown for booru type
    booru_var = ttk.Combobox(root, values=["rule34", "safebooru"], state="readonly")
    booru_var.set("rule34")
    booru_var.configure(background=entry_bg, foreground=entry_fg)
    booru_var.bind("<Enter>", lambda e: show_tooltip(booru_var, "Select which booru site to download from."))
    booru_var.bind("<Leave>", hide_tooltip)

    # Entry for tag with placeholder
    tag_label = ttk.Label(root, text="Tag:")
    tag_entry = tk.Entry(root, bg=entry_bg, fg=entry_fg, insertbackground=fg_color)
    tag_entry.insert(0, "Enter tag...")
    tag_entry.bind("<Enter>", lambda e: show_tooltip(tag_entry, "Enter tags to search for (e.g., 'cat_girl'). Leave blank for all posts."))
    tag_entry.bind("<Leave>", hide_tooltip)

    # Checkbox for anti-ai tags (centered, smaller, above start button)
    anti_ai_var = tk.BooleanVar(value=False)
    anti_ai_checkbox = tk.Checkbutton(
        root,
        text="Anti-AI tags",
        variable=anti_ai_var,
        bg=bg_color,
        fg=fg_color,
        activebackground=bg_color,
        activeforeground=fg_color,
        selectcolor=bg_color,
        font=("TkDefaultFont", 9)
    )
    anti_ai_checkbox.bind("<Enter>", lambda e: show_tooltip(anti_ai_checkbox, "If checked, adds tags to filter out AI-generated images."))
    anti_ai_checkbox.bind("<Leave>", hide_tooltip)

    # Entry for limit with placeholder and validation
    limit_label = ttk.Label(root, text="Limit:")
    limit_entry = tk.Entry(root, bg=entry_bg, fg=entry_fg, insertbackground=fg_color)
    limit_entry.insert(0, "Enter limit...")
    limit_entry.bind("<Enter>", lambda e: show_tooltip(limit_entry, "Maximum number of images to download (default: 10)."))
    limit_entry.bind("<Leave>", hide_tooltip)

    # Progress bar (initially hidden)
    progress_var = tk.DoubleVar()
    progress_bar = ttk.Progressbar(root, variable=progress_var, maximum=100)
    progress_label = ttk.Label(root, text="Progress: 0%")
    progress_bar.grid(row=6, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
    progress_label.grid(row=7, column=0, columnspan=2, pady=2)
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
        logger.info(f"Started download with progress: booru_type={booru_type}, tag='{tag}', limit={limit}")
        progress_bar.grid()
        progress_label.grid()
        output_dir = os.path.join("images", booru_type)
        os.makedirs(output_dir, exist_ok=True)

        posts = fetch_booru_posts(booru_type, tags=tag, limit=limit)
        total = min(len(posts), limit)
        valid_images_processed = 0

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for post in posts:
                image_url = post.get('file_url')
                if not image_url or not image_url.startswith(('http://', 'https://')):
                    logger.warning(f"Skipping invalid post: {post}")
                    print(f"Skipping invalid post: {post}")
                    continue
                future = executor.submit(download_image, post, image_url, output_dir)
                futures.append(future)

            for future in futures:
                try:
                    future.result()
                    valid_images_processed += 1
                    percent = int((valid_images_processed / total) * 100) if total else 100
                    progress_var.set(percent)
                    progress_label.config(text=f"Progress: {percent}%")
                    root.update_idletasks()

                    if valid_images_processed >= limit:
                        logger.info(f"Reached limit of {limit} valid images. Stopping.")
                        print(f"Reached limit of {limit} valid images. Stopping.")
                        break
                except Exception as e:
                    logger.error(f"Error in future result: {e}")
                    print(f"Error in future result: {e}")

        logger.info(f"Download finished. Downloaded {valid_images_processed} images from {booru_type}.")
        messagebox.showinfo("Done", f"Downloaded {valid_images_processed} images from {booru_type}.")
        progress_var.set(0)
        progress_label.config(text="Progress: 0%")
        progress_bar.grid_remove()
        progress_label.grid_remove()

    def start_download():
        try:
            limit = int(limit_entry.get()) if limit_entry.get().isdigit() else 10
        except Exception:
            limit = 10

        tag_text = tag_entry.get() if tag_entry.get() != "Enter tag..." else ""
        if anti_ai_var.get():
            tag_text = (tag_text + " -ai -ai_generated -ai_assisted").strip()

        logger.info(f"User started download: booru_type={booru_var.get()}, tag='{tag_text}', limit={limit}, anti_ai={anti_ai_var.get()}")
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
    start_button.bind("<Enter>", lambda e: show_tooltip(start_button, "Begin downloading images with the selected options."))
    start_button.bind("<Leave>", hide_tooltip)

    # Layout
    root.grid_rowconfigure((0, 1, 2, 3, 4, 5, 6, 7), weight=1)
    root.grid_columnconfigure((0, 1), weight=1)

    booru_label = ttk.Label(root, text="Booru Type:")
    booru_label.grid(row=0, column=0, padx=10, pady=5, sticky="e")
    booru_var.grid(row=0, column=1, padx=10, pady=5, sticky="w")

    tag_label.grid(row=1, column=0, padx=10, pady=5, sticky="e")
    tag_entry.grid(row=1, column=1, padx=10, pady=5, sticky="w")

    limit_label.grid(row=2, column=0, padx=10, pady=5, sticky="e")
    limit_entry.grid(row=2, column=1, padx=10, pady=5, sticky="w")

    # Center the checkbox above the start button, make it span both columns
    anti_ai_checkbox.grid(row=3, column=0, columnspan=2, padx=10, pady=(10, 0), sticky="n")

    start_button.grid(row=4, column=0, columnspan=2, pady=10, sticky="ew")
    # progress_bar and progress_label are managed dynamically

    root.mainloop()

if __name__ == "__main__":
    main_gui()