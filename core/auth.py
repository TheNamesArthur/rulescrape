"""
Authentication module for rulescrape.

This module handles authentication for booru sites that require API keys or user credentials.
Features:
- Encrypts auth.json file with a master password
- Supports multiple booru credentials
- GUI integration for credential management
- Secure storage with salting and hashing
"""

import os
import json
import hashlib
import base64
import logging
from typing import Dict, Optional, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger("auth")

# Booru authentication requirements
BOORU_AUTH_REQUIREMENTS = {
    'rule34.xxx': {
        'type': 'api_key', 
        'fields': ['api_key', 'user_id'],
        'description': 'Rule34.xxx requires an API key and user ID for full access',
        'help_url': 'https://rule34.xxx/index.php?page=help&topic=api'
    },
    'e621': {
        'type': 'username', 
        'fields': ['username'],
        'description': 'E621 requires a username for custom user-agent',
        'help_url': 'https://e621.net/help/api'
    },
    'danbooru': {
        'type': 'api_key',
        'fields': ['api_key', 'username'], 
        'description': 'Danbooru API key provides higher rate limits',
        'help_url': 'https://danbooru.donmai.us/wiki_pages/api'
    }
}

class AuthManager:
    """Manages encrypted authentication credentials for booru sites."""
    
    def __init__(self, auth_file_path: str = None):
        """Initialize the authentication manager.
        
        Args:
            auth_file_path: Path to the auth.json file. Defaults to 'auth.json' in script directory.
        """
        if auth_file_path is None:
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            auth_file_path = os.path.join(script_dir, 'auth.json')
        
        self.auth_file_path = auth_file_path
        self._master_password = None
        self._cipher_suite = None
        self._credentials = {}
        
    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """Derive encryption key from password and salt."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key
        
    def _get_cipher_suite(self, password: str, salt: bytes = None) -> tuple:
        """Get cipher suite for encryption/decryption."""
        if salt is None:
            salt = os.urandom(16)
        key = self._derive_key(password, salt)
        cipher_suite = Fernet(key)
        return cipher_suite, salt
        
    def authenticate(self, password: str) -> bool:
        """Authenticate with master password and load credentials.
        
        Args:
            password: Master password for decrypting credentials
            
        Returns:
            True if authentication successful, False otherwise
        """
        try:
            if not os.path.exists(self.auth_file_path):
                # First time setup - create new auth file
                logger.info("[auth.authenticate] Creating new auth file")
                self._master_password = password
                self._credentials = {}
                self._save_credentials()
                return True
                
            with open(self.auth_file_path, 'r') as f:
                auth_data = json.load(f)
                
            salt = base64.b64decode(auth_data['salt'])
            encrypted_data = base64.b64decode(auth_data['data'])
            
            cipher_suite, _ = self._get_cipher_suite(password, salt)
            
            # Try to decrypt - this will fail with wrong password
            decrypted_data = cipher_suite.decrypt(encrypted_data)
            self._credentials = json.loads(decrypted_data.decode())
            
            self._master_password = password
            self._cipher_suite = cipher_suite
            
            logger.info(f"[auth.authenticate] Successfully loaded credentials for {len(self._credentials)} boorus")
            return True
            
        except Exception as e:
            logger.error(f"[auth.authenticate] Authentication failed: {e}")
            return False
            
    def _save_credentials(self):
        """Save encrypted credentials to file."""
        if not self._master_password:
            raise ValueError("Master password not set")
            
        logger.info(f"[auth._save_credentials] Saving credentials for {len(self._credentials)} boorus")
        
        cipher_suite, salt = self._get_cipher_suite(self._master_password)
        
        credentials_json = json.dumps(self._credentials, indent=2)
        logger.debug(f"[auth._save_credentials] Credentials JSON length: {len(credentials_json)} chars")
        
        encrypted_data = cipher_suite.encrypt(credentials_json.encode())
        
        auth_data = {
            'salt': base64.b64encode(salt).decode(),
            'data': base64.b64encode(encrypted_data).decode(),
            'version': '1.0'
        }
        
        # Create backup of existing file
        if os.path.exists(self.auth_file_path):
            backup_path = f"{self.auth_file_path}.backup"
            os.rename(self.auth_file_path, backup_path)
            logger.debug(f"[auth._save_credentials] Created backup: {backup_path}")
            
        try:
            with open(self.auth_file_path, 'w') as f:
                json.dump(auth_data, f, indent=2)
            logger.info(f"[auth._save_credentials] Successfully saved credentials to {self.auth_file_path}")
        except Exception as e:
            # Restore backup on error
            if os.path.exists(f"{self.auth_file_path}.backup"):
                os.rename(f"{self.auth_file_path}.backup", self.auth_file_path)
                logger.error(f"[auth._save_credentials] Save failed, restored backup: {e}")
            raise e
        else:
            # Remove backup on success
            if os.path.exists(f"{self.auth_file_path}.backup"):
                os.remove(f"{self.auth_file_path}.backup")
                logger.debug(f"[auth._save_credentials] Removed backup file")
                
    def add_credentials(self, booru_name: str, credentials: Dict[str, str]) -> bool:
        """Add or update credentials for a booru.
        
        Args:
            booru_name: Name of the booru site
            credentials: Dictionary of credential fields
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self._master_password:
                logger.error(f"[auth.add_credentials] Not authenticated - call authenticate() first")
                raise ValueError("Not authenticated - call authenticate() first")
                
            logger.info(f"[auth.add_credentials] Adding credentials for {booru_name} with fields: {list(credentials.keys())}")
            self._credentials[booru_name] = credentials
            self._save_credentials()
            
            logger.info(f"[auth.add_credentials] Successfully added credentials for {booru_name}")
            return True
            
        except Exception as e:
            logger.error(f"[auth.add_credentials] Failed to add credentials for {booru_name}: {e}")
            return False
            
    def get_credentials(self, booru_name: str) -> Optional[Dict[str, str]]:
        """Get credentials for a booru.
        
        Args:
            booru_name: Name of the booru site
            
        Returns:
            Dictionary of credentials or None if not found
        """
        return self._credentials.get(booru_name)
        
    def remove_credentials(self, booru_name: str) -> bool:
        """Remove credentials for a booru.
        
        Args:
            booru_name: Name of the booru site
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if booru_name in self._credentials:
                del self._credentials[booru_name]
                self._save_credentials()
                logger.info(f"[auth.remove_credentials] Removed credentials for {booru_name}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"[auth.remove_credentials] Failed to remove credentials for {booru_name}: {e}")
            return False
            
    def list_stored_boorus(self) -> list:
        """Get list of boorus with stored credentials.
        
        Returns:
            List of booru names
        """
        return list(self._credentials.keys())
        
    def has_credentials(self, booru_name: str) -> bool:
        """Check if credentials exist for a booru.
        
        Args:
            booru_name: Name of the booru site
            
        Returns:
            True if credentials exist, False otherwise
        """
        return booru_name in self._credentials
        
    def change_master_password(self, old_password: str, new_password: str) -> bool:
        """Change the master password.
        
        Args:
            old_password: Current master password
            new_password: New master password
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Verify old password by trying to authenticate
            if not self.authenticate(old_password):
                return False
                
            # Update master password and re-encrypt
            self._master_password = new_password
            self._save_credentials()
            
            logger.info("[auth.change_master_password] Master password changed successfully")
            return True
            
        except Exception as e:
            logger.error(f"[auth.change_master_password] Failed to change master password: {e}")
            return False

def requires_auth(booru_name: str) -> bool:
    """Check if a booru requires authentication.
    
    Args:
        booru_name: Name of the booru site
        
    Returns:
        True if authentication is required or recommended
    """
    return booru_name in BOORU_AUTH_REQUIREMENTS

def get_auth_requirements(booru_name: str) -> Optional[Dict[str, Any]]:
    """Get authentication requirements for a booru.
    
    Args:
        booru_name: Name of the booru site
        
    Returns:
        Dictionary with auth requirements or None if not found
    """
    return BOORU_AUTH_REQUIREMENTS.get(booru_name)

# Global auth manager instance
_auth_manager = None

def get_auth_manager() -> AuthManager:
    """Get the global authentication manager instance."""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
    return _auth_manager

