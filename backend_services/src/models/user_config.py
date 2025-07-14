from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import hashlib
import os
from cryptography.fernet import Fernet
import logging

logger = logging.getLogger(__name__)

class UserConfigBase(BaseModel):
    # Alpaca Paper Trading Configuration
    alpaca_paper_api_key: Optional[str] = None
    alpaca_paper_secret_key: Optional[str] = None
    alpaca_paper_endpoint: Optional[str] = "https://paper-api.alpaca.markets/v2"
    
    # Alpaca Live Trading Configuration  
    alpaca_live_api_key: Optional[str] = None
    alpaca_live_secret_key: Optional[str] = None
    alpaca_live_endpoint: Optional[str] = "https://api.alpaca.markets/v2"
    
    # Polygon Configuration
    polygon_api_key_name: Optional[str] = None
    polygon_secret_key: Optional[str] = None

class UserConfigCreate(UserConfigBase):
    pass

class UserConfigUpdate(UserConfigBase):
    pass

class UserConfigInDB(UserConfigBase):
    user_id: str
    created_at: datetime
    updated_at: datetime

class UserConfigResponse(UserConfigBase):
    # Return masked versions for security
    def mask_sensitive_data(self):
        if self.alpaca_paper_api_key:
            self.alpaca_paper_api_key = self.alpaca_paper_api_key[:8] + "..." if len(self.alpaca_paper_api_key) > 8 else "***"
        if self.alpaca_paper_secret_key:
            self.alpaca_paper_secret_key = "***"
        if self.alpaca_live_api_key:
            self.alpaca_live_api_key = self.alpaca_live_api_key[:8] + "..." if len(self.alpaca_live_api_key) > 8 else "***"
        if self.alpaca_live_secret_key:
            self.alpaca_live_secret_key = "***"
        if self.polygon_secret_key:
            self.polygon_secret_key = "***"
        return self

# Encryption utilities
class ConfigEncryption:
    _key = None
    
    @classmethod
    def _get_key(cls):
        if cls._key is None:
            # Try reading from Docker secret file first
            secret_file = os.getenv('CONFIG_ENCRYPTION_KEY_FILE')
            if secret_file and os.path.exists(secret_file):
                try:
                    with open(secret_file, 'rb') as f:
                        key_data = f.read().strip()
                        cls._key = Fernet(key_data)
                        logger.info("Loaded encryption key from Docker secret")
                except Exception as e:
                    logger.error(f"Error reading encryption key from secret file: {e}")
            
            # Fallback to environment variable
            if cls._key is None:
                env_key = os.getenv('CONFIG_ENCRYPTION_KEY')
                if env_key:
                    try:
                        cls._key = Fernet(env_key.encode())
                        logger.info("Loaded encryption key from environment variable")
                    except Exception as e:
                        logger.error(f"Invalid CONFIG_ENCRYPTION_KEY format: {e}")
                        raise ValueError("CONFIG_ENCRYPTION_KEY must be a valid Fernet key")
                else:
                    logger.error("No encryption key found in secret file or environment")
                    raise ValueError("Encryption key not configured")
        return cls._key
    
    @classmethod
    def encrypt_value(cls, value: str) -> str:
        if not value:
            return value
        try:
            key = cls._get_key()
            return key.encrypt(value.encode()).decode()
        except Exception as e:
            logger.error(f"Encryption error: {e}")
            return value
    
    @classmethod
    def decrypt_value(cls, encrypted_value: str) -> str:
        if not encrypted_value:
            return encrypted_value
        try:
            key = cls._get_key()
            decrypted = key.decrypt(encrypted_value.encode()).decode()
            logger.debug(f"Successfully decrypted value")
            return decrypted
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            # Return the encrypted value as-is if decryption fails
            # This allows the system to work with unencrypted values during migration
            logger.warning(f"Returning encrypted value as-is due to decryption failure")
            return encrypted_value