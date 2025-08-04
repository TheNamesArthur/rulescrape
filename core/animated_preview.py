"""
Animated Preview Module for Rulescrape Gallery

Handles animated previews for GIFs and videos on hover in the gallery.
Provides frame extraction and animation management for enhanced media browsing.
"""

import os
from pathlib import Path
from PIL import Image, ImageTk
import logging

logger = logging.getLogger("animated_preview")


class PreviewCache:
    """Cache animated frames to avoid reprocessing and limit memory usage"""
    _cache = {}
    _max_cache_size = 30  # Limit memory usage - cache up to 30 animated previews
    
    @classmethod
    def get_frames(cls, file_path, thumbnail_size=(200, 200)):
        """Get cached frames or extract if not cached"""
        key = f"{file_path}_{thumbnail_size}"
        if key not in cls._cache:
            if len(cls._cache) >= cls._max_cache_size:
                # Remove oldest entry (FIFO)
                oldest_key = next(iter(cls._cache))
                del cls._cache[oldest_key]
                logger.info(f"[PreviewCache] Removed oldest cache entry: {oldest_key}")
            
            preview = AnimatedPreview(file_path, thumbnail_size)
            frames = preview.extract_frames()
            cls._cache[key] = frames
            logger.info(f"[PreviewCache] Cached {len(frames)} frames for {Path(file_path).name}")
        
        return cls._cache[key]
    
    @classmethod
    def clear_cache(cls):
        """Clear all cached frames"""
        cls._cache.clear()
        logger.info("[PreviewCache] Cache cleared")


class AnimatedPreview:
    """Handles animated previews for GIFs and videos on hover"""
    
    def __init__(self, file_path, thumbnail_size=(200, 200)):
        self.file_path = Path(file_path)
        self.thumbnail_size = thumbnail_size
        self.frames = []
        self.current_frame = 0
        self.animation_id = None
        self.is_playing = False
        
    def extract_frames(self):
        """Extract frames from GIF/video for preview animation"""
        if self.file_path.suffix.lower() == '.gif':
            return self._extract_gif_frames()
        elif self.file_path.suffix.lower() in ['.mp4', '.webm']:
            return self._extract_video_frames()
        return []
    
    def _extract_gif_frames(self):
        """Extract frames from animated GIF"""
        try:
            frames = []
            with Image.open(self.file_path) as gif:
                # Check if it's actually animated
                if not hasattr(gif, 'n_frames') or gif.n_frames <= 1:
                    logger.debug(f"[AnimatedPreview] {self.file_path.name} is not animated")
                    return []
                
                # Limit frames to prevent memory issues (max 20 frames for preview)
                max_frames = min(gif.n_frames, 20)
                frame_step = max(1, gif.n_frames // max_frames)
                
                for frame_num in range(0, gif.n_frames, frame_step):
                    if len(frames) >= max_frames:
                        break
                        
                    gif.seek(frame_num)
                    # Convert to RGBA to handle transparency properly
                    frame = gif.convert('RGBA')
                    
                    # Create thumbnail
                    frame.thumbnail(self.thumbnail_size, Image.Resampling.LANCZOS)
                    
                    # Convert to PhotoImage
                    photo = ImageTk.PhotoImage(frame)
                    frames.append(photo)
                
                logger.info(f"[AnimatedPreview] Extracted {len(frames)} frames from GIF: {self.file_path.name}")
                return frames
                
        except Exception as e:
            logger.error(f"[AnimatedPreview] Error extracting GIF frames from {self.file_path.name}: {e}")
            return []
    
    def _extract_video_frames(self):
        """Extract frames from video using opencv"""
        try:
            import cv2
        except ImportError:
            logger.warning("[AnimatedPreview] OpenCV not available for video preview. Install with: pip install opencv-python")
            return []
        
        try:
            cap = cv2.VideoCapture(str(self.file_path))
            if not cap.isOpened():
                logger.error(f"[AnimatedPreview] Could not open video: {self.file_path.name}")
                return []
            
            frames = []
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            
            # Extract frames strategically - aim for ~15 frames covering the video
            max_frames = 15
            if frame_count > max_frames:
                # Skip frames to get a good spread across the video
                step = frame_count // max_frames
            else:
                step = 1
            
            for i in range(0, min(frame_count, max_frames * step), step):
                cap.set(cv2.CAP_PROP_POS_FRAMES, i)
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Convert BGR to RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Convert to PIL Image
                pil_frame = Image.fromarray(frame_rgb)
                pil_frame.thumbnail(self.thumbnail_size, Image.Resampling.LANCZOS)
                
                # Convert to PhotoImage
                photo = ImageTk.PhotoImage(pil_frame)
                frames.append(photo)
                
                if len(frames) >= max_frames:
                    break
            
            cap.release()
            logger.info(f"[AnimatedPreview] Extracted {len(frames)} frames from video: {self.file_path.name}")
            return frames
            
        except Exception as e:
            logger.error(f"[AnimatedPreview] Error extracting video frames from {self.file_path.name}: {e}")
            return []
    
    @staticmethod
    def is_animated_file(file_path):
        """Check if file is potentially animated (GIF or video)"""
        suffix = Path(file_path).suffix.lower()
        return suffix in ['.gif', '.mp4', '.webm']
    
    @staticmethod
    def create_video_thumbnail(video_path, thumbnail_size=(200, 200)):
        """Create a static thumbnail for video files"""
        try:
            import cv2
        except ImportError:
            logger.warning("[AnimatedPreview] OpenCV not available for video thumbnails")
            return None
        
        try:
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                return None
            
            # Get frame from 10% into the video (often better than first frame)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            target_frame = int(frame_count * 0.1)
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            
            ret, frame = cap.read()
            cap.release()
            
            if ret:
                # Convert BGR to RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Convert to PIL Image and create thumbnail
                pil_frame = Image.fromarray(frame_rgb)
                pil_frame.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)
                
                return ImageTk.PhotoImage(pil_frame)
            
        except Exception as e:
            logger.error(f"[AnimatedPreview] Error creating video thumbnail for {Path(video_path).name}: {e}")
        
        return None


