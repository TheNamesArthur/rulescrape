import os
import logging
import requests
from urllib.parse import urljoin
import xml.etree.ElementTree as ET
from html import unescape
import re
import string


# Module logger - will use the main application's logging configuration
logger = logging.getLogger("booru_api")

# HTML entity replacements for XML cleaning
HTML_ENTITY_REPLACEMENTS = {
    '&mdash;': '—', '&ndash;': '–', '&ldquo;': '"', '&rdquo;': '"',
    '&lsquo;': ''', '&rsquo;': ''', '&hellip;': '…', '&trade;': '™',
    '&copy;': '©', '&reg;': '®', '&nbsp;': ' ',
    '&#039;': "'", '&apos;': "'", '&quot;': '"', '&lt;': '<', '&gt;': '>',
    '&amp;': '&'
}

# API configuration for different booru sites
BOORU_APIS = {
    'rule34': {
        'url': "https://api.rule34.xxx/index.php?page=dapi&s=post&q=index",
        'params': lambda tags, limit, pid=0: {
            'tags': tags or '', 
            'limit': limit, 
            'json': 1, 
            'pid': pid
        },
        'headers': {'Accept': 'application/json'},
        'process': lambda data: data
    },
    'safebooru': {
        'url': "https://safebooru.org/index.php?page=dapi&s=post&q=index",
        'params': lambda tags, limit, pid=0: {
            'tags': tags or '', 
            'limit': limit, 
            'json': 1, 
            'pid': pid
        },
        'headers': {'Accept': 'application/json'},
        'process': lambda data: data
    },
    'danbooru': {
        'url': "https://danbooru.donmai.us/posts.json",
        'params': lambda tags, limit, pid=0: {
            'tags': tags or '', 
            'limit': limit, 
            'page': pid + 1  # Danbooru uses 1-based pages
        },
        'headers': {'Accept': 'application/json'},
        'process': lambda data: data  # Danbooru returns a list of posts
    },
    'yande.re': {
        'url': "https://yande.re/post.json",
        'params': lambda tags, limit, pid=0: {
            'tags': tags or '', 
            'limit': limit, 
            'page': pid + 1  # Yande.re uses 1-based pages
        },
        'headers': {'Accept': 'application/json'},
        'process': lambda data: data  # Yande.re returns a list of posts
    },
    'paheal': {
        'url': "https://rule34.paheal.net/api/danbooru/find_posts",
        'params': lambda tags, limit, pid=0: {
            'tags': tags or '', 
            'limit': limit, 
            'page': pid + 1  # Paheal uses 1-based pages
        },
        'headers': {'Accept': 'application/xml'},
        'process': lambda data: data  # Will need XML processing
    },
}

def _clean_xml_text(xml_text):
    """Clean XML text by removing invalid characters and fixing entities."""
    # Remove invalid XML characters (control characters except tab, newline, carriage return)
    cleaned = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', xml_text)
    
    # The key issue: replace &#039; with a temporary placeholder to avoid conflicts
    # We'll restore it as &apos; after other processing
    APOSTROPHE_PLACEHOLDER = '___APOSTROPHE___'
    cleaned = cleaned.replace('&#039;', APOSTROPHE_PLACEHOLDER)
    
    # Handle other numeric HTML entities (but not apostrophe)
    cleaned = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))) if int(m.group(1)) != 39 else APOSTROPHE_PLACEHOLDER, cleaned)
    cleaned = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: chr(int(m.group(1), 16)) if int(m.group(1), 16) != 39 else APOSTROPHE_PLACEHOLDER, cleaned)
    
    # Replace HTML entities that XML parser doesn't recognize
    for entity, replacement in HTML_ENTITY_REPLACEMENTS.items():
        if entity not in ['&#039;', '&apos;']:  # Skip apostrophe-related entities
            cleaned = cleaned.replace(entity, replacement)
    
    # Unescape remaining standard HTML entities (but apostrophe is protected by placeholder)
    try:
        cleaned = unescape(cleaned)
    except Exception:
        pass
    
    # Now replace the placeholder with proper XML apostrophe entity
    cleaned = cleaned.replace(APOSTROPHE_PLACEHOLDER, '&apos;')
    
    # Escape unescaped ampersands (but preserve XML entities)
    cleaned = re.sub(r'&(?![a-zA-Z0-9#]+;)', '&amp;', cleaned)
    
    # Fix truncated XML
    if not cleaned.strip().endswith('</posts>'):
        last_tag_end = cleaned.rfind('></tag>')
        if last_tag_end != -1:
            cleaned = cleaned[:last_tag_end + 7] + '</posts>'
        else:
            cleaned = cleaned.rstrip() + '</tag></posts>'
    
    return cleaned

