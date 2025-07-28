"""
Rulescrape: Download images from booru-style imageboards.

This module provides both CLI and GUI interfaces for downloading images from various
booru sites including rule34, safebooru, danbooru, and yande.re. Features include
tag-based filtering, duplicate detection, multi-threaded downloads, and theme support.
"""

import os
import sys
import json
import gzip
import shutil
import logging
import argparse
import configparser
import multiprocessing
from logging.handlers import TimedRotatingFileHandler


def get_base_path():
    """
    Get the base path for the application (handles both script and frozen executable).
    
    Returns:
        str: Base directory path for the application
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

# Application configuration
script_dir = get_base_path()
log_dir = os.path.join("logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "rulescrape.log")

# Config file for user settings
CONFIG_FILE = os.path.join('user_settings.config')

# Skins support: create skins folder if not exists
skins_dir = os.path.join("skins")
os.makedirs(skins_dir, exist_ok=True)

def load_skin():
    """
    Load skin configuration from JSON files in skins directory.
    
    Returns:
        dict or None: Skin configuration dictionary or None if no skin found
    """
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
    """
    Custom TimedRotatingFileHandler that automatically compresses rotated log files.
    
    This handler extends the standard TimedRotatingFileHandler to automatically
    compress rotated log files using gzip, saving disk space while maintaining
    log history.
    """
    
    def doRollover(self):
        """Perform log rollover and compress the rotated file."""
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
    """
    Run the image download script with specified parameters.
    
    Args:
        booru_type (str): Type of booru site (e.g., 'rule34', 'danbooru')
        tag (str): Tag to search for
        limit (int): Maximum number of images to download
        multithread (bool): Whether to use multi-threaded downloads
        max_workers (int, optional): Number of worker threads
        
    Returns:
        bool: True if download completed successfully, False otherwise
    """
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
    output_dir = os.path.join(user_settings.get('output_dir', 'images'), booru_type)
    os.makedirs(output_dir, exist_ok=True)
    
    # Get organization method from user settings
    org_method = user_settings.get('org_method', 'By extension and first tag')
    
    # Initialize duplication checker and scan existing images
    from dupe_check import get_dupe_checker
    dupe_checker = get_dupe_checker(user_settings.get('output_dir', 'images'))
    
    # Scan existing images before starting download
    dupe_checker.reset_duplicate_count()
    scanned_count = dupe_checker.scan_existing_images()
    logging.getLogger("rulescrape").info(f"[rulescrape.run_script] Scanned {scanned_count} existing images for duplicate detection")

    # Use the unified download module
    from download import run_download
    
    success = run_download(
        booru_type=booru_type,
        tag=tag,
        limit=limit,
        output_dir=output_dir,
        org_method=org_method,
        dupe_checker=dupe_checker,
        multithread=multithread,
        max_workers=max_workers,
        error_queue=error_queue
    )
    
    # Log duplication summary
    dupe_checker.log_session_summary()
    
    if not success:
        logging.getLogger("rulescrape").error(f"[rulescrape.run_script] Download failed.")
    
    return success

def load_user_settings():
    """
    Load user settings from configuration file.
    
    Returns:
        dict: Dictionary containing user settings with defaults for missing values
    """
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
        'output_dir': 'images',
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
            settings['output_dir'] = config['Settings'].get('output_dir', settings['output_dir'])
        if 'UI' in config:
            settings['skin'] = config['UI'].get('skin', settings['skin'])
            settings['window_width'] = config['UI'].getint('window_width', settings['window_width'])
            settings['window_height'] = config['UI'].getint('window_height', settings['window_height'])
        return settings
    return default_settings


def save_user_settings(booru_type, tag, limit, anti_ai, multithread, org_method, output_dir='images', skin=None, window_width=400, window_height=320):
    """
    Save user settings to configuration file.
    
    Args:
        booru_type (str): Type of booru site
        tag (str): Search tag
        limit (int): Download limit
        anti_ai (bool): Whether to exclude AI content
        multithread (bool): Whether to use multi-threading
        org_method (str): File organization method
        output_dir (str): Output directory for images
        skin (str, optional): Skin file name
        window_width (int): GUI window width
        window_height (int): GUI window height
    """
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
        "# Custom output directory for images (default: images)",
        f"output_dir = {output_dir}",
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
        output_dir = settings.get('output_dir', 'images')
        skin = args.skin or settings.get('skin', None)
        window_width = args.window_width if args.window_width is not None else settings.get('window_width', 400)
        window_height = args.window_height if args.window_height is not None else settings.get('window_height', 320)
        max_workers = args.max_workers if args.max_workers is not None else settings.get('max_workers', None)

        # Save settings for future GUI use
        save_user_settings(
            booru_type, tag, limit, anti_ai, multithread, org_method, output_dir,
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
