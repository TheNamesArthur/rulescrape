"""
Disk-based Thumbnail Cache Module for Rulescrape Gallery

Provides persistent disk-based caching for thumbnails to improve performance
and reduce memory usage while maintaining fast gallery loading times.
"""

import os
import json
import hashlib
import threading
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import concurrent.futures

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    # Create dummy classes to prevent errors
    class Image:
        class Image:
            pass
        @staticmethod
        def new(*args, **kwargs):
            return None
        @staticmethod
        def open(*args, **kwargs):
            return None
    
    class ImageTk:
        @staticmethod
        def PhotoImage(*args, **kwargs):
            return None

logger = logging.getLogger("thumbnail_cache")


class DiskThumbnailCache:
    """
    Disk-based thumbnail cache with persistent storage and intelligent cleanup.
    Stores thumbnails as files on disk with metadata for fast access.
    """
    
    def __init__(self, cache_dir: str = "cache/thumbnails", max_cache_size_mb: int = 500, max_workers: int = None):
        """
        Initialize disk-based thumbnail cache.
        
        Args:
            cache_dir: Directory to store cached thumbnails
            max_cache_size_mb: Maximum cache size in megabytes (default 500MB)
            max_workers: Number of worker threads for thumbnail generation
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.metadata_file = self.cache_dir / "cache_metadata.json"
        self.max_cache_size_bytes = max_cache_size_mb * 1024 * 1024
        self.max_workers = max_workers or min(8, (os.cpu_count() or 1) + 4)
        
        self.metadata: Dict[str, Dict[str, Any]] = {}
        self.cache_lock = threading.Lock()
        
        # Load existing metadata
        self._load_metadata()
        
        # Clean up invalid entries on startup
        self._cleanup_invalid_entries()
        
        logger.info(f"Initialized disk thumbnail cache at {self.cache_dir} (max size: {max_cache_size_mb}MB)")
    
    def _load_metadata(self):
        """Load cache metadata from disk"""
        try:
            if self.metadata_file.exists():
                with open(self.metadata_file, 'r') as f:
                    self.metadata = json.load(f)
                logger.info(f"Loaded metadata for {len(self.metadata)} cached thumbnails")
        except Exception as e:
            logger.warning(f"Failed to load cache metadata: {e}")
            self.metadata = {}
    
    def _save_metadata(self):
        """Save cache metadata to disk"""
        try:
            with open(self.metadata_file, 'w') as f:
                json.dump(self.metadata, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save cache metadata: {e}")
    
    def _cleanup_invalid_entries(self):
        """Remove metadata entries for thumbnails that no longer exist on disk"""
        invalid_keys = []
        
        for cache_key, metadata in self.metadata.items():
            cache_file = self.cache_dir / metadata['filename']
            if not cache_file.exists():
                invalid_keys.append(cache_key)
        
        if invalid_keys:
            for key in invalid_keys:
                del self.metadata[key]
            self._save_metadata()
            logger.info(f"Cleaned up {len(invalid_keys)} invalid cache entries")
    
    def _get_cache_key(self, media_path: Path, size: Tuple[int, int]) -> str:
        """Generate a unique cache key for a media file and size"""
        # Use file path, size, and modification time for cache key
        try:
            mtime = media_path.stat().st_mtime
            content = f"{media_path}_{size}_{mtime}"
            return hashlib.md5(content.encode()).hexdigest()
        except:
            # Fallback if file doesn't exist
            content = f"{media_path}_{size}"
            return hashlib.md5(content.encode()).hexdigest()
    
    def _get_cache_filename(self, cache_key: str) -> str:
        """Generate filename for cached thumbnail"""
        return f"thumb_{cache_key}.png"
    
    def _get_cache_size(self) -> int:
        """Calculate current cache size in bytes"""
        total_size = 0
        try:
            for cache_key, metadata in self.metadata.items():
                cache_file = self.cache_dir / metadata['filename']
                if cache_file.exists():
                    total_size += cache_file.stat().st_size
        except Exception as e:
            logger.warning(f"Error calculating cache size: {e}")
        return total_size
    
    def _evict_oldest(self):
        """Remove oldest cache entries to make room"""
        if not self.metadata:
            return
        
        # Sort by access time (oldest first)
        sorted_items = sorted(
            self.metadata.items(),
            key=lambda x: x[1].get('last_access', 0)
        )
        
        current_size = self._get_cache_size()
        target_size = int(self.max_cache_size_bytes * 0.8)  # Reduce to 80% of max
        
        removed_count = 0
        for cache_key, metadata in sorted_items:
            if current_size <= target_size:
                break
                
            # Remove cache file
            cache_file = self.cache_dir / metadata['filename']
            try:
                if cache_file.exists():
                    file_size = cache_file.stat().st_size
                    cache_file.unlink()
                    current_size -= file_size
                    removed_count += 1
                
                # Remove from metadata
                del self.metadata[cache_key]
                
            except Exception as e:
                logger.warning(f"Error removing cache file {cache_file}: {e}")
        
        if removed_count > 0:
            self._save_metadata()
            logger.info(f"Evicted {removed_count} old cache entries (freed {(self._get_cache_size() - current_size) / 1024 / 1024:.1f}MB)")
    
    def _create_thumbnail(self, media_path: Path, size: Tuple[int, int] = (200, 200)) -> Optional[Image.Image]:
        """Create a thumbnail for a media file"""
        if not PIL_AVAILABLE:
            return None
        
        # Check if file exists
        if not media_path.exists():
            logger.warning(f"File not found: {media_path}")
            return self._create_placeholder_thumbnail(size, "FILE NOT FOUND")
            
        try:
            if media_path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}:
                # Regular image
                with Image.open(media_path) as img:
                    # Convert to RGB if necessary (handles RGBA, P mode, etc.)
                    if img.mode not in ('RGB', 'L'):
                        img = img.convert('RGB')
                    img.thumbnail(size, Image.Resampling.LANCZOS)
                    return img.copy()  # Return PIL Image, not PhotoImage yet
                    
            elif media_path.suffix.lower() == '.gif':
                # GIF - load first frame as static
                with Image.open(media_path) as img:
                    # Convert to RGB for consistency (PNG saving)
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    if img.mode == 'RGBA':
                        # Create white background for transparency
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        background.paste(img, mask=img.split()[-1] if len(img.split()) == 4 else None)
                        img = background
                    elif img.mode not in ('RGB', 'L'):
                        img = img.convert('RGB')
                    img.thumbnail(size, Image.Resampling.LANCZOS)
                    return img.copy()
                    
            elif media_path.suffix.lower() in {'.mp4', '.webm'}:
                # Video - create actual thumbnail from video frame
                try:
                    video_thumbnail = self._create_video_thumbnail_pil(media_path, size)
                    if video_thumbnail:
                        return video_thumbnail
                    else:
                        # Fallback to placeholder if video processing fails
                        return self._create_placeholder_thumbnail(size, "VIDEO")
                except Exception as e:
                    logger.warning(f"Video thumbnail failed for {media_path.name}: {e}")
                    return self._create_placeholder_thumbnail(size, "VIDEO")
                
        except Exception as e:
            logger.warning(f"Failed to create thumbnail for {media_path.name}: {e}")
            # Return placeholder instead of None
            return self._create_placeholder_thumbnail(size, "ERROR")
            
        # Fallback for unsupported file types
        return self._create_placeholder_thumbnail(size, "UNSUPPORTED")
    
    def _create_video_thumbnail_pil(self, video_path: Path, size: Tuple[int, int] = (200, 200)) -> Optional[Image.Image]:
        """Create a PIL Image thumbnail from video file using OpenCV"""
        if not PIL_AVAILABLE:
            return None
            
        try:
            import cv2
        except ImportError:
            logger.warning(f"OpenCV not available for video thumbnail generation. Install with: pip install opencv-python")
            return None
        
        try:
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                logger.warning(f"Could not open video file: {video_path.name}")
                return None
            
            # Try to get a frame from 10% into the video (often better than first frame)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if frame_count > 0:
                # Try 10% into the video, fallback to frame 0
                target_frame = max(0, int(frame_count * 0.1))
                cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            
            ret, frame = cap.read()
            cap.release()
            
            if ret and frame is not None:
                # Convert BGR (OpenCV) to RGB (PIL)
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Convert to PIL Image
                pil_image = Image.fromarray(frame_rgb)
                
                # Create thumbnail
                pil_image.thumbnail(size, Image.Resampling.LANCZOS)
                
                logger.debug(f"Successfully created video thumbnail for {video_path.name}")
                return pil_image
            else:
                logger.warning(f"Could not read frame from video: {video_path.name}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating video thumbnail for {video_path.name}: {e}")
            return None
    
    def _create_placeholder_thumbnail(self, size: Tuple[int, int], text: str = "ERROR") -> Optional[Image.Image]:
        """Create a placeholder thumbnail with text"""
        if not PIL_AVAILABLE:
            return None
            
        try:
            # Create a gray placeholder image
            img = Image.new('RGB', size, color='#666666')
            
            # Try to add text if PIL supports it
            try:
                from PIL import ImageDraw, ImageFont
                draw = ImageDraw.Draw(img)
                
                # Try to get a decent font size
                font_size = min(size) // 8
                if font_size < 8:
                    font_size = 8
                
                try:
                    # Try to use system fonts - cross-platform approach
                    import platform
                    system = platform.system()
                    
                    font_paths = []
                    if system == "Linux":
                        font_paths = [
                            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                            "/usr/share/fonts/TTF/DejaVuSans.ttf",
                            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                        ]
                    elif system == "Windows":
                        font_paths = [
                            "C:/Windows/Fonts/arial.ttf",
                            "C:/Windows/Fonts/calibri.ttf",
                        ]
                    elif system == "Darwin":  # macOS
                        font_paths = [
                            "/System/Library/Fonts/Arial.ttf",
                            "/System/Library/Fonts/Helvetica.ttc",
                        ]
                    
                    # Try each font path until one works
                    font = None
                    for font_path in font_paths:
                        try:
                            if os.path.exists(font_path):
                                font = ImageFont.truetype(font_path, font_size)
                                break
                        except:
                            continue
                    
                    # If no system font works, try default
                    if not font:
                        font = ImageFont.load_default()
                except:
                    try:
                        # Fallback to default font
                        font = ImageFont.load_default()
                    except:
                        font = None
                
                if font:
                    # Get text size and center it
                    bbox = draw.textbbox((0, 0), text, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    x = (size[0] - text_width) // 2
                    y = (size[1] - text_height) // 2
                    draw.text((x, y), text, fill='white', font=font)
                
            except ImportError:
                # If ImageDraw/ImageFont not available, just return the gray box
                pass
            
            return img
            
        except Exception as e:
            logger.warning(f"Failed to create placeholder thumbnail: {e}")
            return None
    
    def _save_thumbnail_to_disk(self, pil_image: Image.Image, cache_file: Path) -> bool:
        """Save PIL Image to disk as PNG"""
        if not PIL_AVAILABLE:
            return False
            
        try:
            # Ensure RGB mode for PNG saving
            if pil_image.mode not in ('RGB', 'RGBA'):
                pil_image = pil_image.convert('RGB')
            pil_image.save(cache_file, 'PNG', optimize=True)
            return True
        except Exception as e:
            logger.error(f"Failed to save thumbnail to {cache_file}: {e}")
            return False
    
    def _load_thumbnail_from_disk(self, cache_file: Path) -> Optional[Image.Image]:
        """Load thumbnail from disk and return as PIL Image"""
        if not PIL_AVAILABLE:
            return None
            
        try:
            with Image.open(cache_file) as img:
                return img.copy()  # Return PIL Image instead of PhotoImage
        except Exception as e:
            logger.warning(f"Failed to load thumbnail from {cache_file}: {e}")
            return None
    
    def get_thumbnails_batch(self, media_paths: List[Path], size: Tuple[int, int] = (200, 200)) -> Dict[Path, Image.Image]:
        """
        Get thumbnails for multiple media files using disk cache.
        Returns a dictionary mapping file paths to PIL Image objects.
        The caller should convert to PhotoImage if needed for tkinter.
        """
        if not PIL_AVAILABLE:
            logger.warning("PIL not available, cannot generate thumbnails")
            return {}
            
        logger.debug(f"Processing {len(media_paths)} files for thumbnails")
        result = {}
        uncached_paths = []
        
        # Check disk cache first
        with self.cache_lock:
            for path in media_paths:
                cache_key = self._get_cache_key(path, size)
                
                if cache_key in self.metadata:
                    cache_file = self.cache_dir / self.metadata[cache_key]['filename']
                    if cache_file.exists():
                        # Load from disk cache
                        thumbnail = self._load_thumbnail_from_disk(cache_file)
                        if thumbnail:
                            result[path] = thumbnail
                            # Update access time
                            self.metadata[cache_key]['last_access'] = time.time()
                            continue
                    else:
                        # Remove invalid metadata entry
                        del self.metadata[cache_key]
                
                # Add to uncached list
                uncached_paths.append(path)
        
        # Generate thumbnails for uncached files in parallel
        if uncached_paths:
            executor = None
            try:
                executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers)
                # Submit all thumbnail generation tasks (including videos now)
                future_to_path = {
                    executor.submit(self._create_thumbnail, path, size): path
                    for path in uncached_paths
                }
                
                # Collect results as they complete
                try:
                    for future in concurrent.futures.as_completed(future_to_path):
                        path = future_to_path[future]
                        try:
                            pil_image = future.result()
                            if pil_image:
                                # Store PIL Image directly in result
                                result[path] = pil_image
                                
                                # Cache to disk
                                with self.cache_lock:
                                    cache_key = self._get_cache_key(path, size)
                                    cache_filename = self._get_cache_filename(cache_key)
                                    cache_file = self.cache_dir / cache_filename
                                    
                                    if self._save_thumbnail_to_disk(pil_image, cache_file):
                                        # Update metadata
                                        self.metadata[cache_key] = {
                                            'filename': cache_filename,
                                            'original_path': str(path),
                                            'size': size,
                                            'created': time.time(),
                                            'last_access': time.time()
                                        }
                                        
                                        # Check if we need to evict old entries
                                        if self._get_cache_size() > self.max_cache_size_bytes:
                                            self._evict_oldest()
                            else:
                                # Even if thumbnail generation failed, provide a placeholder
                                logger.warning(f"Thumbnail generation failed for {path.name}, using placeholder")
                                placeholder = self._create_placeholder_thumbnail(size, "FAILED")
                                if placeholder:
                                    result[path] = placeholder
                                        
                        except Exception as e:
                            logger.error(f"Error processing thumbnail for {path.name}: {e}")
                            # Try to provide a placeholder even for processing errors
                            try:
                                placeholder = self._create_placeholder_thumbnail(size, "ERROR")
                                if placeholder:
                                    result[path] = placeholder
                            except Exception as placeholder_error:
                                logger.error(f"Failed to create error placeholder for {path.name}: {placeholder_error}")
                except KeyboardInterrupt:
                    logger.warning("Thumbnail generation interrupted")
                    # Cancel remaining futures
                    for future in future_to_path:
                        future.cancel()
            except Exception as e:
                logger.error(f"Error in thumbnail batch processing: {e}")
            finally:
                # Shutdown executor without blocking
                if executor is not None:
                    try:
                        executor.shutdown(wait=False)
                    except Exception:
                        pass  # Ignore shutdown errors
            
            # Save metadata after batch processing
            with self.cache_lock:
                self._save_metadata()
        
        logger.debug(f"Thumbnail batch complete: {len(result)}/{len(media_paths)} thumbnails generated")
        return result
    
    def clear_cache(self):
        """Clear all cached thumbnails from disk"""
        with self.cache_lock:
            try:
                # Remove all cache files
                for cache_file in self.cache_dir.glob("thumb_*.png"):
                    cache_file.unlink()
                
                # Clear metadata
                self.metadata.clear()
                self._save_metadata()
                
                logger.info("Disk thumbnail cache cleared")
                
            except Exception as e:
                logger.error(f"Error clearing cache: {e}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self.cache_lock:
            cache_size_bytes = self._get_cache_size()
            cache_size_mb = cache_size_bytes / 1024 / 1024
            
            return {
                'cached_items': len(self.metadata),
                'cache_size_mb': round(cache_size_mb, 2),
                'max_size_mb': self.max_cache_size_bytes / 1024 / 1024,
                'cache_dir': str(self.cache_dir),
                'workers': self.max_workers
            }
    
    def optimize_cache(self):
        """Optimize cache by removing orphaned files and compacting metadata"""
        with self.cache_lock:
            # Remove orphaned cache files (files without metadata entries)
            cache_files = set(self.cache_dir.glob("thumb_*.png"))
            metadata_files = {self.cache_dir / meta['filename'] for meta in self.metadata.values()}
            
            orphaned_files = cache_files - metadata_files
            removed_count = 0
            
            for orphaned_file in orphaned_files:
                try:
                    orphaned_file.unlink()
                    removed_count += 1
                except Exception as e:
                    logger.warning(f"Failed to remove orphaned file {orphaned_file}: {e}")
            
            if removed_count > 0:
                logger.info(f"Removed {removed_count} orphaned cache files")
            
            # Clean up invalid metadata entries
            self._cleanup_invalid_entries()
            
            logger.info("Cache optimization complete")


# Backwards compatibility - alias to disk cache
MultithreadedThumbnailCache = DiskThumbnailCache
