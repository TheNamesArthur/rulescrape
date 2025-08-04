"""
Unified download module for rulescrape.
Handles both CLI and GUI downloads with consistent behavior.
"""

import os
import time
import logging
import concurrent.futures
from threading import Lock

from .booru_api import fetch_booru_posts, download_image


# Constants for file organization and processing
SUPPORTED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webm", "mp4", "bmp", "svg"}
DEFAULT_EXTENSION = "jpg"
OTHER_EXTENSION = "other"

# API limits for different booru sites
API_LIMITS = {
    "rule34": 1000,
    "danbooru": 100,
    "safebooru": 100,
    "yande.re": 100,
    "paheal": 100
}

# Organization methods
ORG_METHODS = {
    "By extension and first tag": lambda ext, tag_list: (ext, tag_list[0] if tag_list else "untagged"),
    "By extension only": lambda ext, tag_list: (ext,),
    "Flat (no folders)": lambda ext, tag_list: (),
    "By tag only": lambda ext, tag_list: (tag_list[0] if tag_list else "untagged",)
}


def _get_image_url_for_extension(post, booru_type):
    """
    Get the appropriate image URL for file extension extraction.
    
    Args:
        post (dict): Post metadata dictionary
        booru_type (str): Type of booru site
        
    Returns:
        str: Image URL for extension extraction
    """
    if booru_type == 'paheal':
        # Paheal file_url doesn't have extension, use file_name instead
        file_name = post.get('file_name', '')
        return file_name.split('?')[0]  # Strip URL parameters
    return post.get('file_url', '')


def _extract_file_extension(image_url):
    """
    Extract file extension from image URL.
    
    Args:
        image_url (str): Image URL
        
    Returns:
        str: File extension without dot, or 'other' if not supported
    """
    ext = os.path.splitext(image_url.split('?')[0])[1].lower().replace('.', '')
    return ext if ext in SUPPORTED_EXTENSIONS else OTHER_EXTENSION


def _get_tag_list(post, booru_type):
    """
    Extract tag list from post based on booru type.
    
    Args:
        post (dict): Post metadata dictionary
        booru_type (str): Type of booru site
        
    Returns:
        list: List of tags
    """
    if booru_type == "danbooru":
        tags = post.get('tag_string', '')
    elif booru_type == "paheal":
        tags = post.get('tags', '')
    else:
        tags = post.get('tags', '')
    
    return tags.split() if isinstance(tags, str) else []


def _build_directory_path(output_dir, org_method, ext, tag_list):
    """
    Build directory path based on organization method.
    
    Args:
        output_dir (str): Base output directory
        org_method (str): Organization method
        ext (str): File extension
        tag_list (list): List of tags
        
    Returns:
        str: Full directory path
    """
    path_components = ORG_METHODS.get(org_method, ORG_METHODS["By extension and first tag"])(ext, tag_list)
    return os.path.join(output_dir, *path_components)


