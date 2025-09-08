"""
Secure configuration management for BitAgent.
Handles environment variables, secrets, and configuration validation.
"""

import os
import logging
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet
import base64

class SecureConfig:
    """Secure configuration manager."""
    
    def __init__(self):
        self.config = {}
        self.secrets = {}
        self.encryption_key = None
        self._load_config()
    
    def _load_config(self):
        """Load configuration from environment variables."""
        # Required configuration
        required_vars = [
            "LNBITS_URL",
            "LNBITS_API_KEY",
            "START9_NODE_ID"
        ]
        
        # Optional configuration
        optional_vars = [
            "FEDIMINT_URL",
            "FEDIMINT_API_KEY", 
            "NOSTR_PRIVATE_KEY",
            "DATABASE_URL",
            "HOST",
            "PORT",
            "LOG_LEVEL",
            "ENCRYPTION_KEY"
        ]
        
        # Load required variables
        for var in required_vars:
            value = os.getenv(var)
            if not value:
                raise ValueError(f"Required environment variable {var} not set")
            self.config[var] = value
        
        # Load optional variables
        for var in optional_vars:
            value = os.getenv(var)
            if value:
                self.config[var] = value
        
        # Set defaults
        self.config.setdefault("HOST", "0.0.0.0")
        self.config.setdefault("PORT", "8000")
        self.config.setdefault("LOG_LEVEL", "INFO")
        self.config.setdefault("DATABASE_URL", "sqlite:///data/bitagent.db")
        
        # Initialize encryption
        self._init_encryption()
        
        logging.info("Configuration loaded successfully")
    
    def _init_encryption(self):
        """Initialize encryption for secrets."""
        encryption_key = self.config.get("ENCRYPTION_KEY")
        if encryption_key:
            try:
                self.encryption_key = Fernet(encryption_key.encode())
            except Exception as e:
                logging.warning(f"Invalid encryption key: {e}")
                self.encryption_key = None
        else:
            # Generate a new key (in production, this should be set)
            self.encryption_key = Fernet.generate_key()
            logging.warning("No encryption key provided, generated new key")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        return self.config.get(key, default)
    
    def get_secret(self, key: str) -> Optional[str]:
        """Get a secret value (encrypted)."""
        if key in self.secrets:
            return self.secrets[key]
        
        # Try to decrypt from config
        encrypted_value = self.config.get(f"{key}_ENCRYPTED")
        if encrypted_value and self.encryption_key:
            try:
                decrypted = self.encryption_key.decrypt(encrypted_value.encode())
                self.secrets[key] = decrypted.decode()
                return self.secrets[key]
            except Exception as e:
                logging.error(f"Failed to decrypt {key}: {e}")
        
        return None
    
    def set_secret(self, key: str, value: str):
        """Set a secret value (encrypted)."""
        if self.encryption_key:
            encrypted = self.encryption_key.encrypt(value.encode())
            self.config[f"{key}_ENCRYPTED"] = encrypted.decode()
            self.secrets[key] = value
        else:
            logging.warning("No encryption key available, storing secret in plain text")
            self.config[key] = value
    
    def validate_config(self) -> bool:
        """Validate configuration."""
        try:
            # Validate LNbits URL
            lnbits_url = self.get("LNBITS_URL")
            if not lnbits_url.startswith(("http://", "https://")):
                raise ValueError("LNBITS_URL must start with http:// or https://")
            
            # Validate port
            port = int(self.get("PORT"))
            if port < 1 or port > 65535:
                raise ValueError("PORT must be between 1 and 65535")
            
            # Validate log level
            log_level = self.get("LOG_LEVEL")
            valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            if log_level not in valid_levels:
                raise ValueError(f"LOG_LEVEL must be one of: {valid_levels}")
            
            return True
            
        except Exception as e:
            logging.error(f"Configuration validation failed: {e}")
            return False
    
    def get_cors_origins(self) -> list:
        """Get CORS origins from configuration."""
        origins = self.get("CORS_ORIGINS", "")
        if origins:
            return [origin.strip() for origin in origins.split(",")]
        
        # Default safe origins
        return [
            "https://yourdomain.com",
            "https://your-start9-server.com"
        ]
    
    def get_rate_limits(self) -> Dict[str, int]:
        """Get rate limiting configuration."""
        return {
            "max_requests": int(self.get("RATE_LIMIT_MAX_REQUESTS", "100")),
            "window_seconds": int(self.get("RATE_LIMIT_WINDOW", "3600")),
            "burst_limit": int(self.get("RATE_LIMIT_BURST", "10"))
        }
    
    def get_file_limits(self) -> Dict[str, int]:
        """Get file upload limits."""
        return {
            "max_audio_size": int(self.get("MAX_AUDIO_SIZE", "100")) * 1024 * 1024,  # MB to bytes
            "max_text_length": int(self.get("MAX_TEXT_LENGTH", "10000")),
            "max_tasks": int(self.get("MAX_TASKS", "10"))
        }
    
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.get("ENVIRONMENT", "production").lower() == "development"
    
    def get_database_config(self) -> Dict[str, Any]:
        """Get database configuration."""
        database_url = self.get("DATABASE_URL")
        return {
            "url": database_url,
            "pool_size": int(self.get("DB_POOL_SIZE", "10")),
            "max_overflow": int(self.get("DB_MAX_OVERFLOW", "20")),
            "pool_timeout": int(self.get("DB_POOL_TIMEOUT", "30"))
        }

# Global configuration instance
config = SecureConfig()

def get_config() -> SecureConfig:
    """Get the global configuration instance."""
    return config

def validate_environment() -> bool:
    """Validate the environment configuration."""
    return config.validate_config()
