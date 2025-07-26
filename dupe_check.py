import os
import hashlib
import logging
from typing import Set, Optional
import time

class DuplicationChecker:
    """
    A class to handle image duplication checking using MD5 hashes.
    Caches hashes in memory for efficient duplicate detection during downloads.
    """
    
    def __init__(self, images_base_dir: str = "images"):
        """
        Initialize the duplication checker.
        
        Args:
            images_base_dir: Base directory containing all booru image folders
        """
        self.images_base_dir = images_base_dir
        self.cached_hashes: Set[str] = set()
        self.duplicates_found = 0
        self.logger = logging.getLogger("dupe_check")
        
    def _md5sum(self, filepath: str) -> Optional[str]:
        """
        Calculate MD5 hash of a file.
        
        Args:
            filepath: Path to the file to hash
            
        Returns:
            MD5 hash string or None if error occurred
        """
        hash_md5 = hashlib.md5()
        try:
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            self.logger.warning(f"[dupe_check._md5sum] Failed to calculate hash for {filepath}: {e}")
            return None
    
    def scan_existing_images(self) -> int:
        """
        Scan all existing images in the images directory and cache their MD5 hashes.
        
        Returns:
            Number of images scanned and cached
        """
        start_time = time.time()
        self.cached_hashes.clear()
        self.duplicates_found = 0
        
        if not os.path.exists(self.images_base_dir):
            self.logger.info(f"[dupe_check.scan_existing_images] Images directory {self.images_base_dir} does not exist, starting with empty cache")
            return 0
        
        image_extensions = (".jpg", ".jpeg", ".png", ".gif", ".webm", ".mp4", ".bmp", ".svg")
        scanned_count = 0
        
        self.logger.info(f"[dupe_check.scan_existing_images] Starting scan of existing images in {self.images_base_dir}")
        
        for root, dirs, files in os.walk(self.images_base_dir):
            for file in files:
                if file.lower().endswith(image_extensions):
                    filepath = os.path.join(root, file)
                    file_hash = self._md5sum(filepath)
                    if file_hash:
                        self.cached_hashes.add(file_hash)
                        scanned_count += 1
                        
                        # Log progress every 100 files
                        if scanned_count % 100 == 0:
                            self.logger.info(f"[dupe_check.scan_existing_images] Scanned {scanned_count} images...")
        
        scan_time = time.time() - start_time
        self.logger.info(f"[dupe_check.scan_existing_images] Completed scan: {scanned_count} images cached in {scan_time:.2f} seconds")
        
        return scanned_count
    
    def is_duplicate(self, filepath: str) -> bool:
        """
        Check if a file is a duplicate based on its MD5 hash.
        
        Args:
            filepath: Path to the file to check
            
        Returns:
            True if the file is a duplicate, False otherwise
        """
        if not os.path.exists(filepath):
            self.logger.warning(f"[dupe_check.is_duplicate] File does not exist: {filepath}")
            return False
            
        file_hash = self._md5sum(filepath)
        if not file_hash:
            self.logger.warning(f"[dupe_check.is_duplicate] Could not calculate hash for: {filepath}")
            return False
        
        if file_hash in self.cached_hashes:
            self.duplicates_found += 1
            self.logger.info(f"[dupe_check.is_duplicate] Duplicate detected: {filepath} (hash: {file_hash[:12]}...)")
            return True
        
        # Add the hash to cache for future duplicate detection
        self.cached_hashes.add(file_hash)
        return False
    
    def add_hash_to_cache(self, filepath: str) -> bool:
        """
        Add a file's hash to the cache without checking for duplicates.
        Useful for adding newly downloaded files to the cache.
        
        Args:
            filepath: Path to the file to add to cache
            
        Returns:
            True if hash was successfully added, False otherwise
        """
        if not os.path.exists(filepath):
            return False
            
        file_hash = self._md5sum(filepath)
        if file_hash:
            self.cached_hashes.add(file_hash)
            return True
        return False
    
    def get_duplicate_count(self) -> int:
        """
        Get the number of duplicates found during the current session.
        
        Returns:
            Number of duplicates found
        """
        return self.duplicates_found
    
    def reset_duplicate_count(self):
        """Reset the duplicate counter for a new download session."""
        self.duplicates_found = 0
    
    def get_cache_size(self) -> int:
        """
        Get the number of hashes currently cached in memory.
        
        Returns:
            Number of cached hashes
        """
        return len(self.cached_hashes)
    
    def log_session_summary(self):
        """Log a summary of the duplication checking session."""
        self.logger.info(f"[dupe_check.log_session_summary] Duplication check summary:")
        self.logger.info(f"[dupe_check.log_session_summary] - Total hashes cached: {len(self.cached_hashes)}")
        self.logger.info(f"[dupe_check.log_session_summary] - Duplicates found this session: {self.duplicates_found}")


# Global instance for easy access across modules
_global_dupe_checker: Optional[DuplicationChecker] = None

def get_dupe_checker(images_base_dir: str = "images") -> DuplicationChecker:
    """
    Get the global duplication checker instance, creating it if necessary.
    
    Args:
        images_base_dir: Base directory for images (only used on first creation)
        
    Returns:
        DuplicationChecker instance
    """
    global _global_dupe_checker
    if _global_dupe_checker is None:
        _global_dupe_checker = DuplicationChecker(images_base_dir)
    return _global_dupe_checker

def reset_dupe_checker():
    """Reset the global duplication checker instance."""
    global _global_dupe_checker
    _global_dupe_checker = None
