"""
Unified download module for rulescrape.
Handles both CLI and GUI downloads with consistent behavior.
"""

import os
import time
import logging
import concurrent.futures
from threading import Lock

from booru_api import fetch_booru_posts, download_image


class DownloadManager:
    """
    Manages image downloads with support for both single-threaded and multi-threaded operations.
    
    Attributes:
        booru_type: Type of booru site to download from
        tag: Search tag for filtering images
        limit: Maximum number of images to download
        output_dir: Directory to save downloaded images
        org_method: Organization method for file structure
        dupe_checker: Instance for duplicate detection
        multithread: Whether to use multi-threaded downloads
        max_workers: Number of worker threads for multi-threaded downloads
        error_queue: Queue for error messages (GUI integration)
    """
    
    def __init__(self, booru_type, tag, limit, output_dir, org_method, dupe_checker, 
                 multithread=False, max_workers=None, error_queue=None):
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
        
        # Progress tracking
        self.valid_images_processed = 0
        self.duplicates_in_session = 0
        self.downloaded_files = set()
        self.progress_lock = Lock()
        
        # Fetch control parameters
        self.posts_fetched = 0
        self.max_fetch_attempts = 20
        self.current_page = 0
        self.max_retries = 5
        self.backoff = 2
        
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
            post: Post metadata dictionary
            
        Returns:
            str: Destination directory path
        """
        image_url = post.get('file_url', '')
        ext = os.path.splitext(image_url.split('?')[0])[1].lower().replace('.', '')
        if ext not in ["jpg", "jpeg", "png", "gif", "webm", "mp4", "bmp", "svg"]:
            ext = "other"
        
        # Get tags - handle different booru tag formats
        if self.booru_type == "danbooru":
            tags = post.get('tag_string', '')
            tag_list = tags.split() if isinstance(tags, str) else []
        else:
            tags = post.get('tags', '')
            tag_list = tags.split() if isinstance(tags, str) else []
        
        if self.org_method == "By extension and first tag":
            return os.path.join(self.output_dir, ext, tag_list[0] if tag_list else "untagged")
        elif self.org_method == "By extension only":
            return os.path.join(self.output_dir, ext)
        elif self.org_method == "Flat (no folders)":
            return self.output_dir
        elif self.org_method == "By tag only":
            return os.path.join(self.output_dir, tag_list[0] if tag_list else "untagged")
        else:
            return os.path.join(self.output_dir, ext, tag_list[0] if tag_list else "untagged")
    
    def process_post(self, post):
        """
        Process a single post - download and check for duplicates.
        
        Args:
            post: Post metadata dictionary
            
        Returns:
            str: Result status ('success', 'duplicate', 'error')
        """
        image_url = post.get('file_url')
        if not image_url or not image_url.startswith(('http://', 'https://')):
            self.log_message('warning', f"Skipping invalid post: {post}")
            return "error"

        # Get the proper destination directory based on organization method
        dest_dir = self.get_dest_dir(post)
        os.makedirs(dest_dir, exist_ok=True)
        
        filename_part = image_url.split('/')[-1].split('?')[0]
        _, ext = os.path.splitext(filename_part)
        filename = os.path.join(dest_dir, f"post_{post['id']}{ext if ext else '.jpg'}")

        # Check if file already exists - if so, check if it's a duplicate
        if os.path.exists(filename):
            if self.dupe_checker.is_duplicate(filename):
                self.log_message('info', f"Duplicate image already exists, skipping: {filename}")
                return "duplicate"
            else:
                # File exists but isn't in our hash cache - this shouldn't happen but let's be safe
                self.log_message('warning', f"File exists but not recognized as duplicate, re-downloading: {filename}")

        temp_filename = filename + ".tmp"
        success = False
        try:
            download_image(post, image_url, dest_dir)
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                os.rename(filename, temp_filename)
                
                # Check for duplicates using the duplication checker
                if self.dupe_checker.is_duplicate(temp_filename):
                    self.log_message('info', f"Duplicate image detected after download, skipping: {filename}")
                    os.remove(temp_filename)
                    return "duplicate"
                else:
                    # Not a duplicate, keep the file
                    os.rename(temp_filename, filename)
                    success = True
        except Exception as e:
            self.log_message('error', f"Error downloading image from {image_url}: {e}")
            if os.path.exists(temp_filename):
                os.remove(temp_filename)
            return "error"

        if success:
            self.downloaded_files.add(filename)
            return "success"
        return "error"
    
    def fetch_posts(self, fetch_limit):
        """
        Fetch posts from the booru API with retry logic.
        
        Args:
            fetch_limit: Maximum number of posts to fetch
            
        Returns:
            list or None: List of posts or None on failure
        """
        import time
        
        attempt = 0
        posts = None
        
        while attempt < self.max_retries:
            try:
                # Use full API limit for Rule34 (1000), smaller limits for others
                if self.booru_type == "rule34":
                    current_limit = min(fetch_limit, 1000)  # Rule34 supports up to 1000 posts per request
                else:
                    current_limit = min(fetch_limit, 100)   # Conservative limit for other APIs
                    
                posts = fetch_booru_posts(self.booru_type, tags=self.tag, limit=current_limit, pid=self.current_page)
                break
            except Exception as e:
                err_str = str(e).lower()
                if ("429" in err_str or "rate limit" in err_str or "422" in err_str) and self.booru_type == "danbooru":
                    wait_time = self.backoff ** attempt
                    msg = f"Rate limit encountered ({e}). Retrying in {wait_time} seconds. Attempt {attempt+1}/{self.max_retries}."
                    self.log_message('warning', msg)
                    time.sleep(wait_time)
                    attempt += 1
                    continue
                else:
                    self.log_message('error', f"Error fetching posts from {self.booru_type}: {e}")
                    return None
                    
        if posts is None:
            self.log_message('error', f"Failed to fetch posts from {self.booru_type} after {self.max_retries} retries due to rate limiting or errors.")
            return None

        if not posts:
            self.log_message('warning', f"No posts returned from {self.booru_type} for tag '{self.tag}' and limit {current_limit}. Possible reasons: no results, API error, or invalid query.")
            return None
            
        return posts
    
    def process_posts_multithreaded(self, posts_to_process):
        """Process posts using multithreading with reservation system."""
        self.log_message('info', f"Using multithreaded download with {self.max_workers} workers.")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            post_index = 0
            active_futures = {}
            reserved_downloads = 0  # Track how many downloads we've reserved (submitted futures for)
            
            # Continue processing posts until we reach the limit
            while self.valid_images_processed < self.limit and post_index < len(posts_to_process):
                # Submit new posts while we have worker capacity and haven't reserved more than we need
                while (len(active_futures) < self.max_workers and 
                       post_index < len(posts_to_process) and 
                       reserved_downloads < self.limit):
                    future = executor.submit(self.process_post, posts_to_process[post_index])
                    active_futures[future] = post_index
                    post_index += 1
                    reserved_downloads += 1  # Reserve this slot
                
                # Check for completed downloads
                if active_futures:
                    # Wait for at least one to complete
                    done_futures = concurrent.futures.as_completed(active_futures.keys(), timeout=1)
                    try:
                        for future in done_futures:
                            result = future.result()
                            if result == "success":
                                with self.progress_lock:  # Thread-safe increment
                                    self.valid_images_processed += 1
                                    current_count = self.valid_images_processed
                                self.log_message('info', f"Downloaded {current_count}/{self.limit} unique images")
                            elif result == "duplicate":
                                with self.progress_lock:  # Thread-safe increment
                                    self.duplicates_in_session += 1
                                # Free up the reservation since this wasn't a successful download
                                reserved_downloads -= 1
                            else:
                                # Error case - free up the reservation
                                reserved_downloads -= 1
                            
                            # Remove completed future
                            if future in active_futures:
                                del active_futures[future]
                            
                            # Stop processing if we've reached our limit
                            if self.valid_images_processed >= self.limit:
                                break
                    except concurrent.futures.TimeoutError:
                        # No futures completed in timeout, continue
                        pass
            
            # Wait for any remaining active futures to complete
            for future in list(active_futures.keys()):
                try:
                    result = future.result(timeout=10)  # Wait up to 10 seconds for cleanup
                    if result == "duplicate":
                        with self.progress_lock:
                            self.duplicates_in_session += 1
                    elif result == "success" and self.valid_images_processed < self.limit:
                        # Only count if we haven't exceeded the limit
                        with self.progress_lock:
                            self.valid_images_processed += 1
                            current_count = self.valid_images_processed
                        self.log_message('info', f"Downloaded {current_count}/{self.limit} unique images")
                except:
                    # Handle any exceptions during cleanup
                    pass
    
    def process_posts_singlethreaded(self, posts_to_process):
        """Process posts using single-threaded approach."""
        for post in posts_to_process:
            if self.valid_images_processed >= self.limit:
                self.log_message('info', f"Reached limit of {self.limit} valid images. Stopping.")
                break
            result = self.process_post(post)
            if result == "success":
                self.valid_images_processed += 1
                self.log_message('info', f"Downloaded {self.valid_images_processed}/{self.limit} unique images")
            elif result == "duplicate":
                self.duplicates_in_session += 1
    
    def run_download(self):
        """Main download execution method."""
        self.log_message('info', f"Starting download: {self.booru_type}, tag='{self.tag}', limit={self.limit}, multithread={self.multithread}")
        
        # Start by fetching 2x the limit, but respect API limits
        fetch_limit = min(self.limit * 2, 1000)
        
        while self.valid_images_processed < self.limit and self.posts_fetched < self.max_fetch_attempts:
            # Fetch posts
            posts = self.fetch_posts(fetch_limit)
            if posts is None:
                return False
            
            self.posts_fetched += 1
            posts_to_process = list(posts)  # Convert to list for easier manipulation

            # Process posts
            if self.multithread:
                self.process_posts_multithreaded(posts_to_process)
            else:
                self.process_posts_singlethreaded(posts_to_process)
            
            # Check if we've reached our target
            if self.valid_images_processed >= self.limit:
                self.log_message('info', f"Target of {self.limit} images reached. Download complete.")
                break
                
            # If we haven't gotten enough unique images, try fetching more
            if self.valid_images_processed < self.limit:
                remaining_needed = self.limit - self.valid_images_processed
                
                # Be more aggressive with fetch limit if we're seeing many duplicates
                if self.duplicates_in_session > remaining_needed:
                    # High duplicate rate - fetch much more
                    if self.booru_type == "rule34":
                        fetch_limit = min(remaining_needed * 5, 1000)  # Use Rule34's full API limit
                    else:
                        fetch_limit = max(remaining_needed * 5, 100)
                else:
                    # Normal duplicate rate - fetch 2x what we need
                    if self.booru_type == "rule34":
                        fetch_limit = min(remaining_needed * 2, 1000)  # Use Rule34's full API limit
                    else:
                        fetch_limit = max(remaining_needed * 2, 20)
                    
                self.current_page += 1  # Move to next page to get different posts
                self.log_message('info', f"Need {remaining_needed} more unique images, fetching {fetch_limit} more posts from page {self.current_page}... (duplicates so far: {self.duplicates_in_session})")

        # Log completion summary
        duplicates_found = self.dupe_checker.get_duplicate_count()
        self.log_message('info', f"Download completed: {self.valid_images_processed} new images downloaded, {duplicates_found} duplicates skipped from {self.booru_type}.")
        
        return True


def run_download(booru_type, tag, limit, output_dir, org_method, dupe_checker,
                multithread=False, max_workers=None, error_queue=None):
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
        error_queue=error_queue
    )
    
    return manager.run_download()
