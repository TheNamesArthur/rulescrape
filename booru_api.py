import os
import logging
import requests
from urllib.parse import urljoin


# Module logger - will use the main application's logging configuration
logger = logging.getLogger("booru_api")

# API configuration for different booru sites
BOORU_APIS = {
    'rule34': {
        'url': "https://api.rule34.xxx/index.php?page=dapi&s=post&q=index",
        'params': lambda tags, limit, pid=0: {
            'tags': tags, 
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
            'tags': tags, 
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
        try:
            import xml.etree.ElementTree as ET
            from html import unescape
            import re
            
            # Clean up the XML by removing or escaping problematic characters
            cleaned_xml = response.text
            
            # First, try to parse as-is
            try:
                root = ET.fromstring(cleaned_xml)
                posts = []
                # Paheal uses <tag> elements instead of <post>
                for post_elem in root.findall('.//tag'):
                    post = {}
                    for attr in post_elem.attrib:
                        post[attr] = post_elem.attrib[attr]
                    # Convert essential attributes to expected format
                    if 'file_url' in post:
                        # Paheal might have relative URLs, make them absolute
                        if post['file_url'].startswith('//'):
                            post['file_url'] = 'https:' + post['file_url']
                        elif post['file_url'].startswith('/'):
                            post['file_url'] = 'https://rule34.paheal.net' + post['file_url']
                    posts.append(post)
                return posts
            except ET.ParseError:
                # If direct parsing fails, try cleaning the XML
                pass
            
            # Remove or replace invalid XML characters (control characters except tab, newline, carriage return)
            cleaned_xml = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', cleaned_xml)
            
            # Replace common problematic entities and characters
            # First unescape any HTML entities that might be properly encoded
            try:
                cleaned_xml = unescape(cleaned_xml)
            except Exception:
                pass
            
            # Then escape any remaining & characters that aren't part of proper entities
            cleaned_xml = re.sub(r'&(?![a-zA-Z0-9#]+;)', '&amp;', cleaned_xml)
            
            # Try to fix truncated XML by ensuring it ends properly
            if not cleaned_xml.strip().endswith('</posts>'):
                # Find the last complete <tag> element
                last_tag_end = cleaned_xml.rfind('></tag>')
                if last_tag_end != -1:
                    cleaned_xml = cleaned_xml[:last_tag_end + 7] + '</posts>'
                else:
                    # If no complete tag found, add closing tags
                    cleaned_xml = cleaned_xml.rstrip() + '</tag></posts>'
            
            # Parse the cleaned XML
            root = ET.fromstring(cleaned_xml)
            posts = []
            # Paheal uses <tag> elements instead of <post>
            for post_elem in root.findall('.//tag'):
                post = {}
                for attr in post_elem.attrib:
                    post[attr] = post_elem.attrib[attr]
                # Convert essential attributes to expected format
                if 'file_url' in post:
                    # Paheal might have relative URLs, make them absolute
                    if post['file_url'].startswith('//'):
                        post['file_url'] = 'https:' + post['file_url']
                    elif post['file_url'].startswith('/'):
                        post['file_url'] = 'https://rule34.paheal.net' + post['file_url']
                posts.append(post)
            return posts
        except Exception as e:
            logger.error(
                f"[booru_api.fetch_booru_posts] Error parsing XML from {booru_type}: {e}\n"
                f"Response text: {response.text[:500]}"
            )
            return []
    
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
        post: Post metadata dictionary containing 'id'
        image_url: URL of the image to download
        output_dir: Directory to save the image
    """
    try:
        if not image_url or not image_url.startswith(('http://', 'https://')):
            logger.warning(
                f"[booru_api.download_image] Invalid image URL for post ID {post['id']}: {image_url}"
            )
            return

        response = requests.get(image_url, stream=True, timeout=10)
        response.raise_for_status()

        # Determine file extension from URL or content type
        content_type = response.headers.get('Content-Type', '')
        extension = ''

        # Remove query parameters from filename (for complex URLs)
        filename_part = image_url.split('/')[-1].split('?')[0]
        _, ext = os.path.splitext(filename_part)
        
        if ext:
            extension = ext
        else:
            # Fallback to content type detection
            content_type_map = {
                'image/jpeg': '.jpg',
                'image/png': '.png',
                'image/gif': '.gif',
                'video/mp4': '.mp4'
            }
            extension = content_type_map.get(content_type, '.jpg')

        filename = os.path.join(output_dir, f"post_{post['id']}{extension}")
        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024

        # Download with progress bar
        from tqdm import tqdm
        with open(filename, 'wb') as f:
            with tqdm(total=total_size, unit='B', unit_scale=True, unit_divisor=1024, 
                     desc=f"Downloading {filename}") as pbar:
                for chunk in response.iter_content(chunk_size=block_size):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))

        logger.info(
            f"[booru_api.download_image] Downloaded image for post ID {post['id']} -> {filename}"
        )

    except requests.RequestException as e:
        logger.error(
            f"[booru_api.download_image] Failed to download image for post ID {post['id']}: {e}"
        )
    except Exception as e:
        logger.error(
            f"[booru_api.download_image] Error saving image for post ID {post['id']}: {e}"
        )