def _fix_paheal_url(url):
    """Convert relative Paheal URLs to absolute URLs."""
    if url.startswith('//'):
        return 'https:' + url
    elif url.startswith('/'):
        return 'https://rule34.paheal.net' + url
    return url

def _parse_paheal_xml(xml_text):
    """Parse Paheal XML response with robust error handling."""
    try:
        # First attempt: parse as-is
        try:
            root = ET.fromstring(xml_text)
            return _extract_paheal_posts(root)
        except ET.ParseError:
            pass
        
        # Second attempt: clean the XML
        cleaned_xml = _clean_xml_text(xml_text)
        try:
            root = ET.fromstring(cleaned_xml)
            return _extract_paheal_posts(root)
        except ET.ParseError:
            pass
        
        # Third attempt: aggressive cleaning
        printable_chars = set(string.printable)
        printable_chars.update({'\u00A0', '\u2014', '\u2013', '\u201C', '\u201D', 
                               '\u2018', '\u2019', '\u2026', '\u2122', '\u00A9', '\u00AE'})
        
        aggressive_clean = ''.join(c for c in xml_text if c in printable_chars)
        aggressive_clean = _clean_xml_text(aggressive_clean)
        
        root = ET.fromstring(aggressive_clean)
        logger.info("[booru_api._parse_paheal_xml] Successfully parsed XML after aggressive cleaning")
        return _extract_paheal_posts(root)
        
    except Exception as e:
        error_context = xml_text[:1000] if len(xml_text) > 1000 else xml_text
        logger.error(f"[booru_api._parse_paheal_xml] Failed to parse XML: {e}\n"
                    f"First 1000 chars: {error_context}")
        return []

def _extract_paheal_posts(root):
    """Extract posts from parsed Paheal XML."""
    posts = []
    for post_elem in root.findall('.//tag'):
        post = dict(post_elem.attrib)
        if 'file_url' in post:
            post['file_url'] = _fix_paheal_url(post['file_url'])
        posts.append(post)
    return posts

def fetch_booru_posts(booru_type, tags=None, limit=10, pid=0):
    """
    Fetch posts from a booru API.
    
    Args:
        booru_type: Type of booru ('rule34', 'safebooru', 'danbooru', 'yande.re', 'paheal')
        tags: Search tags (optional)
        limit: Maximum number of posts to fetch
        pid: Page ID for pagination
        
    Returns:
        List of posts or empty list on error
    """
    api = BOORU_APIS.get(booru_type)
    if not api:
        logger.error(f"[booru_api.fetch_booru_posts] Unsupported booru type: {booru_type}")
        return []
    
    url = api['url']
    params = api['params'](tags, limit, pid)
    headers = api.get('headers', {})
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(
            f"[booru_api.fetch_booru_posts] Error fetching data from {booru_type} API: {e}\n"
            f"URL: {url}\nParams: {params}"
        )
        return []
    
    # Handle XML response for Paheal
    if booru_type == 'paheal':
        return _parse_paheal_xml(response.text)
    
    # Handle JSON response for other boorus
    try:
        data = response.json()
    except ValueError as e:
        logger.error(
            f"[booru_api.fetch_booru_posts] Invalid JSON response from {booru_type} API. Error: {e}\n"
            f"URL: {url}\nParams: {params}\nResponse text: {response.text[:500]}"
        )
        return []
    
    posts = api['process'](data)
    if not posts:
        logger.warning(
            f"[booru_api.fetch_booru_posts] Empty results from {booru_type} API.\n"
            f"URL: {url}\nParams: {params}\nResponse: {data}"
        )
    
    return posts

