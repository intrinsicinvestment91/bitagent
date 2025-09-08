"""
Advanced payment security features including escrow, multi-signature, and fraud detection.
Implements secure payment flows with dispute resolution mechanisms.
"""

import time
import hashlib
import secrets
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import json
import logging
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend
import base64

class PaymentStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DISPUTED = "disputed"
    REFUNDED = "refunded"
    COMPLETED = "completed"
    FAILED = "failed"

class EscrowStatus(Enum):
    CREATED = "created"
    FUNDED = "funded"
    RELEASED = "released"
    DISPUTED = "disputed"
    REFUNDED = "refunded"

class DisputeStatus(Enum):
    OPEN = "open"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"
    CLOSED = "closed"

@dataclass
class EscrowPayment:
    """Escrow payment with multi-party security."""
    escrow_id: str
    buyer_id: str
    seller_id: str
    amount_sats: int
    service_description: str
    escrow_fee_sats: int
    status: EscrowStatus
    created_at: float
    funded_at: Optional[float]
    released_at: Optional[float]
    dispute_id: Optional[str]
    arbitrator_id: Optional[str]
    conditions: Dict[str, Any]
    signatures: Dict[str, str]

@dataclass
class PaymentDispute:
    """Payment dispute for escrow resolution."""
    dispute_id: str
    escrow_id: str
    complainant_id: str
    respondent_id: str
    arbitrator_id: str
    reason: str
    evidence: List[str]
    status: DisputeStatus
    created_at: float
    resolved_at: Optional[float]
    resolution: Optional[str]
    refund_amount: Optional[int]

@dataclass
class FraudDetectionRule:
    """Rule for fraud detection."""
    rule_id: str
    name: str
    description: str
    conditions: Dict[str, Any]
    severity: str
    action: str
    enabled: bool

