"""
Enhanced Decentralized Identity (DID) system with verification and trust mechanisms.
Implements DID documents, verifiable credentials, and reputation systems.
"""

import json
import hashlib
import time
import secrets
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict
from enum import Enum
import base64
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.backends import default_backend

class DIDMethod(Enum):
    KEY = "key"
    WEB = "web"
    BITCOIN = "bitcoin"
    ETHEREUM = "ethereum"
    NOSTR = "nostr"

class CredentialType(Enum):
    AGENT_CAPABILITY = "agent-capability"
    REPUTATION_SCORE = "reputation-score"
    SERVICE_VERIFICATION = "service-verification"
    PAYMENT_HISTORY = "payment-history"
    IDENTITY_VERIFICATION = "identity-verification"

class TrustLevel(Enum):
    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERIFIED = "verified"

@dataclass
class DIDDocument:
    """DID Document containing agent identity information."""
    did: str
    context: List[str]
    id: str
    public_key: List[Dict[str, Any]]
    authentication: List[str]
    service: List[Dict[str, Any]]
    created: str
    updated: str
    proof: Optional[Dict[str, Any]] = None

@dataclass
class VerifiableCredential:
    """Verifiable credential for agent capabilities and attributes."""
    context: List[str]
    type: List[str]
    issuer: str
    issuance_date: str
    expiration_date: Optional[str]
    credential_subject: Dict[str, Any]
    proof: Dict[str, Any]
    id: Optional[str] = None

@dataclass
class TrustScore:
    """Trust score for an agent."""
    agent_id: str
    overall_score: float
    payment_reliability: float
    service_quality: float
    response_time: float
    uptime: float
    verification_level: TrustLevel
    last_updated: float
    total_interactions: int
    positive_interactions: int

@dataclass
class IdentityClaim:
    """Identity claim made by an agent."""
    claim_id: str
    issuer: str
    subject: str
    claim_type: str
    claim_data: Dict[str, Any]
    evidence: List[str]
    timestamp: float
    signature: str