def download_image(post, image_url, output_dir):
    """
    Download an image from a URL and save it to the output directory.
    
    Args:
        post (dict): Post metadata dictionary containing 'id'
        image_url (str): URL of the image to download
        output_dir (str): Directory to save the image
        
    Returns:
        str: Path to downloaded file on success, None on failure
    """
    try:
        if not image_url or not image_url.startswith(('http://', 'https://')):
            logger.warning(f"[booru_api.download_image] Invalid image URL for post ID {post.get('id', 'unknown')}: {image_url}")
            return None

        response = requests.get(image_url, stream=True, timeout=30)
        response.raise_for_status()

        # Determine file extension from URL or content type
        extension = _get_file_extension(image_url, response.headers.get('Content-Type', ''))
        filename = os.path.join(output_dir, f"post_{post['id']}{extension}")
        
        # Download the file
        _download_with_progress(response, filename)
        
        logger.info(f"[booru_api.download_image] Downloaded image for post ID {post['id']} -> {filename}")
        return filename

    except requests.RequestException as e:
        logger.error(f"[booru_api.download_image] Failed to download image for post ID {post.get('id', 'unknown')}: {e}")
        return None
    except Exception as e:
        logger.error(f"[booru_api.download_image] Error saving image for post ID {post.get('id', 'unknown')}: {e}")
        return None

def _get_file_extension(image_url, content_type):
    """Determine file extension from URL or content type."""
    # Try to get extension from URL first
    filename_part = image_url.split('/')[-1].split('?')[0]
    _, ext = os.path.splitext(filename_part)
    
    if ext:
        return ext
    
    # Fallback to content type detection
    content_type_map = {
        'image/jpeg': '.jpg',
        'image/png': '.png', 
        'image/gif': '.gif',
        'image/webp': '.webp',
        'video/mp4': '.mp4',
        'video/webm': '.webm'
    }
    return content_type_map.get(content_type, '.jpg')

def _download_with_progress(response, filename):
    """Download response content to file with optional progress bar."""
    total_size = int(response.headers.get('content-length', 0))
    block_size = 8192  # 8KB chunks for better performance
    
    # Try to use tqdm for progress bar
    progress_bar = None
    try:
        from tqdm import tqdm
        progress_bar = tqdm(
            total=total_size, 
            unit='B', 
            unit_scale=True,
            unit_divisor=1024, 
            desc=f"Downloading {os.path.basename(filename)}"
        )
    except ImportError:
        if total_size > 0:
            logger.info(f"[booru_api._download_with_progress] Downloading {os.path.basename(filename)} ({total_size:,} bytes)")

    try:
        with open(filename, 'wb') as f:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=block_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    if progress_bar:
                        progress_bar.update(len(chunk))
                    elif total_size > 0 and downloaded % (block_size * 128) == 0:  # Log every 1MB
                        percent = (downloaded / total_size) * 100
                        logger.debug(f"Download progress: {percent:.1f}%")
    finally:
        if progress_bar:
            progress_bar.close()


def download_images_from_posts(posts, output_dir):
    """
    Download images from a list of posts to the specified output directory.
    
    Args:
        posts (list): List of post dictionaries containing image URLs
        output_dir (str): Directory to save downloaded images
        
    Returns:
        list: List of successfully downloaded file paths
    """
    if not posts:
        logger.warning("[booru_api.download_images_from_posts] No posts to download.")
        return []

    logger.info(f"[booru_api.download_images_from_posts] Starting download of {len(posts)} posts to {output_dir}")
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    downloaded_files = []
    for post in posts:
        image_url = post.get('image_url') or post.get('file_url')  # Support different URL field names
        if image_url:
            downloaded_file = download_image(post, image_url, output_dir)
            if downloaded_file:
                downloaded_files.append(downloaded_file)
        else:
            logger.warning(
                f"[booru_api.download_images_from_posts] No image URL found for post ID {post.get('id', 'unknown')}"
            )
    
    logger.info(f"[booru_api.download_images_from_posts] Successfully downloaded {len(downloaded_files)} out of {len(posts)} images")
    return downloaded_files
