import requests
import os
import logging
import gzip
import shutil
from urllib.parse import urljoin

# Ensure logging is always configured to use a log file in the script's directory
def _get_log_dir():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir = os.path.join(script_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir

def _setup_logging():
    log_dir = _get_log_dir()
    log_file = os.path.join(log_dir, "rulescrape.log")
    if not getattr(_setup_logging, "configured", False):
        from logging.handlers import TimedRotatingFileHandler
        class GzTimedRotatingFileHandler(TimedRotatingFileHandler):
            def doRollover(self):
                super().doRollover()
                if self.backupCount > 0:
                    import glob
                    rotated_logs = sorted(glob.glob(f"{self.baseFilename}.*"), reverse=True)
                    for rotated_log in rotated_logs:
                        if not rotated_log.endswith('.gz') and rotated_log != self.baseFilename:
                            with open(rotated_log, 'rb') as f_in, gzip.open(rotated_log + '.gz', 'wb') as f_out:
                                shutil.copyfileobj(f_in, f_out)
                            os.remove(rotated_log)
                            break
        handler = GzTimedRotatingFileHandler(log_file, when='midnight', backupCount=7, encoding='utf-8', delay=True)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s'))
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        for h in logger.handlers[:]:
            logger.removeHandler(h)
        logger.addHandler(handler)
        _setup_logging.configured = True

_setup_logging()

BOORU_APIS = {
    'rule34': {
        'url': "https://api.rule34.xxx/index.php?page=dapi&s=post&q=index",
        'params': lambda tags, limit: {'tags': tags, 'limit': limit, 'json': 1},
        'headers': {'Accept': 'application/json'},
        'process': lambda data: data
    },
    'safebooru': {
        'url': "https://safebooru.org/index.php?page=dapi&s=post&q=index",
        'params': lambda tags, limit: {'tags': tags, 'limit': limit, 'json': 1},
        'headers': {'Accept': 'application/json'},
        'process': lambda data: data
    },
    'danbooru': {
        'url': "https://danbooru.donmai.us/posts.json",
        'params': lambda tags, limit: {'tags': tags or '', 'limit': limit},
        'headers': {'Accept': 'application/json'},
        'process': lambda data: data  # Danbooru returns a list of posts
    },
    # Add more booru types here
}

def fetch_booru_posts(booru_type, tags=None, limit=10):
    api = BOORU_APIS.get(booru_type)
    if not api:
        logging.getLogger("booru_api").error(f"[booru_api.fetch_booru_posts] Unsupported booru type: {booru_type}")
        return []
    url = api['url']
    params = api['params'](tags, limit)
    headers = api.get('headers', {})
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        logging.getLogger("booru_api").error(f"[booru_api.fetch_booru_posts] Error fetching data from {booru_type} API: {e}\nURL: {url}\nParams: {params}")
        return []
    try:
        data = response.json()
    except ValueError as e:
        logging.getLogger("booru_api").error(f"[booru_api.fetch_booru_posts] Invalid JSON response from {booru_type} API. Error: {e}\nURL: {url}\nParams: {params}\nResponse text: {response.text[:500]}")
        return []
    posts = api['process'](data)
    if not posts:
        logging.getLogger("booru_api").warning(f"[booru_api.fetch_booru_posts] Empty results from {booru_type} API.\nURL: {url}\nParams: {params}\nResponse: {data}")
    return posts

def download_image(post, image_url, output_dir):
    try:
        if not image_url or not image_url.startswith(('http://', 'https://')):
            logging.getLogger("booru_api").warning(f"[booru_api.download_image] Invalid image URL for post ID {post['id']}: {image_url}")
            return

        response = requests.get(image_url, stream=True, timeout=10)
        response.raise_for_status()

        content_type = response.headers.get('Content-Type', '')
        extension = ''

        # Remove query parameters from filename (for sancomplex and similar)
        filename_part = image_url.split('/')[-1].split('?')[0]
        _, ext = os.path.splitext(filename_part)
        if ext:
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

        from tqdm import tqdm
        with open(filename, 'wb') as f:
            with tqdm(total=total_size, unit='B', unit_scale=True, unit_divisor=1024, desc=f"Downloading {filename}") as pbar:
                for chunk in response.iter_content(chunk_size=block_size):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))

        logging.getLogger("booru_api").info(f"[booru_api.download_image] Downloaded image for post ID {post['id']} -> {filename}")

    except requests.RequestException as e:
        logging.getLogger("booru_api").error(f"[booru_api.download_image] Failed to download image for post ID {post['id']}: {e}")
    except Exception as e:
        logging.getLogger("booru_api").error(f"[booru_api.download_image] Error saving image for post ID {post['id']}: {e}")