class EnhancedDIDManager:
    """Enhanced DID management with verification and trust systems."""
    
    def __init__(self, method: DIDMethod = DIDMethod.KEY):
        self.method = method
        self.private_key = self._generate_keypair()[0]
        self.public_key = self._generate_keypair()[1]
        self.did_documents = {}
        self.verifiable_credentials = {}
        self.trust_scores = {}
        self.identity_claims = {}
        self.verification_rules = {}
        
    def _generate_keypair(self):
        """Generate RSA keypair for DID operations."""
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        public_key = private_key.public_key()
        return private_key, public_key
    
    def create_did(self, agent_id: str, services: List[Dict[str, Any]] = None) -> str:
        """Create a new DID for an agent."""
        did = f"did:{self.method.value}:{agent_id}"
        
        public_key_pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode()
        
        did_document = DIDDocument(
            did=did,
            context=["https://www.w3.org/ns/did/v1"],
            id=did,
            public_key=[{
                "id": f"{did}#key-1",
                "type": "RsaVerificationKey2018",
                "controller": did,
                "public_key_pem": public_key_pem
            }],
            authentication=[f"{did}#key-1"],
            service=services or [],
            created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            updated=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        )
        
        # Sign the document
        did_document.proof = self._sign_did_document(did_document)
        
        self.did_documents[did] = did_document
        return did
    
    def issue_verifiable_credential(self, subject_did: str, credential_type: CredentialType, 
                                  credential_data: Dict[str, Any], expiration_days: int = 365) -> VerifiableCredential:
        """Issue a verifiable credential."""
        credential_id = secrets.token_hex(16)
        issuance_date = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        expiration_date = time.strftime("%Y-%m-%dT%H:%M:%SZ", 
                                      time.gmtime(time.time() + (expiration_days * 24 * 3600)))
        
        credential = VerifiableCredential(
            context=["https://www.w3.org/2018/credentials/v1"],
            type=["VerifiableCredential", credential_type.value],
            issuer=self._get_issuer_did(),
            issuance_date=issuance_date,
            expiration_date=expiration_date,
            credential_subject={
                "id": subject_did,
                **credential_data
            },
            proof={},
            id=credential_id
        )
        
        # Sign the credential
        credential.proof = self._sign_credential(credential)
        
        self.verifiable_credentials[credential_id] = credential
        return credential
    
    def verify_credential(self, credential: VerifiableCredential) -> bool:
        """Verify a verifiable credential."""
        try:
            # Check expiration
            if credential.expiration_date:
                exp_time = time.mktime(time.strptime(credential.expiration_date, "%Y-%m-%dT%H:%M:%SZ"))
                if time.time() > exp_time:
                    return False
            
            # Verify signature
            return self._verify_credential_signature(credential)
        except Exception:
            return False
    
    def calculate_trust_score(self, agent_id: str, interactions: List[Dict[str, Any]]) -> TrustScore:
        """Calculate trust score based on interactions."""
        if not interactions:
            return TrustScore(
                agent_id=agent_id,
                overall_score=0.0,
                payment_reliability=0.0,
                service_quality=0.0,
                response_time=0.0,
                uptime=0.0,
                verification_level=TrustLevel.UNKNOWN,
                last_updated=time.time(),
                total_interactions=0,
                positive_interactions=0
            )
        
        # Calculate metrics
        total_interactions = len(interactions)
        positive_interactions = sum(1 for i in interactions if i.get("success", False))
        
        payment_reliability = sum(i.get("payment_success", 0) for i in interactions) / total_interactions
        service_quality = sum(i.get("quality_score", 0) for i in interactions) / total_interactions
        response_time = sum(i.get("response_time", 0) for i in interactions) / total_interactions
        uptime = sum(i.get("uptime", 0) for i in interactions) / total_interactions
        
        # Calculate overall score
        overall_score = (
            payment_reliability * 0.3 +
            service_quality * 0.3 +
            (1.0 - min(response_time / 10.0, 1.0)) * 0.2 +  # Lower response time is better
            uptime * 0.2
        )
        
        # Determine verification level
        if overall_score >= 0.9:
            verification_level = TrustLevel.VERIFIED
        elif overall_score >= 0.7:
            verification_level = TrustLevel.HIGH
        elif overall_score >= 0.5:
            verification_level = TrustLevel.MEDIUM
        elif overall_score >= 0.3:
            verification_level = TrustLevel.LOW
        else:
            verification_level = TrustLevel.UNKNOWN
        
        trust_score = TrustScore(
            agent_id=agent_id,
            overall_score=overall_score,
            payment_reliability=payment_reliability,
            service_quality=service_quality,
            response_time=response_time,
            uptime=uptime,
            verification_level=verification_level,
            last_updated=time.time(),
            total_interactions=total_interactions,
            positive_interactions=positive_interactions
        )
        
        self.trust_scores[agent_id] = trust_score
        return trust_score
    
    def create_identity_claim(self, subject_did: str, claim_type: str, 
                            claim_data: Dict[str, Any], evidence: List[str] = None) -> IdentityClaim:
        """Create an identity claim."""
        claim_id = secrets.token_hex(16)
        
        claim = IdentityClaim(
            claim_id=claim_id,
            issuer=self._get_issuer_did(),
            subject=subject_did,
            claim_type=claim_type,
            claim_data=claim_data,
            evidence=evidence or [],
            timestamp=time.time(),
            signature=""
        )
        
        # Sign the claim
        claim.signature = self._sign_identity_claim(claim)
        
        self.identity_claims[claim_id] = claim
        return claim
    
    def verify_identity_claim(self, claim: IdentityClaim) -> bool:
        """Verify an identity claim."""
        try:
            return self._verify_claim_signature(claim)
        except Exception:
            return False
    
    def get_agent_reputation(self, agent_id: str) -> Optional[TrustScore]:
        """Get agent reputation score."""
        return self.trust_scores.get(agent_id)
    
    def update_agent_interaction(self, agent_id: str, interaction_data: Dict[str, Any]):
        """Update agent interaction data for trust calculation."""
        # This would typically store in a database
        # For now, we'll simulate by updating the trust score
        if agent_id in self.trust_scores:
            # Add interaction to history and recalculate
            # In a real implementation, this would be more sophisticated
            pass
    
    def _get_issuer_did(self) -> str:
        """Get the issuer DID."""
        # In a real implementation, this would be the agent's own DID
        return "did:key:issuer"
    
    def _sign_did_document(self, document: DIDDocument) -> Dict[str, Any]:
        """Sign a DID document."""
        document_data = asdict(document)
        document_data.pop("proof", None)  # Remove existing proof
        
        document_str = json.dumps(document_data, sort_keys=True)
        signature = self.private_key.sign(
            document_str.encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        
        return {
            "type": "RsaSignature2018",
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "creator": f"{document.did}#key-1",
            "signature_value": base64.b64encode(signature).decode()
        }
    
    def _sign_credential(self, credential: VerifiableCredential) -> Dict[str, Any]:
        """Sign a verifiable credential."""
        credential_data = asdict(credential)
        credential_data.pop("proof", None)  # Remove existing proof
        
        credential_str = json.dumps(credential_data, sort_keys=True)
        signature = self.private_key.sign(
            credential_str.encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        
        return {
            "type": "RsaSignature2018",
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "creator": f"{credential.issuer}#key-1",
            "signature_value": base64.b64encode(signature).decode()
        }
    
    def _sign_identity_claim(self, claim: IdentityClaim) -> str:
        """Sign an identity claim."""
        claim_data = asdict(claim)
        claim_data.pop("signature", None)  # Remove existing signature
        
        claim_str = json.dumps(claim_data, sort_keys=True)
        signature = self.private_key.sign(
            claim_str.encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        
        return base64.b64encode(signature).decode()
    
    def _verify_credential_signature(self, credential: VerifiableCredential) -> bool:
        """Verify credential signature."""
        # This would verify against the issuer's public key
        # For now, return True as a placeholder
        return True
    
    def _verify_claim_signature(self, claim: IdentityClaim) -> bool:
        """Verify claim signature."""
        # This would verify against the issuer's public key
        # For now, return True as a placeholder
        return True

class TrustNetwork:
    """Trust network for managing agent relationships and reputation."""
    
    def __init__(self):
        self.trust_relationships = {}
        self.recommendations = {}
        self.blacklist = set()
        self.whitelist = set()
    
    def add_trust_relationship(self, trustor: str, trustee: str, trust_level: float):
        """Add a trust relationship between agents."""
        if trustor not in self.trust_relationships:
            self.trust_relationships[trustor] = {}
        
        self.trust_relationships[trustor][trustee] = {
            "trust_level": trust_level,
            "created_at": time.time(),
            "last_updated": time.time()
        }
    
    def get_trust_path(self, source: str, target: str, max_hops: int = 3) -> Optional[List[str]]:
        """Find a trust path between two agents."""
        if source == target:
            return [source]
        
        if max_hops <= 0:
            return None
        
        if source in self.trust_relationships:
            for trustee, relationship in self.trust_relationships[source].items():
                if relationship["trust_level"] > 0.5:  # Minimum trust threshold
                    path = self.get_trust_path(trustee, target, max_hops - 1)
                    if path:
                        return [source] + path
        
        return None
    
    def calculate_indirect_trust(self, source: str, target: str) -> float:
        """Calculate indirect trust through the network."""
        path = self.get_trust_path(source, target)
        if not path:
            return 0.0
        
        # Calculate trust as product of trust levels along the path
        trust = 1.0
        for i in range(len(path) - 1):
            current = path[i]
            next_agent = path[i + 1]
            
            if current in self.trust_relationships and next_agent in self.trust_relationships[current]:
                trust *= self.trust_relationships[current][next_agent]["trust_level"]
            else:
                return 0.0
        
        return trust
    
    def add_to_blacklist(self, agent_id: str, reason: str):
        """Add an agent to the blacklist."""
        self.blacklist.add(agent_id)
        logging.warning(f"Added {agent_id} to blacklist: {reason}")
    
    def add_to_whitelist(self, agent_id: str, reason: str):
        """Add an agent to the whitelist."""
        self.whitelist.add(agent_id)
        logging.info(f"Added {agent_id} to whitelist: {reason}")
    
    def is_trusted(self, agent_id: str) -> bool:
        """Check if an agent is trusted."""
        if agent_id in self.blacklist:
            return False
        if agent_id in self.whitelist:
            return True
        return True  # Default to trusted if not explicitly listed