class DownloadManager:
    """
    Manages image downloads with support for both single-threaded and multi-threaded operations.
    
    This class handles the complete download workflow including:
    - Fetching posts from booru APIs with retry logic
    - Organizing files based on user preferences  
    - Duplicate detection and prevention
    - Progress reporting for GUI integration
    - Multi-threaded downloads for improved performance
    
    Attributes:
        booru_type (str): Type of booru site to download from
        tag (str): Search tag for filtering images
        limit (int): Maximum number of images to download
        output_dir (str): Directory to save downloaded images
        org_method (str): Organization method for file structure
        dupe_checker: Instance for duplicate detection
        multithread (bool): Whether to use multi-threaded downloads
        max_workers (int): Number of worker threads for multi-threaded downloads
        error_queue: Queue for error messages (GUI integration)
        progress_callback: Callback function for progress updates
    """
    
    def __init__(self, booru_type, tag, limit, output_dir, org_method, dupe_checker, 
                 multithread=False, max_workers=None, error_queue=None, progress_callback=None):
        # Basic configuration
        self.booru_type = booru_type
        self.tag = tag
        self.limit = limit
        self.output_dir = output_dir
        self.org_method = org_method
        self.dupe_checker = dupe_checker
        
        # Threading configuration
        self.multithread = multithread
        self.max_workers = max_workers if max_workers is not None else os.cpu_count() // 2 or 1
        self.error_queue = error_queue
        self.progress_callback = progress_callback
        
        # Progress tracking
        self.valid_images_processed = 0
        self.duplicates_in_session = 0
        self.downloaded_files = set()
        self.progress_lock = Lock()
        
        # Cancellation control
        self.cancelled = False
        self.paused = False
        self.cancel_lock = Lock()
        
        # Fetch control parameters
        self.posts_fetched = 0
        self.max_fetch_attempts = 20
        self.current_page = 0
        self.max_retries = 5
        self.backoff = 2
        
    def report_progress(self, progress_value):
        """Report progress to GUI if callback is provided."""
        if self.progress_callback and callable(self.progress_callback):
            try:
                self.progress_callback(progress_value)
            except Exception as e:
                self.log_message("WARNING", f"Progress callback error: {e}")
    
    def cancel(self):
        """Cancel the download operation."""
        with self.cancel_lock:
            self.cancelled = True
            self.paused = False
            self.log_message("info", "Download cancellation requested")
    
    def pause(self):
        """Pause the download operation."""
        with self.cancel_lock:
            self.paused = True
            self.log_message("info", "Download pause requested")
    
    def resume(self):
        """Resume the download operation."""
        with self.cancel_lock:
            self.paused = False
            self.log_message("info", "Download resumed")
    
    def is_cancelled(self):
        """Check if download has been cancelled."""
        with self.cancel_lock:
            return self.cancelled
    
    def is_paused(self):
        """Check if download is paused."""
        with self.cancel_lock:
            return self.paused
    
    def wait_if_paused(self):
        """Wait while the download is paused."""
        import time
        while self.is_paused() and not self.is_cancelled():
            time.sleep(0.1)
        
    def log_message(self, level, message):
        """
        Log a message and optionally send to error queue.
        
        Args:
            level: Logging level ('info', 'warning', 'error')
            message: Message to log
        """
        logger = logging.getLogger("rulescrape")
        getattr(logger, level)(f"[download] {message}")
        
        if self.error_queue and level in ['warning', 'error']:
            self.error_queue.put(message)
    
    def get_dest_dir(self, post):
        """
        Get destination directory based on organization method.
        
        Args:
            post (dict): Post metadata dictionary
            
        Returns:
            str: Destination directory path
        """
        # Extract file extension
        image_url = _get_image_url_for_extension(post, self.booru_type)
        ext = _extract_file_extension(image_url)
        
        # Extract tag list
        tag_list = _get_tag_list(post, self.booru_type)
        
        # Build directory path
        return _build_directory_path(self.output_dir, self.org_method, ext, tag_list)
    
    def process_post(self, post):
        """
        Process a single post - download and check for duplicates.
        
        Args:
            post (dict): Post metadata dictionary
            
        Returns:
            str: Result status ('success', 'duplicate', 'error')
        """
        # Get image URL - both paheal and other boorus use file_url
        image_url = post.get('file_url')
            
        if not image_url or not image_url.startswith(('http://', 'https://')):
            self.log_message('warning', f"Skipping post {post.get('id', 'unknown')} - invalid URL: {image_url}")
            return "error"

        # Get the proper destination directory based on organization method
        dest_dir = self.get_dest_dir(post)
        os.makedirs(dest_dir, exist_ok=True)
        
        # Build filename with proper extension
        # For paheal, use file_name which contains the extension, for others use URL
        if self.booru_type == 'paheal' and 'file_name' in post:
            filename_part = post['file_name'].split('?')[0]  # Strip URL parameters from file_name too
        else:
            filename_part = image_url.split('/')[-1].split('?')[0]
        
        _, ext = os.path.splitext(filename_part)
        filename = os.path.join(dest_dir, f"post_{post['id']}{ext or '.jpg'}")

        # Check if file already exists
        if os.path.exists(filename):
            if self.dupe_checker.is_duplicate(filename):
                self.log_message('info', f"Duplicate image already exists, skipping: {os.path.basename(filename)}")
                return "duplicate"
            else:
                # File exists but isn't in our hash cache - re-download to be safe
                self.log_message('warning', f"File exists but not in duplicate cache, re-downloading: {os.path.basename(filename)}")

        # Download with temporary filename for atomic operation
        return self._download_and_verify(post, image_url, filename)
    
    def _download_and_verify(self, post, image_url, filename):
        """
        Download image and verify it's not a duplicate.
        
        Args:
            post (dict): Post metadata
            image_url (str): URL to download from
            filename (str): Target filename
            
        Returns:
            str: Result status ('success', 'duplicate', 'error')
        """
        temp_filename = filename + ".tmp"
        
        try:
            # Download to temporary location
            dest_dir = os.path.dirname(filename)
            downloaded_file = download_image(post, image_url, dest_dir)
            
            if not downloaded_file or not os.path.exists(downloaded_file):
                self.log_message('error', f"Download failed for post {post.get('id', 'unknown')}")
                return "error"
            
            # If download_image created a different filename, handle it
            if downloaded_file != filename:
                if os.path.exists(filename):
                    os.remove(filename)  # Remove any existing file
                os.rename(downloaded_file, temp_filename)
            else:
                os.rename(filename, temp_filename)
            
            # Verify file size
            if os.path.getsize(temp_filename) == 0:
                self.log_message('warning', f"Downloaded file is empty for post {post.get('id', 'unknown')}")
                os.remove(temp_filename)
                return "error"
                
            # Check for duplicates
            if self.dupe_checker.is_duplicate(temp_filename):
                self.log_message('info', f"Duplicate detected after download, removing: {os.path.basename(filename)}")
                os.remove(temp_filename)
                return "duplicate"
            
            # Move to final location
            os.rename(temp_filename, filename)
            self.downloaded_files.add(filename)
            return "success"
            
        except Exception as e:
            self.log_message('error', f"Error processing post {post.get('id', 'unknown')}: {e}")
            # Clean up temporary file
            if os.path.exists(temp_filename):
                try:
                    os.remove(temp_filename)
                except:
                    pass
            return "error"
    
    def fetch_posts(self, fetch_limit):
        """
        Fetch posts from the booru API with retry logic and blacklist filtering.
        
        Args:
            fetch_limit (int): Maximum number of posts to fetch
            
        Returns:
            list or None: List of posts or None on failure
        """
        # Determine API limit for this booru type
        api_limit = API_LIMITS.get(self.booru_type, 100)
        current_limit = min(fetch_limit, api_limit)
        
        for attempt in range(self.max_retries):
            try:
                posts = fetch_booru_posts(
                    self.booru_type, 
                    tags=self.tag, 
                    limit=current_limit, 
                    pid=self.current_page
                )
                
                if posts is not None:
                    # Apply blacklist filtering
                    from .blacklist import filter_blacklisted_posts
                    original_count = len(posts)
                    filtered_posts = filter_blacklisted_posts(posts, self.booru_type)
                    
                    if len(filtered_posts) < original_count:
                        filtered_count = original_count - len(filtered_posts)
                        self.log_message(
                            'info', 
                            f"Blacklist filtered {filtered_count} posts from {original_count} fetched"
                        )
                    
                    return filtered_posts
                    
            except Exception as e:
                if self._is_rate_limit_error(e) and self.booru_type == "danbooru":
                    wait_time = self.backoff ** attempt
                    self.log_message(
                        'warning', 
                        f"Rate limit encountered ({e}). Retrying in {wait_time}s. "
                        f"Attempt {attempt+1}/{self.max_retries}."
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    self.log_message('error', f"Error fetching posts from {self.booru_type}: {e}")
                    return None
        
        # All retries exhausted
        self.log_message(
            'error', 
            f"Failed to fetch posts from {self.booru_type} after {self.max_retries} retries."
        )
        return None
    
    def _is_rate_limit_error(self, error):
        """Check if error indicates rate limiting."""
        err_str = str(error).lower()
        return any(indicator in err_str for indicator in ["429", "rate limit", "422"])
    
    def process_posts_multithreaded(self, posts_to_process):
        """Process posts using multithreading with reservation system."""
        self.log_message('info', f"Using multithreaded download with {self.max_workers} workers.")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            post_index = 0
            active_futures = {}
            
            # Main processing loop
            while self.valid_images_processed < self.limit and post_index < len(posts_to_process):
                # Check for cancellation
                if self.is_cancelled():
                    self.log_message('info', "Download cancelled, stopping multithreaded processing")
                    # Cancel remaining futures
                    for future in active_futures.keys():
                        future.cancel()
                    return
                
                # Wait if paused
                self.wait_if_paused()
                
                # Check for cancellation again after potential pause
                if self.is_cancelled():
                    self.log_message('info', "Download cancelled, stopping multithreaded processing")
                    # Cancel remaining futures
                    for future in active_futures.keys():
                        future.cancel()
                    return
                
                # Submit new posts to worker threads
                post_index = self._submit_download_tasks(
                    executor, posts_to_process, active_futures, post_index
                )
                
                # Process completed downloads
                if active_futures:
                    self._process_completed_downloads(active_futures)
            
            # Wait for remaining downloads to complete
            self._cleanup_remaining_downloads(active_futures)
    
    def _submit_download_tasks(self, executor, posts_to_process, active_futures, post_index):
        """Submit download tasks to the thread pool."""
        submitted = 0
        while (len(active_futures) < self.max_workers and 
               post_index < len(posts_to_process) and 
               (self.valid_images_processed + len(active_futures)) < self.limit):
            future = executor.submit(self.process_post, posts_to_process[post_index])
            active_futures[future] = post_index
            post_index += 1
            submitted += 1
        return post_index
    
    def _process_completed_downloads(self, active_futures):
        """Process completed download futures."""
        try:
            done_futures = concurrent.futures.as_completed(active_futures.keys(), timeout=1)
            for future in done_futures:
                result = future.result()
                self._handle_download_result(result)
                
                # Remove completed future
                if future in active_futures:
                    del active_futures[future]
                
                # Stop if we've reached the limit
                if self.valid_images_processed >= self.limit:
                    break
                    
        except concurrent.futures.TimeoutError:
            # No futures completed in timeout window
            pass
    
    def _handle_download_result(self, result):
        """Handle the result of a download operation."""
        with self.progress_lock:
            if result == "success":
                self.valid_images_processed += 1
                current_count = self.valid_images_processed
                progress = min(current_count / self.limit, 1.0)
                self.report_progress(progress)
                self.log_message('info', f"Downloaded {current_count}/{self.limit} unique images")
            elif result == "duplicate":
                self.duplicates_in_session += 1
    
    def _cleanup_remaining_downloads(self, active_futures):
        """Clean up any remaining active download futures."""
        for future in list(active_futures.keys()):
            try:
                result = future.result(timeout=10)
                if result == "duplicate":
                    with self.progress_lock:
                        self.duplicates_in_session += 1
                elif result == "success" and self.valid_images_processed < self.limit:
                    with self.progress_lock:
                        self.valid_images_processed += 1
                        current_count = self.valid_images_processed
                    self.log_message('info', f"Downloaded {current_count}/{self.limit} unique images")
            except Exception:
                # Handle cleanup exceptions silently
                pass
    
    def process_posts_singlethreaded(self, posts_to_process):
        """Process posts using single-threaded approach."""
        for post in posts_to_process:
            # Check for cancellation
            if self.is_cancelled():
                self.log_message('info', "Download cancelled, stopping single-threaded processing")
                return
            
            # Wait if paused
            self.wait_if_paused()
            
            # Check for cancellation again after potential pause
            if self.is_cancelled():
                self.log_message('info', "Download cancelled, stopping single-threaded processing")
                return
            
            if self.valid_images_processed >= self.limit:
                self.log_message('info', f"Reached limit of {self.limit} valid images. Stopping.")
                break
            result = self.process_post(post)
            if result == "success":
                self.valid_images_processed += 1
                self.log_message('info', f"Downloaded {self.valid_images_processed}/{self.limit} unique images")
                # Report progress after each successful download
                progress = min(self.valid_images_processed / self.limit, 1.0)
                self.report_progress(progress)
            elif result == "duplicate":
                self.duplicates_in_session += 1
    
    def run_download(self):
        """Main download execution method."""
        self.log_message(
            'info', 
            f"Starting download: {self.booru_type}, tag='{self.tag}', "
            f"limit={self.limit}, multithread={self.multithread}"
        )
        
        # Report initial progress
        self.report_progress(0.0)
        
        # Calculate initial fetch limit
        api_limit = API_LIMITS.get(self.booru_type, 100)
        fetch_limit = min(self.limit * 2, api_limit)
        
        # Main download loop
        while (self.valid_images_processed < self.limit and 
               self.posts_fetched < self.max_fetch_attempts):
            
            # Check for cancellation
            if self.is_cancelled():
                self.log_message('info', "Download cancelled by user")
                return False
            
            # Wait if paused
            self.wait_if_paused()
            
            # Check for cancellation again after potential pause
            if self.is_cancelled():
                self.log_message('info', "Download cancelled by user")
                return False
            
            # Fetch posts from API
            posts = self.fetch_posts(fetch_limit)
            if posts is None:
                return False
            
            if not posts:
                self.log_message(
                    'warning', 
                    f"No posts returned from {self.booru_type} for tag '{self.tag}'"
                )
                break
            
            self.posts_fetched += 1
            
            # Process posts based on threading preference
            if self.multithread:
                self.process_posts_multithreaded(posts)
            else:
                self.process_posts_singlethreaded(posts)
            
            # Check for cancellation after processing
            if self.is_cancelled():
                self.log_message('info', "Download cancelled by user")
                return False
            
            # Update progress
            progress = min(self.valid_images_processed / self.limit, 1.0)
            self.report_progress(progress)
            
            # Check completion
            if self.valid_images_processed >= self.limit:
                self.log_message('info', f"Target of {self.limit} images reached. Download complete.")
                break
            
            # Adjust fetch strategy for next iteration
            fetch_limit = self._calculate_next_fetch_limit()
            self.current_page += 1
            
            remaining = self.limit - self.valid_images_processed
            self.log_message(
                'info', 
                f"Need {remaining} more images, fetching {fetch_limit} posts from page {self.current_page} "
                f"(duplicates so far: {self.duplicates_in_session})"
            )

        # Log completion summary
        duplicates_found = self.dupe_checker.get_duplicate_count()
        self.log_message(
            'info', 
            f"Download completed: {self.valid_images_processed} new images downloaded, "
            f"{duplicates_found} duplicates skipped from {self.booru_type}."
        )
        
        # Report final completion
        self.report_progress(1.0)
        return True
    
    def _calculate_next_fetch_limit(self):
        """Calculate optimal fetch limit for next API call based on duplicate rate."""
        remaining_needed = self.limit - self.valid_images_processed
        api_limit = API_LIMITS.get(self.booru_type, 100)
        
        # Adjust multiplier based on duplicate rate
        if self.duplicates_in_session > remaining_needed:
            # High duplicate rate - fetch aggressively
            multiplier = 5
        else:
            # Normal duplicate rate - fetch conservatively
            multiplier = 2
        
        return min(remaining_needed * multiplier, api_limit)


def run_download(booru_type, tag, limit, output_dir, org_method, dupe_checker,
                multithread=False, max_workers=None, error_queue=None, progress_callback=None):
    """
    Unified download function for both CLI and GUI.
    
    Args:
        booru_type: Type of booru site (e.g., 'rule34', 'danbooru')
        tag: Tag to search for
        limit: Number of images to download
        output_dir: Output directory for images
        org_method: Organization method for images
        dupe_checker: Duplicate checker instance
        multithread: Whether to use multithreading
        max_workers: Number of worker threads (None for auto)
        error_queue: Queue for error messages (GUI integration)
        progress_callback: Callback function for progress updates (GUI integration)
    
    Returns:
        bool: True if download completed successfully, False otherwise
    """
    manager = DownloadManager(
        booru_type=booru_type,
        tag=tag,
        limit=limit,
        output_dir=output_dir,
        org_method=org_method,
        dupe_checker=dupe_checker,
        multithread=multithread,
        max_workers=max_workers,
        error_queue=error_queue,
        progress_callback=progress_callback
    )
    
    return manager.run_download()
