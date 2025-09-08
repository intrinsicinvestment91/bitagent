"""
Advanced encryption utilities for secure agent communication.
Implements AES-256-GCM, ChaCha20-Poly1305, and key exchange protocols.
"""

import os
import secrets
import hashlib
from typing import Tuple, Optional
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519, rsa, padding
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305, AESGCM
from cryptography.hazmat.backends import default_backend
import base64

class EncryptionManager:
    """Handles encryption and decryption for agent communications."""
    
    def __init__(self):
        self.backend = default_backend()
    
    def generate_symmetric_key(self, length: int = 32) -> bytes:
        """Generate a random symmetric key."""
        return secrets.token_bytes(length)
    
    def derive_key_from_password(self, password: str, salt: bytes = None) -> Tuple[bytes, bytes]:
        """Derive a key from a password using PBKDF2."""
        if salt is None:
            salt = secrets.token_bytes(16)
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=self.backend
        )
        key = kdf.derive(password.encode())
        return key, salt
    
    def derive_key_scrypt(self, password: str, salt: bytes = None) -> Tuple[bytes, bytes]:
        """Derive a key using Scrypt (more secure but slower)."""
        if salt is None:
            salt = secrets.token_bytes(16)
        
        kdf = Scrypt(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            n=2**14,  # CPU/memory cost
            r=8,      # Block size
            p=1,      # Parallelization
            backend=self.backend
        )
        key = kdf.derive(password.encode())
        return key, salt
    
    def encrypt_aes_gcm(self, data: bytes, key: bytes) -> Tuple[bytes, bytes, bytes]:
        """Encrypt data using AES-256-GCM."""
        iv = secrets.token_bytes(12)  # 96-bit IV for GCM
        cipher = AESGCM(key)
        ciphertext = cipher.encrypt(iv, data, None)
        return ciphertext, iv, b""  # No additional data
    
    def decrypt_aes_gcm(self, ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
        """Decrypt data using AES-256-GCM."""
        cipher = AESGCM(key)
        return cipher.decrypt(iv, ciphertext, None)
    
    def encrypt_chacha20_poly1305(self, data: bytes, key: bytes) -> Tuple[bytes, bytes]:
        """Encrypt data using ChaCha20-Poly1305."""
        nonce = secrets.token_bytes(12)
        cipher = ChaCha20Poly1305(key)
        ciphertext = cipher.encrypt(nonce, data, None)
        return ciphertext, nonce
    
    def decrypt_chacha20_poly1305(self, ciphertext: bytes, key: bytes, nonce: bytes) -> bytes:
        """Decrypt data using ChaCha20-Poly1305."""
        cipher = ChaCha20Poly1305(key)
        return cipher.decrypt(nonce, ciphertext, None)
    
    def encrypt_with_password(self, data: bytes, password: str) -> str:
        """Encrypt data with a password (returns base64 encoded)."""
        key, salt = self.derive_key_from_password(password)
        ciphertext, iv, _ = self.encrypt_aes_gcm(data, key)
        
        # Combine salt + iv + ciphertext
        encrypted_data = salt + iv + ciphertext
        return base64.b64encode(encrypted_data).decode()
    
    def decrypt_with_password(self, encrypted_data: str, password: str) -> bytes:
        """Decrypt data with a password."""
        encrypted_bytes = base64.b64decode(encrypted_data)
        
        # Extract components
        salt = encrypted_bytes[:16]
        iv = encrypted_bytes[16:28]
        ciphertext = encrypted_bytes[28:]
        
        key, _ = self.derive_key_from_password(password, salt)
        return self.decrypt_aes_gcm(ciphertext, key, iv)

class KeyExchange:
    """Handles secure key exchange between agents."""
    
    def __init__(self):
        self.private_key = x25519.X25519PrivateKey.generate()
        self.public_key = self.private_key.public_key()
    
    def get_public_key_bytes(self) -> bytes:
        """Get public key as bytes."""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
    
    def derive_shared_secret(self, peer_public_key_bytes: bytes) -> bytes:
        """Derive shared secret with peer's public key."""
        peer_public_key = x25519.X25519PublicKey.from_public_bytes(peer_public_key_bytes)
        shared_secret = self.private_key.exchange(peer_public_key)
        
        # Use HKDF to derive a proper key
        return self._hkdf_expand(shared_secret, b"bitagent-key-exchange", 32)
    
    def _hkdf_expand(self, shared_secret: bytes, info: bytes, length: int) -> bytes:
        """Expand shared secret using HKDF."""
        hkdf = hashes.Hash(hashes.SHA256(), backend=default_backend())
        hkdf.update(shared_secret)
        hkdf.update(info)
        return hkdf.finalize()[:length]

class SecureMessage:
    """Secure message wrapper with encryption and authentication."""
    
    def __init__(self, encryption_manager: EncryptionManager):
        self.encryption_manager = encryption_manager
    
    def create_secure_message(self, data: dict, key: bytes, use_chacha20: bool = True) -> dict:
        """Create a secure encrypted message."""
        import json
        message_data = json.dumps(data).encode()
        
        if use_chacha20:
            ciphertext, nonce = self.encryption_manager.encrypt_chacha20_poly1305(message_data, key)
            return {
                "ciphertext": base64.b64encode(ciphertext).decode(),
                "nonce": base64.b64encode(nonce).decode(),
                "algorithm": "chacha20-poly1305"
            }
        else:
            ciphertext, iv, _ = self.encryption_manager.encrypt_aes_gcm(message_data, key)
            return {
                "ciphertext": base64.b64encode(ciphertext).decode(),
                "iv": base64.b64encode(iv).decode(),
                "algorithm": "aes-256-gcm"
            }
    
    def decrypt_secure_message(self, secure_message: dict, key: bytes) -> dict:
        """Decrypt a secure message."""
        import json
        
        algorithm = secure_message.get("algorithm", "aes-256-gcm")
        ciphertext = base64.b64decode(secure_message["ciphertext"])
        
        if algorithm == "chacha20-poly1305":
            nonce = base64.b64decode(secure_message["nonce"])
            plaintext = self.encryption_manager.decrypt_chacha20_poly1305(ciphertext, key, nonce)
        else:  # aes-256-gcm
            iv = base64.b64decode(secure_message["iv"])
            plaintext = self.encryption_manager.decrypt_aes_gcm(ciphertext, key, iv)
        
        return json.loads(plaintext.decode())

class InputValidator:
    """Validates and sanitizes input data."""
    
    @staticmethod
    def validate_json_schema(data: dict, schema: dict) -> bool:
        """Validate data against JSON schema."""
        # Simplified schema validation - in production, use jsonschema library
        for field, rules in schema.items():
            if field not in data:
                if rules.get("required", False):
                    return False
                continue
            
            value = data[field]
            field_type = rules.get("type")
            
            if field_type == "string":
                if not isinstance(value, str):
                    return False
                max_length = rules.get("max_length")
                if max_length and len(value) > max_length:
                    return False
            elif field_type == "integer":
                if not isinstance(value, int):
                    return False
                min_val = rules.get("minimum")
                max_val = rules.get("maximum")
                if min_val is not None and value < min_val:
                    return False
                if max_val is not None and value > max_val:
                    return False
            elif field_type == "array":
                if not isinstance(value, list):
                    return False
                max_items = rules.get("max_items")
                if max_items and len(value) > max_items:
                    return False
        
        return True
    
    @staticmethod
    def sanitize_string(text: str, max_length: int = 1000) -> str:
        """Sanitize string input."""
        # Remove null bytes and control characters
        sanitized = "".join(char for char in text if ord(char) >= 32 or char in "\t\n\r")
        return sanitized[:max_length]
    
    @staticmethod
    def validate_agent_id(agent_id: str) -> bool:
        """Validate agent ID format."""
        import re
        pattern = r"^[a-zA-Z0-9_-]{3,50}$"
        return bool(re.match(pattern, agent_id))
