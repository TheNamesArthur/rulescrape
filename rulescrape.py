import os
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
    
    # Get organization method from user settings
    org_method = user_settings.get('org_method', 'By extension and first tag')

    import time
    max_retries = 5
    backoff = 2
    
    # Initialize duplication checker and scan existing images
    from dupe_check import get_dupe_checker
    dupe_checker = get_dupe_checker("images")
    
    # Scan existing images before starting download
    dupe_checker.reset_duplicate_count()
    scanned_count = dupe_checker.scan_existing_images()
    logging.getLogger("rulescrape").info(f"[rulescrape.run_script] Scanned {scanned_count} existing images for duplicate detection")

    downloaded_files = set()
    valid_images_processed = 0
    duplicates_in_session = 0  # Track duplicates found during this session
    
    # Helper function to get destination directory based on organization method
    def get_dest_dir(post):
        image_url = post.get('file_url', '')
        ext = os.path.splitext(image_url.split('?')[0])[1].lower().replace('.', '')
        if ext not in ["jpg", "jpeg", "png", "gif", "webm", "mp4", "bmp", "svg"]:
            ext = "other"
        
        # Get tags - handle different booru tag formats
        if booru_type == "danbooru":
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
    
    # We'll keep fetching more posts until we get the required number of unique images
    posts_fetched = 0
    fetch_limit = min(limit * 2, 1000)  # Start by fetching 2x the limit, but respect API limits
    max_fetch_attempts = 20  # Allow more attempts for high limits
    current_page = 0  # Track pagination for APIs that support it
    
    while valid_images_processed < limit and posts_fetched < max_fetch_attempts:
        attempt = 0
        posts = None
        
        # Fetch posts with retry logic
        while attempt < max_retries:
            try:
                # Use full API limit for Rule34 (1000), smaller limits for others
                if booru_type == "rule34":
                    current_limit = min(fetch_limit, 1000)  # Rule34 supports up to 1000 posts per request
                else:
                    current_limit = min(fetch_limit, 100)   # Conservative limit for other APIs
                posts = fetch_booru_posts(booru_type, tags=tag, limit=current_limit, pid=current_page)
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
            msg = f"No posts returned from {booru_type} for tag '{tag}' and limit {current_limit}. Possible reasons: no results, API error, or invalid query."
            logging.getLogger("rulescrape").warning(f"[rulescrape.run_script] {msg}")
            if error_queue:
                error_queue.put(msg)
            return
        
        posts_fetched += 1
        posts_to_process = list(posts)  # Convert to list for easier manipulation

        def process_post(post):
            image_url = post.get('file_url')
            if not image_url or not image_url.startswith(('http://', 'https://')):
                msg = f"Skipping invalid post: {post}"
                logging.getLogger("rulescrape").warning(f"[rulescrape.run_script] {msg}")
                if error_queue:
                    error_queue.put(msg)
                return False

            # Get the proper destination directory based on organization method
            dest_dir = get_dest_dir(post)
            os.makedirs(dest_dir, exist_ok=True)
            
            filename_part = image_url.split('/')[-1].split('?')[0]
            _, ext = os.path.splitext(filename_part)
            filename = os.path.join(dest_dir, f"post_{post['id']}{ext if ext else '.jpg'}")

            # Check if file already exists - if so, check if it's a duplicate
            if os.path.exists(filename):
                if dupe_checker.is_duplicate(filename):
                    msg = f"Duplicate image already exists, skipping: {filename}"
                    logging.getLogger("rulescrape").info(f"[rulescrape.run_script] {msg}")
                    if error_queue:
                        error_queue.put(msg)
                    return "duplicate"
                else:
                    # File exists but isn't in our hash cache - this shouldn't happen but let's be safe
                    msg = f"File exists but not recognized as duplicate, re-downloading: {filename}"
                    logging.getLogger("rulescrape").warning(f"[rulescrape.run_script] {msg}")

            temp_filename = filename + ".tmp"
            success = False
            try:
                download_image(post, image_url, dest_dir)
                if os.path.exists(filename) and os.path.getsize(filename) > 0:
                    os.rename(filename, temp_filename)
                    
                    # Check for duplicates using the new duplication checker
                    if dupe_checker.is_duplicate(temp_filename):
                        msg = f"Duplicate image detected after download, skipping: {filename}"
                        logging.getLogger("rulescrape").info(f"[rulescrape.run_script] {msg}")
                        if error_queue:
                            error_queue.put(msg)
                        os.remove(temp_filename)
                        return "duplicate"
                    else:
                        # Not a duplicate, keep the file
                        os.rename(temp_filename, filename)
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
                return "success"
            return "error"

        # Process posts until we reach the desired limit
        if multithread:
            import concurrent.futures
            from threading import Lock
            progress_lock = Lock()  # Add lock for thread-safe progress tracking
            workers = max_workers if max_workers is not None else os.cpu_count() // 2 or 1
            logging.getLogger("rulescrape").info(f"[rulescrape.run_script] Using multithreaded download with {workers} workers.")
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                post_index = 0
                active_futures = {}
                
                # Continue processing posts until we reach the limit
                while valid_images_processed < limit and post_index < len(posts_to_process):
                    # Submit new posts while we have worker capacity and haven't reached limit
                    while len(active_futures) < workers and post_index < len(posts_to_process) and valid_images_processed < limit:
                        future = executor.submit(process_post, posts_to_process[post_index])
                        active_futures[future] = post_index
                        post_index += 1
                    
                    # Check for completed downloads
                    if active_futures:
                        # Wait for at least one to complete
                        done_futures = concurrent.futures.as_completed(active_futures.keys(), timeout=1)
                        try:
                            for future in done_futures:
                                result = future.result()
                                if result == "success":
                                    with progress_lock:  # Thread-safe increment
                                        valid_images_processed += 1
                                        current_count = valid_images_processed
                                    logging.getLogger("rulescrape").info(f"[rulescrape.run_script] Downloaded {current_count}/{limit} unique images")
                                elif result == "duplicate":
                                    with progress_lock:  # Thread-safe increment
                                        duplicates_in_session += 1
                                
                                # Remove completed future
                                del active_futures[future]
                                
                                # Stop if we've reached our limit
                                if valid_images_processed >= limit:
                                    break
                        except concurrent.futures.TimeoutError:
                            # No futures completed in timeout, continue
                            pass
                
                # Wait for any remaining active futures to complete, but don't count towards limit
                for future in active_futures:
                    try:
                        result = future.result(timeout=5)  # Wait up to 5 seconds for cleanup
                        if result == "duplicate":
                            with progress_lock:
                                duplicates_in_session += 1
                    except:
                        pass
                        
                # Check if we processed all posts in this batch but haven't reached the limit
                # If so, the outer loop will fetch more posts from the next page
        else:
            for post in posts_to_process:
                if valid_images_processed >= limit:
                    logging.getLogger("rulescrape").info(f"[rulescrape.run_script] Reached limit of {limit} valid images. Stopping.")
                    break
                result = process_post(post)
                if result == "success":
                    valid_images_processed += 1
                    logging.getLogger("rulescrape").info(f"[rulescrape.run_script] Downloaded {valid_images_processed}/{limit} unique images")
                elif result == "duplicate":
                    duplicates_in_session += 1
        
        # If we've reached our target, break out of the fetch loop
        if valid_images_processed >= limit:
            break
            
        # If we haven't gotten enough unique images, try fetching more
        if valid_images_processed < limit:
            remaining_needed = limit - valid_images_processed
            
            # Be more aggressive with fetch limit if we're seeing many duplicates
            if duplicates_in_session > remaining_needed:
                # High duplicate rate - fetch much more
                if booru_type == "rule34":
                    fetch_limit = min(remaining_needed * 5, 1000)  # Use Rule34's full API limit
                else:
                    fetch_limit = max(remaining_needed * 5, 100)
            else:
                # Normal duplicate rate - fetch 2x what we need
                if booru_type == "rule34":
                    fetch_limit = min(remaining_needed * 2, 1000)  # Use Rule34's full API limit
                else:
                    fetch_limit = max(remaining_needed * 2, 20)
                
            current_page += 1  # Move to next page to get different posts
            logging.getLogger("rulescrape").info(f"[rulescrape.run_script] Need {remaining_needed} more unique images, fetching {fetch_limit} more posts from page {current_page}... (duplicates so far: {duplicates_in_session})")

    # Log duplication summary
    dupe_checker.log_session_summary()
    duplicates_found = dupe_checker.get_duplicate_count()
    
    logging.getLogger("rulescrape").info(f"[rulescrape.run_script] Download completed: {valid_images_processed} new images downloaded, {duplicates_found} duplicates skipped from {booru_type}.")

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
