"""
Advanced authentication and authorization system for BitAgent.
Implements JWT tokens, API keys, and cryptographic signatures.
"""

import jwt
import hashlib
import hmac
import time
import secrets
from typing import Optional, Dict, Any
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import base64
import json

class AuthenticationManager:
    """Handles authentication for agent-to-agent communication."""
    
    def __init__(self, secret_key: Optional[str] = None):
        self.secret_key = secret_key or secrets.token_urlsafe(32)
        self.private_key = self._generate_keypair()[0]
        self.public_key = self._generate_keypair()[1]
        self.active_tokens = {}
        
    def _generate_keypair(self):
        """Generate RSA keypair for signing."""
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        public_key = private_key.public_key()
        return private_key, public_key
    
    def generate_api_key(self, agent_id: str, permissions: list = None) -> str:
        """Generate a secure API key for an agent."""
        permissions = permissions or ["read", "write"]
        payload = {
            "agent_id": agent_id,
            "permissions": permissions,
            "created_at": time.time(),
            "expires_at": time.time() + (365 * 24 * 3600)  # 1 year
        }
        
        api_key = jwt.encode(payload, self.secret_key, algorithm="HS256")
        return api_key
    
    def verify_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        """Verify and decode an API key."""
        try:
            payload = jwt.decode(api_key, self.secret_key, algorithms=["HS256"])
            if payload.get("expires_at", 0) < time.time():
                return None
            return payload
        except jwt.InvalidTokenError:
            return None
    
    def create_signed_message(self, message: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
        """Create a cryptographically signed message."""
        timestamp = time.time()
        message_data = {
            "message": message,
            "agent_id": agent_id,
            "timestamp": timestamp,
            "nonce": secrets.token_hex(16)
        }
        
        # Create signature
        message_str = json.dumps(message_data, sort_keys=True)
        signature = self.private_key.sign(
            message_str.encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        
        return {
            "data": message_data,
            "signature": base64.b64encode(signature).decode(),
            "public_key": self.public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ).decode()
        }
    
    def verify_signed_message(self, signed_message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Verify a cryptographically signed message."""
        try:
            data = signed_message["data"]
            signature = base64.b64decode(signed_message["signature"])
            public_key_pem = signed_message["public_key"]
            
            # Load public key
            public_key = serialization.load_pem_public_key(
                public_key_pem.encode(),
                backend=default_backend()
            )
            
            # Verify signature
            message_str = json.dumps(data, sort_keys=True)
            public_key.verify(
                signature,
                message_str.encode(),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            # Check timestamp (prevent replay attacks)
            if time.time() - data["timestamp"] > 300:  # 5 minutes
                return None
                
            return data
        except Exception:
            return None
    
    def create_jwt_token(self, agent_id: str, permissions: list = None, expires_in: int = 3600) -> str:
        """Create a JWT token for session management."""
        permissions = permissions or ["read"]
        payload = {
            "agent_id": agent_id,
            "permissions": permissions,
            "iat": time.time(),
            "exp": time.time() + expires_in,
            "jti": secrets.token_hex(16)  # JWT ID
        }
        
        token = jwt.encode(payload, self.secret_key, algorithm="HS256")
        self.active_tokens[payload["jti"]] = payload
        return token
    
    def verify_jwt_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify a JWT token."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            if payload["jti"] not in self.active_tokens:
                return None
            return payload
        except jwt.InvalidTokenError:
            return None
    
    def revoke_token(self, token: str):
        """Revoke a JWT token."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            self.active_tokens.pop(payload["jti"], None)
        except jwt.InvalidTokenError:
            pass

class RateLimiter:
    """Rate limiting for API endpoints."""
    
    def __init__(self, max_requests: int = 100, window_seconds: int = 3600):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}
    
    def is_allowed(self, agent_id: str) -> bool:
        """Check if agent is within rate limits."""
        now = time.time()
        window_start = now - self.window_seconds
        
        # Clean old entries
        if agent_id in self.requests:
            self.requests[agent_id] = [
                req_time for req_time in self.requests[agent_id]
                if req_time > window_start
            ]
        else:
            self.requests[agent_id] = []
        
        # Check limit
        if len(self.requests[agent_id]) >= self.max_requests:
            return False
        
        # Add current request
        self.requests[agent_id].append(now)
        return True