class PaymentSecurityManager:
    """Manages secure payments with escrow and fraud detection."""
    
    def __init__(self):
        self.escrow_payments = {}
        self.disputes = {}
        self.fraud_rules = []
        self.payment_history = {}
        self.arbitrators = {}
        self.escrow_fee_rate = 0.01  # 1% escrow fee
        
        # Initialize default fraud detection rules
        self._initialize_fraud_rules()
    
    def create_escrow_payment(self, buyer_id: str, seller_id: str, amount_sats: int,
                            service_description: str, conditions: Dict[str, Any] = None,
                            arbitrator_id: str = None) -> EscrowPayment:
        """Create an escrow payment."""
        escrow_id = self._generate_escrow_id()
        escrow_fee = int(amount_sats * self.escrow_fee_rate)
        
        escrow = EscrowPayment(
            escrow_id=escrow_id,
            buyer_id=buyer_id,
            seller_id=seller_id,
            amount_sats=amount_sats,
            service_description=service_description,
            escrow_fee_sats=escrow_fee,
            status=EscrowStatus.CREATED,
            created_at=time.time(),
            funded_at=None,
            released_at=None,
            dispute_id=None,
            arbitrator_id=arbitrator_id,
            conditions=conditions or {},
            signatures={}
        )
        
        self.escrow_payments[escrow_id] = escrow
        logging.info(f"Created escrow payment {escrow_id} for {amount_sats} sats")
        return escrow
    
    def fund_escrow(self, escrow_id: str, payment_hash: str) -> bool:
        """Fund an escrow payment."""
        if escrow_id not in self.escrow_payments:
            return False
        
        escrow = self.escrow_payments[escrow_id]
        if escrow.status != EscrowStatus.CREATED:
            return False
        
        # Verify payment (this would integrate with your LNbits client)
        if self._verify_payment(payment_hash, escrow.amount_sats + escrow.escrow_fee_sats):
            escrow.status = EscrowStatus.FUNDED
            escrow.funded_at = time.time()
            escrow.signatures["funding"] = payment_hash
            
            # Run fraud detection
            if self._detect_fraud(escrow):
                self._handle_fraud_detection(escrow)
            
            logging.info(f"Escrow {escrow_id} funded with {escrow.amount_sats} sats")
            return True
        
        return False
    
    def release_escrow(self, escrow_id: str, release_reason: str = "Service completed") -> bool:
        """Release escrow funds to seller."""
        if escrow_id not in self.escrow_payments:
            return False
        
        escrow = self.escrow_payments[escrow_id]
        if escrow.status != EscrowStatus.FUNDED:
            return False
        
        # Check if conditions are met
        if not self._check_escrow_conditions(escrow):
            return False
        
        # Release funds (this would integrate with your payment system)
        if self._process_payment_release(escrow):
            escrow.status = EscrowStatus.RELEASED
            escrow.released_at = time.time()
            escrow.signatures["release"] = self._generate_release_signature(escrow, release_reason)
            
            logging.info(f"Escrow {escrow_id} released to seller")
            return True
        
        return False
    
    def create_dispute(self, escrow_id: str, complainant_id: str, reason: str,
                      evidence: List[str] = None) -> PaymentDispute:
        """Create a payment dispute."""
        if escrow_id not in self.escrow_payments:
            raise ValueError("Escrow not found")
        
        escrow = self.escrow_payments[escrow_id]
        if escrow.status not in [EscrowStatus.FUNDED, EscrowStatus.RELEASED]:
            raise ValueError("Invalid escrow status for dispute")
        
        dispute_id = self._generate_dispute_id()
        
        # Determine respondent
        respondent_id = escrow.seller_id if complainant_id == escrow.buyer_id else escrow.buyer_id
        
        # Assign arbitrator
        arbitrator_id = escrow.arbitrator_id or self._assign_arbitrator()
        
        dispute = PaymentDispute(
            dispute_id=dispute_id,
            escrow_id=escrow_id,
            complainant_id=complainant_id,
            respondent_id=respondent_id,
            arbitrator_id=arbitrator_id,
            reason=reason,
            evidence=evidence or [],
            status=DisputeStatus.OPEN,
            created_at=time.time(),
            resolved_at=None,
            resolution=None,
            refund_amount=None
        )
        
        self.disputes[dispute_id] = dispute
        escrow.dispute_id = dispute_id
        escrow.status = EscrowStatus.DISPUTED
        
        logging.info(f"Created dispute {dispute_id} for escrow {escrow_id}")
        return dispute
    
    def resolve_dispute(self, dispute_id: str, arbitrator_id: str, resolution: str,
                       refund_amount: Optional[int] = None) -> bool:
        """Resolve a payment dispute."""
        if dispute_id not in self.disputes:
            return False
        
        dispute = self.disputes[dispute_id]
        if dispute.arbitrator_id != arbitrator_id:
            return False
        
        if dispute.status != DisputeStatus.OPEN:
            return False
        
        dispute.status = DisputeStatus.RESOLVED
        dispute.resolved_at = time.time()
        dispute.resolution = resolution
        dispute.refund_amount = refund_amount
        
        # Update escrow status
        escrow = self.escrow_payments[dispute.escrow_id]
        if refund_amount and refund_amount > 0:
            escrow.status = EscrowStatus.REFUNDED
            # Process refund
            self._process_refund(escrow, refund_amount)
        else:
            escrow.status = EscrowStatus.RELEASED
            # Release to seller
            self._process_payment_release(escrow)
        
        logging.info(f"Dispute {dispute_id} resolved: {resolution}")
        return True
    
    def detect_payment_fraud(self, payment_data: Dict[str, Any]) -> List[str]:
        """Detect potential payment fraud."""
        triggered_rules = []
        
        for rule in self.fraud_rules:
            if not rule.enabled:
                continue
            
            if self._evaluate_fraud_rule(rule, payment_data):
                triggered_rules.append(rule.rule_id)
                logging.warning(f"Fraud rule triggered: {rule.name}")
        
        return triggered_rules
    
    def add_fraud_rule(self, rule: FraudDetectionRule):
        """Add a fraud detection rule."""
        self.fraud_rules.append(rule)
        logging.info(f"Added fraud detection rule: {rule.name}")
    
    def get_escrow_status(self, escrow_id: str) -> Optional[Dict[str, Any]]:
        """Get escrow payment status."""
        if escrow_id not in self.escrow_payments:
            return None
        
        escrow = self.escrow_payments[escrow_id]
        return asdict(escrow)
    
    def get_dispute_info(self, dispute_id: str) -> Optional[Dict[str, Any]]:
        """Get dispute information."""
        if dispute_id not in self.disputes:
            return None
        
        dispute = self.disputes[dispute_id]
        return asdict(dispute)
    
    def _generate_escrow_id(self) -> str:
        """Generate unique escrow ID."""
        return f"escrow_{secrets.token_hex(16)}"
    
    def _generate_dispute_id(self) -> str:
        """Generate unique dispute ID."""
        return f"dispute_{secrets.token_hex(16)}"
    
    def _verify_payment(self, payment_hash: str, expected_amount: int) -> bool:
        """Verify payment (integrate with your LNbits client)."""
        # This would integrate with your existing payment verification
        # For now, return True as a placeholder
        return True
    
    def _check_escrow_conditions(self, escrow: EscrowPayment) -> bool:
        """Check if escrow conditions are met."""
        # Implement condition checking logic
        # For now, return True
        return True
    
    def _process_payment_release(self, escrow: EscrowPayment) -> bool:
        """Process payment release to seller."""
        # This would integrate with your payment system
        # For now, return True as a placeholder
        return True
    
    def _process_refund(self, escrow: EscrowPayment, refund_amount: int) -> bool:
        """Process refund to buyer."""
        # This would integrate with your payment system
        # For now, return True as a placeholder
        return True
    
    def _generate_release_signature(self, escrow: EscrowPayment, reason: str) -> str:
        """Generate release signature."""
        data = f"{escrow.escrow_id}:{escrow.amount_sats}:{reason}:{time.time()}"
        return hashlib.sha256(data.encode()).hexdigest()
    
    def _assign_arbitrator(self) -> str:
        """Assign an arbitrator for dispute resolution."""
        # This would select from a pool of trusted arbitrators
        # For now, return a placeholder
        return "arbitrator_1"
    
    def _detect_fraud(self, escrow: EscrowPayment) -> bool:
        """Detect fraud in escrow payment."""
        payment_data = {
            "buyer_id": escrow.buyer_id,
            "seller_id": escrow.seller_id,
            "amount": escrow.amount_sats,
            "timestamp": escrow.created_at
        }
        
        triggered_rules = self.detect_payment_fraud(payment_data)
        return len(triggered_rules) > 0
    
    def _handle_fraud_detection(self, escrow: EscrowPayment):
        """Handle detected fraud."""
        logging.warning(f"Fraud detected in escrow {escrow.escrow_id}")
        # Implement fraud handling logic
        # Could include freezing funds, notifying parties, etc.
    
    def _evaluate_fraud_rule(self, rule: FraudDetectionRule, payment_data: Dict[str, Any]) -> bool:
        """Evaluate a fraud detection rule."""
        # Implement rule evaluation logic
        # For now, return False as a placeholder
        return False
    
    def _initialize_fraud_rules(self):
        """Initialize default fraud detection rules."""
        rules = [
            FraudDetectionRule(
                rule_id="high_amount",
                name="High Amount Transaction",
                description="Detect unusually high payment amounts",
                conditions={"amount_threshold": 1000000},  # 1M sats
                severity="medium",
                action="flag",
                enabled=True
            ),
            FraudDetectionRule(
                rule_id="rapid_transactions",
                name="Rapid Transaction Pattern",
                description="Detect rapid successive transactions",
                conditions={"time_window": 300, "max_transactions": 5},  # 5 transactions in 5 minutes
                severity="high",
                action="block",
                enabled=True
            ),
            FraudDetectionRule(
                rule_id="new_agent",
                name="New Agent Transaction",
                description="Flag transactions from new agents",
                conditions={"min_age_days": 7},
                severity="low",
                action="flag",
                enabled=True
            )
        ]
        
        for rule in rules:
            self.add_fraud_rule(rule)

