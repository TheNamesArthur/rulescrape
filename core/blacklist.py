"""
Blacklist Integration Module for Rulescrape

Provides comprehensive blacklist functionality for filtering unwanted content.
Features easy-to-edit JSON configuration and integration with CLI and GUI.
"""

import json
import logging
from pathlib import Path
from typing import List, Set, Dict, Optional

logger = logging.getLogger("blacklist")


class BlacklistManager:
    """Manages blacklisted tags and filtering functionality"""
    
    DEFAULT_BLACKLIST_FILE = "blacklist.json"
    
    def __init__(self, blacklist_file: Optional[str] = None):
        """
        Initialize blacklist manager.
        
        Args:
            blacklist_file (str, optional): Path to blacklist JSON file
        """
        self.blacklist_file = blacklist_file or self.DEFAULT_BLACKLIST_FILE
        self.blacklisted_tags: Set[str] = set()
        self.tag_groups: Dict[str, List[str]] = {}
        self.enabled = True
        self.case_sensitive = False
        self._load_blacklist()
    
    def _get_default_blacklist_config(self) -> Dict:
        """Get default blacklist configuration with examples"""
        return {
            "enabled": True,
            "case_sensitive": False,
            "description": "Rulescrape Blacklist - Tags and content to exclude from downloads",
            "tags": [
                "gore",
                "scat",
                "vore",
                "watersports"
            ],
            "tag_groups": {
                "extreme_content": [
                    "gore",
                    "death",
                    "torture",
                    "snuff"
                ],
                "fetish_content": [
                    "scat",
                    "watersports",
                    "diaper",
                    "vore"
                ],
                "ai_generated": [
                    "ai_generated",
                    "artificial_intelligence",
                    "ai_art",
                    "machine_generated",
                    "stable_diffusion",
                    "midjourney",
                    "dall-e"
                ]
            },
            "notes": {
                "usage": "Add individual tags to 'tags' array or create groups in 'tag_groups'",
                "examples": "Use tag groups to organize related blacklisted content",
                "editing": "This file can be edited manually or through the GUI settings"
            }
        }
    
    def _load_blacklist(self):
        """Load blacklist configuration from JSON file"""
        blacklist_path = Path(self.blacklist_file)
        
        if not blacklist_path.exists():
            logger.info(f"[BlacklistManager] Creating default blacklist file: {self.blacklist_file}")
            self._create_default_blacklist()
            return
        
        try:
            with open(blacklist_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Load configuration
            self.enabled = config.get('enabled', True)
            self.case_sensitive = config.get('case_sensitive', False)
            
            # Load individual tags
            tags = config.get('tags', [])
            if isinstance(tags, list):
                self.blacklisted_tags.update(tags)
            
            # Load tag groups
            self.tag_groups = config.get('tag_groups', {})
            for group_name, group_tags in self.tag_groups.items():
                if isinstance(group_tags, list):
                    self.blacklisted_tags.update(group_tags)
            
            # Convert to lowercase if not case sensitive
            if not self.case_sensitive:
                self.blacklisted_tags = {tag.lower() for tag in self.blacklisted_tags}
            
            logger.info(f"[BlacklistManager] Loaded {len(self.blacklisted_tags)} blacklisted tags from {self.blacklist_file}")
            
        except Exception as e:
            logger.error(f"[BlacklistManager] Error loading blacklist from {self.blacklist_file}: {e}")
            logger.info("[BlacklistManager] Creating backup and default blacklist")
            self._backup_and_create_default()
    
    def _create_default_blacklist(self):
        """Create default blacklist JSON file"""
        try:
            default_config = self._get_default_blacklist_config()
            
            with open(self.blacklist_file, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)
            
            # Load the default configuration
            self.enabled = default_config['enabled']
            self.case_sensitive = default_config['case_sensitive']
            self.blacklisted_tags = set(default_config['tags'])
            self.tag_groups = default_config['tag_groups']
            
            # Add tag groups to blacklisted tags
            for group_tags in self.tag_groups.values():
                self.blacklisted_tags.update(group_tags)
            
            # Convert to lowercase if not case sensitive
            if not self.case_sensitive:
                self.blacklisted_tags = {tag.lower() for tag in self.blacklisted_tags}
            
            logger.info(f"[BlacklistManager] Created default blacklist with {len(self.blacklisted_tags)} tags")
            
        except Exception as e:
            logger.error(f"[BlacklistManager] Error creating default blacklist: {e}")
    
    def _backup_and_create_default(self):
        """Backup corrupted blacklist file and create default"""
        try:
            if Path(self.blacklist_file).exists():
                backup_file = f"{self.blacklist_file}.backup"
                Path(self.blacklist_file).rename(backup_file)
                logger.info(f"[BlacklistManager] Backed up corrupted blacklist to {backup_file}")
        except Exception as e:
            logger.warning(f"[BlacklistManager] Could not backup corrupted blacklist: {e}")
        
        self._create_default_blacklist()
    
    def save_blacklist(self):
        """Save current blacklist configuration to JSON file"""
        try:
            # Prepare configuration for saving
            config = {
                "enabled": self.enabled,
                "case_sensitive": self.case_sensitive,
                "description": "Rulescrape Blacklist - Tags and content to exclude from downloads",
                "tags": sorted(list(self.blacklisted_tags - self._get_group_tags())),
                "tag_groups": self.tag_groups,
                "notes": {
                    "usage": "Add individual tags to 'tags' array or create groups in 'tag_groups'",
                    "examples": "Use tag groups to organize related blacklisted content",
                    "editing": "This file can be edited manually or through the GUI settings",
                    "last_modified": f"Last modified via Rulescrape on {self._get_timestamp()}"
                }
            }
            
            with open(self.blacklist_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            logger.info(f"[BlacklistManager] Saved blacklist to {self.blacklist_file}")
            return True
            
        except Exception as e:
            logger.error(f"[BlacklistManager] Error saving blacklist: {e}")
            return False
    
    def _get_group_tags(self) -> Set[str]:
        """Get all tags that are part of tag groups"""
        group_tags = set()
        for group_list in self.tag_groups.values():
            group_tags.update(group_list)
        return group_tags
    
    def _get_timestamp(self) -> str:
        """Get current timestamp string"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def add_tag(self, tag: str) -> bool:
        """
        Add a tag to the blacklist.
        
        Args:
            tag (str): Tag to add
            
        Returns:
            bool: True if tag was added, False if already existed
        """
        if not tag or not tag.strip():
            return False
        
        tag = tag.strip()
        if not self.case_sensitive:
            tag = tag.lower()
        
        if tag in self.blacklisted_tags:
            return False
        
        self.blacklisted_tags.add(tag)
        logger.info(f"[BlacklistManager] Added tag to blacklist: {tag}")
        return True
    
    def remove_tag(self, tag: str) -> bool:
        """
        Remove a tag from the blacklist.
        
        Args:
            tag (str): Tag to remove
            
        Returns:
            bool: True if tag was removed, False if not found
        """
        if not tag or not tag.strip():
            return False
        
        tag = tag.strip()
        if not self.case_sensitive:
            tag = tag.lower()
        
        if tag not in self.blacklisted_tags:
            return False
        
        self.blacklisted_tags.remove(tag)
        
        # Also remove from any tag groups
        for group_name, group_tags in self.tag_groups.items():
            if tag in group_tags:
                group_tags.remove(tag)
        
        logger.info(f"[BlacklistManager] Removed tag from blacklist: {tag}")
        return True
    
    def add_tag_group(self, group_name: str, tags: List[str]) -> bool:
        """
        Add a tag group to the blacklist.
        
        Args:
            group_name (str): Name of the tag group
            tags (List[str]): List of tags in the group
            
        Returns:
            bool: True if group was added/updated
        """
        if not group_name or not group_name.strip():
            return False
        
        group_name = group_name.strip()
        clean_tags = []
        
        for tag in tags:
            if tag and tag.strip():
                clean_tag = tag.strip()
                if not self.case_sensitive:
                    clean_tag = clean_tag.lower()
                clean_tags.append(clean_tag)
        
        if not clean_tags:
            return False
        
        self.tag_groups[group_name] = clean_tags
        self.blacklisted_tags.update(clean_tags)
        
        logger.info(f"[BlacklistManager] Added tag group '{group_name}' with {len(clean_tags)} tags")
        return True
    
    def remove_tag_group(self, group_name: str) -> bool:
        """
        Remove a tag group from the blacklist.
        
        Args:
            group_name (str): Name of the tag group to remove
            
        Returns:
            bool: True if group was removed, False if not found
        """
        if group_name not in self.tag_groups:
            return False
        
        # Remove group tags from blacklisted_tags
        group_tags = set(self.tag_groups[group_name])
        self.blacklisted_tags -= group_tags
        
        # Remove the group
        del self.tag_groups[group_name]
        
        logger.info(f"[BlacklistManager] Removed tag group: {group_name}")
        return True
    
    def is_tag_blacklisted(self, tag: str) -> bool:
        """
        Check if a tag is blacklisted.
        
        Args:
            tag (str): Tag to check
            
        Returns:
            bool: True if tag is blacklisted
        """
        if not self.enabled or not tag:
            return False
        
        check_tag = tag.strip()
        if not self.case_sensitive:
            check_tag = check_tag.lower()
        
        return check_tag in self.blacklisted_tags
    
    def filter_posts(self, posts: List[Dict], booru_type: str) -> List[Dict]:
        """
        Filter posts based on blacklisted tags.
        
        Args:
            posts (List[Dict]): List of post dictionaries
            booru_type (str): Type of booru site
            
        Returns:
            List[Dict]: Filtered posts with blacklisted content removed
        """
        if not self.enabled or not posts:
            return posts
        
        filtered_posts = []
        filtered_count = 0
        
        for post in posts:
            tags = self._extract_post_tags(post, booru_type)
            
            # Check if any tag is blacklisted
            is_blacklisted = False
            for tag in tags:
                if self.is_tag_blacklisted(tag):
                    is_blacklisted = True
                    break
            
            if is_blacklisted:
                filtered_count += 1
                logger.debug(f"[BlacklistManager] Filtered post {post.get('id', 'unknown')} - blacklisted tags found")
            else:
                filtered_posts.append(post)
        
        if filtered_count > 0:
            logger.info(f"[BlacklistManager] Filtered {filtered_count} posts with blacklisted content")
        
        return filtered_posts
    
    def _extract_post_tags(self, post: Dict, booru_type: str) -> List[str]:
        """
        Extract tags from a post based on booru type.
        
        Args:
            post (Dict): Post dictionary
            booru_type (str): Type of booru site
            
        Returns:
            List[str]: List of tags from the post
        """
        if booru_type == "danbooru":
            tags_str = post.get('tag_string', '')
        elif booru_type == "paheal":
            tags_str = post.get('tags', '')
        else:
            tags_str = post.get('tags', '')
        
        if isinstance(tags_str, str):
            tags = tags_str.split()
        elif isinstance(tags_str, list):
            tags = tags_str
        else:
            tags = []
        
        # Normalize case if not case sensitive
        if not self.case_sensitive:
            tags = [tag.lower() for tag in tags]
        
        return tags
    
    def get_blacklisted_tags(self) -> List[str]:
        """
        Get list of all blacklisted tags.
        
        Returns:
            List[str]: Sorted list of blacklisted tags
        """
        return sorted(list(self.blacklisted_tags))
    
    def get_tag_groups(self) -> Dict[str, List[str]]:
        """
        Get dictionary of tag groups.
        
        Returns:
            Dict[str, List[str]]: Dictionary of tag groups
        """
        return self.tag_groups.copy()
    
    def get_blacklist_stats(self) -> Dict:
        """
        Get blacklist statistics.
        
        Returns:
            Dict: Statistics about the blacklist
        """
        group_tag_count = len(self._get_group_tags())
        individual_tag_count = len(self.blacklisted_tags) - group_tag_count
        
        return {
            "enabled": self.enabled,
            "case_sensitive": self.case_sensitive,
            "total_tags": len(self.blacklisted_tags),
            "individual_tags": individual_tag_count,
            "tag_groups": len(self.tag_groups),
            "group_tags": group_tag_count,
            "blacklist_file": self.blacklist_file
        }
    
    def enable_blacklist(self):
        """Enable blacklist filtering"""
        self.enabled = True
        logger.info("[BlacklistManager] Blacklist enabled")
    
    def disable_blacklist(self):
        """Disable blacklist filtering"""
        self.enabled = False
        logger.info("[BlacklistManager] Blacklist disabled")
    
    def set_case_sensitive(self, case_sensitive: bool):
        """
        Set case sensitivity for blacklist matching.
        
        Args:
            case_sensitive (bool): Whether to use case-sensitive matching
        """
        if self.case_sensitive != case_sensitive:
            self.case_sensitive = case_sensitive
            
            # Reload blacklist to apply case sensitivity changes
            self._load_blacklist()
            logger.info(f"[BlacklistManager] Case sensitivity set to: {case_sensitive}")


# Global blacklist manager instance
_blacklist_manager = None


def get_blacklist_manager(blacklist_file: Optional[str] = None) -> BlacklistManager:
    """
    Get global blacklist manager instance.
    
    Args:
        blacklist_file (str, optional): Path to blacklist JSON file
        
    Returns:
        BlacklistManager: Global blacklist manager instance
    """
    global _blacklist_manager
    
    if _blacklist_manager is None:
        _blacklist_manager = BlacklistManager(blacklist_file)
    
    return _blacklist_manager


def add_blacklist_tag(tag: str) -> bool:
    """
    Add a tag to the blacklist (convenience function).
    
    Args:
        tag (str): Tag to add
        
    Returns:
        bool: True if tag was added
    """
    return get_blacklist_manager().add_tag(tag)


def remove_blacklist_tag(tag: str) -> bool:
    """
    Remove a tag from the blacklist (convenience function).
    
    Args:
        tag (str): Tag to remove
        
    Returns:
        bool: True if tag was removed
    """
    return get_blacklist_manager().remove_tag(tag)


def is_tag_blacklisted(tag: str) -> bool:
    """
    Check if a tag is blacklisted (convenience function).
    
    Args:
        tag (str): Tag to check
        
    Returns:
        bool: True if tag is blacklisted
    """
    return get_blacklist_manager().is_tag_blacklisted(tag)


def filter_blacklisted_posts(posts: List[Dict], booru_type: str) -> List[Dict]:
    """
    Filter posts based on blacklisted tags (convenience function).
    
    Args:
        posts (List[Dict]): List of post dictionaries
        booru_type (str): Type of booru site
        
    Returns:
        List[Dict]: Filtered posts
    """
    return get_blacklist_manager().filter_posts(posts, booru_type)


def save_blacklist() -> bool:
    """
    Save blacklist to file (convenience function).
    
    Returns:
        bool: True if saved successfully
    """
    return get_blacklist_manager().save_blacklist()


def get_blacklist_stats() -> Dict:
    """
    Get blacklist statistics (convenience function).
    
    Returns:
        Dict: Blacklist statistics
    """
    return get_blacklist_manager().get_blacklist_stats()