class AnimationManager:
    """Manages animation playback for gallery items"""
    
    def __init__(self, root):
        self.root = root
        self.active_animations = {}  # Track active animations by widget
    
    def start_animation(self, label, file_path, static_photo):
        """Start animated preview on hover"""
        if label in self.active_animations:
            return  # Already animating
        
        # Get cached frames
        frames = PreviewCache.get_frames(file_path)
        if not frames:
            logger.debug(f"[AnimationManager] No frames available for {Path(file_path).name}")
            return
        
        # Create animation state
        animation_state = {
            'frames': frames,
            'current_frame': 0,
            'is_playing': True,
            'static_photo': static_photo,
            'animation_id': None
        }
        
        self.active_animations[label] = animation_state
        self._animate_frame(label)
        logger.debug(f"[AnimationManager] Started animation for {Path(file_path).name}")
    
    def stop_animation(self, label):
        """Stop animated preview and restore static thumbnail"""
        if label not in self.active_animations:
            return
        
        animation_state = self.active_animations[label]
        
        # Cancel scheduled animation
        if animation_state['animation_id']:
            self.root.after_cancel(animation_state['animation_id'])
        
        # Restore static thumbnail
        try:
            label.configure(image=animation_state['static_photo'])
        except:
            pass  # Widget might be destroyed
        
        # Clean up
        del self.active_animations[label]
        logger.debug("[AnimationManager] Stopped animation")
    
    def _animate_frame(self, label):
        """Animate frames in sequence"""
        if label not in self.active_animations:
            return
        
        animation_state = self.active_animations[label]
        
        if not animation_state['is_playing'] or not animation_state['frames']:
            return
        
        try:
            # Check if root still exists before updating
            if not self.root or not self.root.winfo_exists():
                # Clean up if root is destroyed
                if label in self.active_animations:
                    del self.active_animations[label]
                return
            
            # Update label with current frame
            current_frame = animation_state['frames'][animation_state['current_frame']]
            label.configure(image=current_frame)
            
            # Move to next frame
            animation_state['current_frame'] = (animation_state['current_frame'] + 1) % len(animation_state['frames'])
            
            # Schedule next frame (120ms = ~8fps for smooth preview) - only if root still exists
            if self.root and self.root.winfo_exists():
                animation_state['animation_id'] = self.root.after(120, lambda: self._animate_frame(label))
            
        except Exception as e:
            # Widget might be destroyed, clean up
            logger.debug(f"[AnimationManager] Animation cleanup: {e}")
            if label in self.active_animations:
                del self.active_animations[label]
    
    def stop_all_animations(self):
        """Stop all active animations (useful for cleanup)"""
        for label in list(self.active_animations.keys()):
            self.stop_animation(label)
        logger.info("[AnimationManager] Stopped all animations")