class MultiSigWallet:
    """Multi-signature wallet for enhanced security."""
    
    def __init__(self, required_signatures: int = 2):
        self.required_signatures = required_signatures
        self.signers = {}
        self.pending_transactions = {}
        self.completed_transactions = {}
    
    def add_signer(self, signer_id: str, public_key: str):
        """Add a signer to the multi-sig wallet."""
        self.signers[signer_id] = {
            "public_key": public_key,
            "added_at": time.time()
        }
    
    def create_transaction(self, transaction_id: str, amount: int, recipient: str,
                          description: str = "") -> Dict[str, Any]:
        """Create a pending transaction requiring signatures."""
        transaction = {
            "transaction_id": transaction_id,
            "amount": amount,
            "recipient": recipient,
            "description": description,
            "created_at": time.time(),
            "signatures": {},
            "status": "pending"
        }
        
        self.pending_transactions[transaction_id] = transaction
        return transaction
    
    def sign_transaction(self, transaction_id: str, signer_id: str, signature: str) -> bool:
        """Sign a pending transaction."""
        if transaction_id not in self.pending_transactions:
            return False
        
        if signer_id not in self.signers:
            return False
        
        transaction = self.pending_transactions[transaction_id]
        transaction["signatures"][signer_id] = signature
        
        # Check if we have enough signatures
        if len(transaction["signatures"]) >= self.required_signatures:
            return self._execute_transaction(transaction_id)
        
        return True
    
    def _execute_transaction(self, transaction_id: str) -> bool:
        """Execute a fully signed transaction."""
        if transaction_id not in self.pending_transactions:
            return False
        
        transaction = self.pending_transactions[transaction_id]
        transaction["status"] = "executed"
        transaction["executed_at"] = time.time()
        
        # Move to completed transactions
        self.completed_transactions[transaction_id] = transaction
        del self.pending_transactions[transaction_id]
        
        # Here you would integrate with your actual payment system
        logging.info(f"Executed multi-sig transaction {transaction_id}")
        return True
    
    def get_transaction_status(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        """Get transaction status."""
        if transaction_id in self.pending_transactions:
            return self.pending_transactions[transaction_id]
        elif transaction_id in self.completed_transactions:
            return self.completed_transactions[transaction_id]
        return None
