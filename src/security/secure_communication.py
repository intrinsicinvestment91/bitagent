"""
Secure agent-to-agent communication protocols.
Implements end-to-end encryption, message authentication, and secure channels.
"""

import asyncio
import json
import time
import hashlib
import secrets
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import aiohttp
import logging
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.backends import default_backend
import base64

from .encryption import EncryptionManager, KeyExchange, SecureMessage
from .authentication import AuthenticationManager

class MessageType(Enum):
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    HEARTBEAT = "heartbeat"
    ERROR = "error"

class SecurityLevel(Enum):
    NONE = "none"
    BASIC = "basic"  # API key only
    ENCRYPTED = "encrypted"  # End-to-end encryption
    AUTHENTICATED = "authenticated"  # Signed messages
    SECURE = "secure"  # Full security stack

@dataclass
class SecureMessage:
    """Secure message with encryption and authentication."""
    message_id: str
    sender_id: str
    recipient_id: str
    message_type: MessageType
    payload: Dict[str, Any]
    timestamp: float
    security_level: SecurityLevel
    signature: Optional[str] = None
    encrypted_payload: Optional[str] = None
    nonce: Optional[str] = None

@dataclass
class CommunicationChannel:
    """Represents a secure communication channel between agents."""
    channel_id: str
    agent_a_id: str
    agent_b_id: str
    shared_secret: bytes
    security_level: SecurityLevel
    created_at: float
    last_activity: float
    message_count: int = 0

