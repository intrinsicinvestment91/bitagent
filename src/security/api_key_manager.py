"""
API Key Management System for BitAgent.
Provides secure API key generation, validation, and management.
"""

import secrets
import hashlib
import time
import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

@dataclass
class APIKey:
    """API Key data structure."""
    key_id: str
    key_hash: str
    agent_id: str
    permissions: List[str]
    created_at: float
    last_used: Optional[float]
    expires_at: Optional[float]
    is_active: bool
    description: str

class APIKeyManager:
    """Manages API keys for BitAgent agents."""
    
    def __init__(self, storage_file: str = "api_keys.json"):
        self.storage_file = storage_file
        self.api_keys: Dict[str, APIKey] = {}
        self.load_keys()
        
    def load_keys(self):
        """Load API keys from storage."""
        try:
            with open(self.storage_file, 'r') as f:
                data = json.load(f)
                for key_id, key_data in data.items():
                    self.api_keys[key_id] = APIKey(**key_data)
        except FileNotFoundError:
            logging.info("No existing API keys file found, starting fresh")
        except Exception as e:
            logging.error(f"Error loading API keys: {e}")
    
    def save_keys(self):
        """Save API keys to storage."""
        try:
            data = {}
            for key_id, api_key in self.api_keys.items():
                data[key_id] = asdict(api_key)
            
            with open(self.storage_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logging.error(f"Error saving API keys: {e}")
    
    def generate_api_key(self, agent_id: str, permissions: List[str] = None, 
                        description: str = "", expires_days: int = 365) -> str:
        """Generate a new API key."""
        permissions = permissions or ["read"]
        
        # Generate secure key
        raw_key = secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_id = secrets.token_urlsafe(16)
        
        # Create API key record
        api_key = APIKey(
            key_id=key_id,
            key_hash=key_hash,
            agent_id=agent_id,
            permissions=permissions,
            created_at=time.time(),
            last_used=None,
            expires_at=time.time() + (expires_days * 24 * 3600) if expires_days > 0 else None,
            is_active=True,
            description=description
        )
        
        # Store the key
        self.api_keys[key_id] = api_key
        self.save_keys()
        
        logging.info(f"Generated API key for agent {agent_id}")
        return raw_key
    
    def verify_api_key(self, raw_key: str) -> Optional[APIKey]:
        """Verify an API key and return the key data."""
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        
        for api_key in self.api_keys.values():
            if api_key.key_hash == key_hash and api_key.is_active:
                # Check expiration
                if api_key.expires_at and api_key.expires_at < time.time():
                    logging.warning(f"API key {api_key.key_id} has expired")
                    return None
                
                # Update last used
                api_key.last_used = time.time()
                self.save_keys()
                
                return api_key
        
        return None
    
    def revoke_api_key(self, key_id: str) -> bool:
        """Revoke an API key."""
        if key_id in self.api_keys:
            self.api_keys[key_id].is_active = False
            self.save_keys()
            logging.info(f"Revoked API key {key_id}")
            return True
        return False
    
    def list_api_keys(self, agent_id: str = None) -> List[Dict[str, Any]]:
        """List API keys, optionally filtered by agent."""
        keys = []
        for api_key in self.api_keys.values():
            if agent_id and api_key.agent_id != agent_id:
                continue
            
            keys.append({
                "key_id": api_key.key_id,
                "agent_id": api_key.agent_id,
                "permissions": api_key.permissions,
                "created_at": datetime.fromtimestamp(api_key.created_at).isoformat(),
                "last_used": datetime.fromtimestamp(api_key.last_used).isoformat() if api_key.last_used else None,
                "expires_at": datetime.fromtimestamp(api_key.expires_at).isoformat() if api_key.expires_at else None,
                "is_active": api_key.is_active,
                "description": api_key.description
            })
        
        return keys
    
    def cleanup_expired_keys(self):
        """Remove expired API keys."""
        current_time = time.time()
        expired_keys = []
        
        for key_id, api_key in self.api_keys.items():
            if api_key.expires_at and api_key.expires_at < current_time:
                expired_keys.append(key_id)
        
        for key_id in expired_keys:
            del self.api_keys[key_id]
        
        if expired_keys:
            self.save_keys()
            logging.info(f"Cleaned up {len(expired_keys)} expired API keys")

# Global API key manager
api_key_manager = APIKeyManager()

def create_agent_api_key(agent_id: str, permissions: List[str] = None) -> str:
    """Create an API key for an agent."""
    return api_key_manager.generate_api_key(
        agent_id=agent_id,
        permissions=permissions or ["read", "write"],
        description=f"API key for {agent_id}"
    )

def verify_agent_api_key(api_key: str) -> Optional[Dict[str, Any]]:
    """Verify an agent API key."""
    api_key_data = api_key_manager.verify_api_key(api_key)
    if api_key_data:
        return {
            "agent_id": api_key_data.agent_id,
            "permissions": api_key_data.permissions,
            "key_id": api_key_data.key_id
        }
    return None
