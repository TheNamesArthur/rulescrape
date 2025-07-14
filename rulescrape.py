import os
import logging
from logging.handlers import TimedRotatingFileHandler
import gzip
import shutil
from booru_api import fetch_booru_posts, download_image
import configparser
import sys

import booru_api

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
                continue
    return None

class GzTimedRotatingFileHandler(TimedRotatingFileHandler):
    def doRollover(self):
        super().doRollover()
        # Compress the most recent rotated log file
        import glob
        rotated_logs = sorted(glob.glob(f"{self.baseFilename}.*"), reverse=True)
        for rotated_log in rotated_logs:
            # Only compress non-gz log files that are not the active log file
            if not rotated_log.endswith('.gz') and rotated_log != self.baseFilename:
                try:
                    with open(rotated_log, 'rb') as f_in, gzip.open(rotated_log + '.gz', 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                    os.remove(rotated_log)
                    logging.getLogger("rulescrape").info(f"[rulescrape.GzTimedRotatingFileHandler] Compressed log file: {rotated_log} -> {rotated_log}.gz")
                except Exception as e:
                    logging.getLogger("rulescrape").warning(f"[rulescrape.GzTimedRotatingFileHandler] Failed to compress log file {rotated_log}: {e}")
                break

handler = GzTimedRotatingFileHandler(log_file, when='midnight', backupCount=7, encoding='utf-8', delay=True)
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s'))
logger = logging.getLogger()
logger.setLevel(logging.INFO)
# Remove all existing handlers (if any)
for h in logger.handlers[:]:
    logger.removeHandler(h)
logger.addHandler(handler)

def run_script(booru_type, tag, limit, multithread=False, max_workers=None):
    # Error feedback for GUI
    import queue
    error_queue = None
    try:
        from gui import error_queue as gui_error_queue
        error_queue = gui_error_queue
    except Exception:
        error_queue = None
    # Load user settings
    user_settings = load_user_settings()
    output_dir = os.path.join("images", booru_type)
    os.makedirs(output_dir, exist_ok=True)

    import time
    max_retries = 5
    backoff = 2
    attempt = 0
    posts = None
    while attempt < max_retries:
        try:
            posts = fetch_booru_posts(booru_type, tags=tag, limit=limit)
            break
        except Exception as e:
            err_str = str(e).lower()
            if ("429" in err_str or "rate limit" in err_str or "422" in err_str) and booru_type == "danbooru":
                wait_time = backoff ** attempt
                msg = f"Rate limit encountered ({e}). Retrying in {wait_time} seconds. Attempt {attempt+1}/{max_retries}."
                logging.getLogger("rulescrape").warning(f"[rulescrape.run_script] {msg}")
                logging.getLogger("gui").warning(f"[gui.rate_limit] {msg}")
                if error_queue:
                    error_queue.put(msg)
                time.sleep(wait_time)
                attempt += 1
                continue
            else:
                msg = f"Error fetching posts from {booru_type}: {e}"
                logging.getLogger("rulescrape").error(f"[rulescrape.run_script] {msg}")
                if error_queue:
                    error_queue.put(msg)
                return
    if posts is None:
        msg = f"Failed to fetch posts from {booru_type} after {max_retries} retries due to rate limiting or errors."
        logging.getLogger("rulescrape").error(f"[rulescrape.run_script] {msg}")
        logging.getLogger("gui").error(f"[gui.rate_limit] {msg}")
        if error_queue:
            error_queue.put(msg)
        return

    if not posts:
        msg = f"No posts returned from {booru_type} for tag '{tag}' and limit {limit}. Possible reasons: no results, API error, or invalid query."
        logging.getLogger("rulescrape").warning(f"[rulescrape.run_script] {msg}")
        if error_queue:
            error_queue.put(msg)
        return

    valid_images_processed = 0

    import hashlib
    def md5sum(filepath):
        hash_md5 = hashlib.md5()
        try:
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception:
            return None

    # Build a set of existing image hashes in output_dir
    existing_hashes = set()
    for root, dirs, files in os.walk(output_dir):
        for file in files:
            if file.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webm", ".mp4")):
                path = os.path.join(root, file)
                h = md5sum(path)
                if h:
                    existing_hashes.add(h)


    downloaded_files = set()

    def process_post(post):
        image_url = post.get('file_url')
        if not image_url or not image_url.startswith(('http://', 'https://')):
            msg = f"Skipping invalid post: {post}"
            logging.getLogger("rulescrape").warning(f"[rulescrape.run_script] {msg}")
            if error_queue:
                error_queue.put(msg)
            return False

        filename_part = image_url.split('/')[-1].split('?')[0]
        _, ext = os.path.splitext(filename_part)
        filename = os.path.join(output_dir, f"post_{post['id']}{ext if ext else '.jpg'}")

        temp_filename = filename + ".tmp"
        success = False
        try:
            download_image(post, image_url, output_dir)
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                os.rename(filename, temp_filename)
                file_hash = md5sum(temp_filename)
                if file_hash in existing_hashes:
                    msg = f"Duplicate image hash detected, skipping: {filename}"
                    logging.getLogger("rulescrape").info(f"[rulescrape.run_script] {msg}")
                    if error_queue:
                        error_queue.put(msg)
                    os.remove(temp_filename)
                    return False
                else:
                    os.rename(temp_filename, filename)
                    existing_hashes.add(file_hash)
                    success = True
        except Exception as e:
            msg = f"Error downloading image from {image_url}: {e}"
            logging.getLogger("rulescrape").error(f"[rulescrape.run_script] {msg}")
            if error_queue:
                error_queue.put(msg)
            if os.path.exists(temp_filename):
                os.remove(temp_filename)
            return False

        if success:
            downloaded_files.add(filename)
            return True
        return False

    if multithread:
        import concurrent.futures
        workers = max_workers if max_workers is not None else os.cpu_count() // 2 or 1
        logging.getLogger("rulescrape").info(f"[rulescrape.run_script] Using multithreaded download with {workers} workers.")
        valid_images_processed = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = []
            for post in posts:
                if valid_images_processed >= limit:
                    break
                future = executor.submit(process_post, post)
                futures.append(future)
            for future in concurrent.futures.as_completed(futures):
                if future.result():
                    valid_images_processed += 1
                if valid_images_processed >= limit:
                    break
    else:
        for post in posts:
            if valid_images_processed >= limit:
                logging.getLogger("rulescrape").info(f"[rulescrape.run_script] Reached limit of {limit} valid images. Stopping.")
                break
            if process_post(post):
                valid_images_processed += 1

    logging.getLogger("rulescrape").info(f"[rulescrape.run_script] Downloaded {valid_images_processed} images from {booru_type}.")

def load_user_settings():
    import multiprocessing
    cpu_threads = multiprocessing.cpu_count()
    default_workers = max(1, cpu_threads // 2)
    config = configparser.ConfigParser()
    default_settings = {
        'booru_type': 'rule34',
        'tag': '',
        'limit': 10,
        'anti_ai': False,
        'multithread': False,
        'org_method': 'By extension and first tag',
        'max_workers': default_workers,
        'skin': None,
        'window_width': 400,
        'window_height': 320
    }
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)
        settings = default_settings.copy()
        if 'Settings' in config:
            settings['booru_type'] = config['Settings'].get('booru_type', settings['booru_type'])
            settings['tag'] = config['Settings'].get('tag', settings['tag'])
            settings['limit'] = config['Settings'].getint('limit', settings['limit'])
            settings['anti_ai'] = config['Settings'].getboolean('anti_ai', settings['anti_ai'])
            settings['multithread'] = config['Settings'].getboolean('multithread', settings['multithread'])
            settings['org_method'] = config['Settings'].get('org_method', settings['org_method'])
            settings['max_workers'] = config['Settings'].getint('max_workers', settings['max_workers'])
        if 'UI' in config:
            settings['skin'] = config['UI'].get('skin', settings['skin'])
            settings['window_width'] = config['UI'].getint('window_width', settings['window_width'])
            settings['window_height'] = config['UI'].getint('window_height', settings['window_height'])
        return settings
    return default_settings


def save_user_settings(booru_type, tag, limit, anti_ai, multithread, org_method, skin=None, window_width=400, window_height=320):
    # Always update config file with latest settings
    import configparser
    config = configparser.ConfigParser()
    # Always preserve max_workers if present, otherwise use default
    import multiprocessing
    cpu_threads = multiprocessing.cpu_count()
    default_workers = max(1, cpu_threads // 2)
    prev_max_workers = default_workers
    if os.path.exists(CONFIG_FILE):
        prev_config = configparser.ConfigParser()
        prev_config.read(CONFIG_FILE)
        if 'Settings' in prev_config:
            prev_max_workers = prev_config['Settings'].get('max_workers', str(default_workers))

    # Write config with comments above each setting
    # Prevent placeholder tag from being saved
    tag_to_save = tag if tag.strip().lower() not in ["enter tag...", "enter tag..", "enter tag."] else ""
    config_lines = [
        "[Settings]",
        "# Which booru site to use (e.g. rule34, safebooru)",
        f"booru_type = {booru_type}",
        "# Tag to search for",
        f"tag = {tag_to_save}",
        "# Number of images to download",
        f"limit = {limit}",
        "# Exclude AI-generated content (True/False)",
        f"anti_ai = {anti_ai}",
        "# Enable multithreaded downloads (True/False)",
        f"multithread = {multithread}",
        "# Organization method for images",
        f"org_method = {org_method}",
        "# Number of threads for multithreaded downloads",
        f"max_workers = {prev_max_workers}",
        "",
        "[UI]",
        "# Skin/theme file for GUI",
        f"skin = {skin if skin is not None else 'None'}",
        "# GUI window width",
        f"window_width = {window_width}",
        "# GUI window height",
        f"window_height = {window_height}",
        ""
    ]

    with open(CONFIG_FILE, 'w') as configfile:
        configfile.write('\n'.join(config_lines))




if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="rulescrape: Download images from booru sites via CLI or GUI.")
    parser.add_argument('--booru_type', type=str, help='Booru type (e.g. rule34, danbooru, etc.)')
    parser.add_argument('--tag', type=str, help='Tag to search for')
    parser.add_argument('--limit', type=int, help='Number of images to download')
    parser.add_argument('--anti_ai', type=str, choices=['true', 'false'], help='Enable or disable anti-AI filtering (true/false)')
    parser.add_argument('--multithread', action='store_true', help='Enable multithreaded downloads')
    parser.add_argument('--max_workers', type=int, help='Number of threads/workers for multithreaded downloads')
    parser.add_argument('--org_method', type=str, help='Organization method for images')
    parser.add_argument('--skin', type=str, help='Skin file to use for GUI')
    parser.add_argument('--window_width', type=int, help='Window width for GUI')
    parser.add_argument('--window_height', type=int, help='Window height for GUI')
    parser.add_argument('--cli', action='store_true', help='Force CLI mode (do not launch GUI)')
    args = parser.parse_args()

    # If any CLI-relevant argument is provided or --cli is set, run in CLI mode
    cli_mode = args.cli or any([
        args.booru_type, args.tag, args.limit, args.anti_ai is not None, args.multithread, args.org_method, args.max_workers is not None
    ])

    if cli_mode:
        # Load settings, override with CLI args if provided
        settings = load_user_settings()
        booru_type = args.booru_type or settings.get('booru_type', 'rule34')
        tag = args.tag if args.tag is not None else settings.get('tag', '')
        limit = args.limit if args.limit is not None else settings.get('limit', 10)
        # anti_ai: allow true/false string, fallback to config
        if args.anti_ai is not None:
            anti_ai = args.anti_ai.lower() == 'true'
        else:
            anti_ai = settings.get('anti_ai', False)
        multithread = args.multithread if args.multithread else settings.get('multithread', False)
        org_method = args.org_method or settings.get('org_method', 'By extension and first tag')
        skin = args.skin or settings.get('skin', None)
        window_width = args.window_width if args.window_width is not None else settings.get('window_width', 400)
        window_height = args.window_height if args.window_height is not None else settings.get('window_height', 320)
        max_workers = args.max_workers if args.max_workers is not None else settings.get('max_workers', None)

        # Save settings for future GUI use
        save_user_settings(
            booru_type, tag, limit, anti_ai, multithread, org_method,
            skin=skin, window_width=window_width, window_height=window_height
        )
        # If max_workers is specified, update config file directly
        if max_workers is not None:
            import configparser
            config = configparser.ConfigParser()
            config.read(CONFIG_FILE)
            if 'Settings' not in config:
                config['Settings'] = {}
            config['Settings']['max_workers'] = str(max_workers)
            with open(CONFIG_FILE, 'w') as configfile:
                config.write(configfile)

        cli_log = logging.getLogger("rulescrape")
        cli_log.info(f"[CLI] Starting CLI mode: booru_type={booru_type}, tag={tag}, limit={limit}, anti_ai={anti_ai}, multithread={multithread}, max_workers={max_workers}")
        print(f"[rulescrape] Running in CLI mode: booru_type={booru_type}, tag={tag}, limit={limit}, anti_ai={anti_ai}, multithread={multithread}, max_workers={max_workers}")

        # Wrap run_script to add CLI log prefix to all log messages
        import functools
        orig_info = cli_log.info
        orig_warning = cli_log.warning
        orig_error = cli_log.error
        cli_log.info = lambda msg, *a, **kw: orig_info(f"[CLI] {msg}", *a, **kw)
        cli_log.warning = lambda msg, *a, **kw: orig_warning(f"[CLI] {msg}", *a, **kw)
        cli_log.error = lambda msg, *a, **kw: orig_error(f"[CLI] {msg}", *a, **kw)

        run_script(booru_type, tag, limit, multithread=multithread, max_workers=max_workers)

        # Restore original log methods
        cli_log.info = orig_info
        cli_log.warning = orig_warning
        cli_log.error = orig_error
        cli_log.info(f"[CLI] Finished CLI run.")
    else:
        from gui import main_gui
        main_gui()