class SecureCommunicationManager:
    """Manages secure communication between agents."""
    
    def __init__(self, agent_id: str, auth_manager: AuthenticationManager = None):
        self.agent_id = agent_id
        self.auth_manager = auth_manager or AuthenticationManager()
        self.encryption_manager = EncryptionManager()
        self.key_exchange = KeyExchange()
        self.secure_message = SecureMessage(self.encryption_manager)
        
        self.active_channels = {}
        self.message_handlers = {}
        self.heartbeat_interval = 30.0
        self.channel_timeout = 300.0  # 5 minutes
        
        # Start cleanup task
        asyncio.create_task(self._cleanup_expired_channels())
    
    async def establish_secure_channel(self, peer_agent_id: str, peer_public_key: bytes, 
                                     security_level: SecurityLevel = SecurityLevel.SECURE) -> str:
        """Establish a secure communication channel with another agent."""
        channel_id = self._generate_channel_id(self.agent_id, peer_agent_id)
        
        # Perform key exchange
        shared_secret = self.key_exchange.derive_shared_secret(peer_public_key)
        
        # Create channel
        channel = CommunicationChannel(
            channel_id=channel_id,
            agent_a_id=self.agent_id,
            agent_b_id=peer_agent_id,
            shared_secret=shared_secret,
            security_level=security_level,
            created_at=time.time(),
            last_activity=time.time()
        )
        
        self.active_channels[channel_id] = channel
        
        # Send channel establishment message
        await self._send_channel_establishment(channel, peer_agent_id)
        
        logging.info(f"Established secure channel {channel_id} with {peer_agent_id}")
        return channel_id
    
    async def send_secure_message(self, channel_id: str, message_type: MessageType, 
                                payload: Dict[str, Any], recipient_id: str = None) -> bool:
        """Send a secure message through an established channel."""
        if channel_id not in self.active_channels:
            logging.error(f"Channel {channel_id} not found")
            return False
        
        channel = self.active_channels[channel_id]
        
        # Create message
        message = SecureMessage(
            message_id=self._generate_message_id(),
            sender_id=self.agent_id,
            recipient_id=recipient_id or channel.agent_b_id,
            message_type=message_type,
            payload=payload,
            timestamp=time.time(),
            security_level=channel.security_level
        )
        
        # Apply security based on level
        if channel.security_level in [SecurityLevel.ENCRYPTED, SecurityLevel.SECURE]:
            encrypted_payload = self.secure_message.create_secure_message(
                payload, channel.shared_secret
            )
            message.encrypted_payload = json.dumps(encrypted_payload)
            message.payload = {}  # Clear unencrypted payload
        
        if channel.security_level in [SecurityLevel.AUTHENTICATED, SecurityLevel.SECURE]:
            message.signature = self._sign_message(message)
        
        # Update channel activity
        channel.last_activity = time.time()
        channel.message_count += 1
        
        # Send message (this would be implemented based on your transport layer)
        return await self._transport_message(channel, message)
    
    async def receive_secure_message(self, channel_id: str, raw_message: Dict[str, Any]) -> Optional[SecureMessage]:
        """Receive and process a secure message."""
        if channel_id not in self.active_channels:
            logging.error(f"Channel {channel_id} not found")
            return None
        
        channel = self.active_channels[channel_id]
        
        try:
            # Parse message
            message = SecureMessage(**raw_message)
            
            # Verify signature if present
            if message.signature and not self._verify_message_signature(message):
                logging.error(f"Invalid signature for message {message.message_id}")
                return None
            
            # Decrypt payload if encrypted
            if message.encrypted_payload:
                encrypted_data = json.loads(message.encrypted_payload)
                message.payload = self.secure_message.decrypt_secure_message(
                    encrypted_data, channel.shared_secret
                )
            
            # Update channel activity
            channel.last_activity = time.time()
            
            # Handle message
            await self._handle_received_message(message)
            
            return message
            
        except Exception as e:
            logging.error(f"Failed to process secure message: {e}")
            return None
    
    def register_message_handler(self, message_type: MessageType, handler: Callable):
        """Register a handler for specific message types."""
        self.message_handlers[message_type] = handler
    
    async def send_heartbeat(self, channel_id: str) -> bool:
        """Send heartbeat to keep channel alive."""
        return await self.send_secure_message(
            channel_id, 
            MessageType.HEARTBEAT, 
            {"timestamp": time.time()}
        )
    
    async def close_channel(self, channel_id: str):
        """Close a communication channel."""
        if channel_id in self.active_channels:
            del self.active_channels[channel_id]
            logging.info(f"Closed channel {channel_id}")
    
    def get_channel_info(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a channel."""
        if channel_id not in self.active_channels:
            return None
        
        channel = self.active_channels[channel_id]
        return {
            "channel_id": channel.channel_id,
            "peer_agent": channel.agent_b_id,
            "security_level": channel.security_level.value,
            "created_at": channel.created_at,
            "last_activity": channel.last_activity,
            "message_count": channel.message_count,
            "is_active": time.time() - channel.last_activity < self.channel_timeout
        }
    
    def _generate_channel_id(self, agent_a: str, agent_b: str) -> str:
        """Generate a unique channel ID."""
        combined = f"{agent_a}:{agent_b}" if agent_a < agent_b else f"{agent_b}:{agent_a}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]
    
    def _generate_message_id(self) -> str:
        """Generate a unique message ID."""
        return secrets.token_hex(16)
    
    def _sign_message(self, message: SecureMessage) -> str:
        """Sign a message for authentication."""
        message_data = {
            "message_id": message.message_id,
            "sender_id": message.sender_id,
            "recipient_id": message.recipient_id,
            "message_type": message.message_type.value,
            "timestamp": message.timestamp
        }
        
        signed_data = self.auth_manager.create_signed_message(message_data, self.agent_id)
        return signed_data["signature"]
    
    def _verify_message_signature(self, message: SecureMessage) -> bool:
        """Verify message signature."""
        try:
            message_data = {
                "message_id": message.message_id,
                "sender_id": message.sender_id,
                "recipient_id": message.recipient_id,
                "message_type": message.message_type.value,
                "timestamp": message.timestamp
            }
            
            signed_message = {
                "data": message_data,
                "signature": message.signature,
                "public_key": ""  # Would need peer's public key
            }
            
            return self.auth_manager.verify_signed_message(signed_message) is not None
        except Exception:
            return False
    
    async def _transport_message(self, channel: CommunicationChannel, message: SecureMessage) -> bool:
        """Transport layer for sending messages."""
        # This would be implemented based on your specific transport needs
        # Could be HTTP, WebSocket, or other protocols
        try:
            # For now, just log the message
            logging.info(f"Transporting message {message.message_id} via channel {channel.channel_id}")
            return True
        except Exception as e:
            logging.error(f"Failed to transport message: {e}")
            return False
    
    async def _send_channel_establishment(self, channel: CommunicationChannel, peer_agent_id: str):
        """Send channel establishment message."""
        establishment_payload = {
            "channel_id": channel.channel_id,
            "security_level": channel.security_level.value,
            "public_key": base64.b64encode(self.key_exchange.get_public_key_bytes()).decode(),
            "timestamp": time.time()
        }
        
        # This would send via your transport layer
        logging.info(f"Sending channel establishment to {peer_agent_id}")
    
    async def _handle_received_message(self, message: SecureMessage):
        """Handle a received message."""
        handler = self.message_handlers.get(message.message_type)
        if handler:
            try:
                await handler(message)
            except Exception as e:
                logging.error(f"Error in message handler: {e}")
    
    async def _cleanup_expired_channels(self):
        """Clean up expired channels."""
        while True:
            try:
                current_time = time.time()
                expired_channels = [
                    channel_id for channel_id, channel in self.active_channels.items()
                    if current_time - channel.last_activity > self.channel_timeout
                ]
                
                for channel_id in expired_channels:
                    await self.close_channel(channel_id)
                
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                logging.error(f"Error in channel cleanup: {e}")
                await asyncio.sleep(60)

class SecureAgentClient:
    """Client for secure agent-to-agent communication."""
    
    def __init__(self, agent_id: str, communication_manager: SecureCommunicationManager):
        self.agent_id = agent_id
        self.comm_manager = communication_manager
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def call_agent_service(self, peer_agent_id: str, service_name: str, 
                               parameters: Dict[str, Any], security_level: SecurityLevel = SecurityLevel.SECURE) -> Dict[str, Any]:
        """Call a service on another agent securely."""
        # This would implement the actual service call
        # For now, return a mock response
        return {
            "status": "success",
            "service": service_name,
            "result": f"Mock result from {peer_agent_id}",
            "timestamp": time.time()
        }
    
    async def discover_and_call_service(self, service_name: str, parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Discover agents providing a service and call them."""
        # This would integrate with the discovery system
        # For now, return mock results
        return [
            {
                "agent_id": "mock-agent-1",
                "service": service_name,
                "result": "Mock result 1",
                "timestamp": time.time()
            }
        ]
