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

def run_script(booru_type, tag, limit):
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
                logging.getLogger("rulescrape").warning(f"[rulescrape.run_script] Rate limit encountered ({e}). Retrying in {wait_time} seconds. Attempt {attempt+1}/{max_retries}.")
                # For GUI notification, log a special message
                logging.getLogger("gui").warning(f"[gui.rate_limit] Rate limit encountered for {booru_type}. Retrying in {wait_time} seconds. Attempt {attempt+1}/{max_retries}.")
                time.sleep(wait_time)
                attempt += 1
                continue
            else:
                logging.getLogger("rulescrape").error(f"[rulescrape.run_script] Error fetching posts from {booru_type}: {e}")
                return
    if posts is None:
        logging.getLogger("rulescrape").error(f"[rulescrape.run_script] Failed to fetch posts from {booru_type} after {max_retries} retries due to rate limiting or errors.")
        # For GUI notification, log a special message
        logging.getLogger("gui").error(f"[gui.rate_limit] Failed to fetch posts from {booru_type} after {max_retries} retries due to rate limiting or errors.")
        return

    if not posts:
        logging.getLogger("rulescrape").warning(f"[rulescrape.run_script] No posts returned from {booru_type} for tag '{tag}' and limit {limit}. Possible reasons: no results, API error, or invalid query.")
        return

    valid_images_processed = 0

    downloaded_files = set()
    for post in posts:
        image_url = post.get('file_url')
        if not image_url or not image_url.startswith(('http://', 'https://')):
            logging.getLogger("rulescrape").warning(f"[rulescrape.run_script] Skipping invalid post: {post}")
            continue

        filename_part = image_url.split('/')[-1].split('?')[0]
        _, ext = os.path.splitext(filename_part)
        filename = os.path.join(output_dir, f"post_{post['id']}{ext if ext else '.jpg'}")

        if filename in downloaded_files or (os.path.exists(filename) and os.path.getsize(filename) > 0):
            logging.getLogger("rulescrape").info(f"[rulescrape.run_script] Duplicate detected, skipping: {filename}")
            continue

        success = False
        try:
            download_image(post, image_url, output_dir)
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                success = True
        except Exception as e:
            logging.getLogger("rulescrape").error(f"[rulescrape.run_script] Error downloading image from {image_url}: {e}")
            continue

        if success:
            downloaded_files.add(filename)
            valid_images_processed += 1
            if valid_images_processed >= limit:
                logging.getLogger("rulescrape").info(f"[rulescrape.run_script] Reached limit of {limit} valid images. Stopping.")
                break

    logging.getLogger("rulescrape").info(f"[rulescrape.run_script] Downloaded {valid_images_processed} images from {booru_type}.")

def load_user_settings():
    import multiprocessing
    cpu_threads = multiprocessing.cpu_count()
    default_workers = max(1, cpu_threads // 2)
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
            settings['org_method'] = config['Settings'].get('org_method', 'By extension and first tag')
            settings['max_workers'] = config['Settings'].getint('max_workers', default_workers)
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
        'org_method': 'By extension and first tag',
        'max_workers': default_workers,
        'skin': None,
        'window_width': 400,
        'window_height': 320
    }


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
    config['Settings'] = {
        'booru_type': booru_type,
        'tag': tag,
        'limit': str(limit),
        'anti_ai': str(anti_ai),
        'multithread': str(multithread),
        'org_method': org_method,
        'max_workers': str(prev_max_workers)
    }
    config['UI'] = {
        'skin': skin or 'custom_skin_here.json',
        'window_width': str(window_width),
        'window_height': str(window_height)
    }
    with open(CONFIG_FILE, 'w') as configfile:
        config.write(configfile)



if __name__ == "__main__":
    from gui import main_gui
    main_gui()
