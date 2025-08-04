"""
Core modules for Rulescrape application.

This package contains all the core functionality for the Rulescrape image downloader:
- API interfaces for various booru sites
- Download management and file organization
- Duplicate detection and image processing
- Blacklist management and filtering
- GUI components and interfaces
- Thumbnail caching and preview systems
- Animation handling and display

All modules are designed to work together to provide a comprehensive
image downloading and management system.
"""

# Version information
__version__ = "1.5"
__author__ = "TheNamesArthur"

# Import core functionality for easier access
from .download import run_download, DownloadManager
from .blacklist import get_blacklist_manager, filter_blacklisted_posts
from .dupe_check import get_dupe_checker
from .booru_api import fetch_booru_posts, download_image

__all__ = [
    'run_download',
    'DownloadManager', 
    'get_blacklist_manager',
    'filter_blacklisted_posts',
    'get_dupe_checker',
    'fetch_booru_posts',
    'download_image'
]
