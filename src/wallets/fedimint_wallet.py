import os
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class FedimintWallet:
    """
    Client for fedimint-clientd HTTP daemon.
    Set FEDIMINT_CLIENTD_URL and FEDIMINT_CLIENTD_PASSWORD to enable.
    If not configured, enabled=False and all methods are no-ops.
    """

    def __init__(self):
        self.base_url = os.getenv("FEDIMINT_CLIENTD_URL", "").rstrip("/")
        self.password = os.getenv("FEDIMINT_CLIENTD_PASSWORD", "")
        self._enabled = bool(self.base_url and self.password)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.password}"}

    async def validate_notes(self, notes: str) -> Optional[int]:
        """Check ecash notes are valid. Returns amount in msats, or None if invalid. Does not redeem."""
        if not self._enabled:
            return None
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.base_url}/v2/mint/validate",
                    json={"notes": notes},
                    headers=self._headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                return resp.json().get("amount_msat")
        except Exception as e:
            logger.error(f"Fedimint validate error: {e}")
            return None

    async def receive_notes(self, notes: str) -> Optional[int]:
        """Redeem ecash notes into the federation wallet. Returns amount in msats or None on failure."""
        if not self._enabled:
            return None
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.base_url}/v2/mint/reissue",
                    json={"notes": notes},
                    headers=self._headers(),
                    timeout=30.0,
                )
                resp.raise_for_status()
                return resp.json().get("amount_msat")
        except Exception as e:
            logger.error(f"Fedimint reissue error: {e}")
            return None

    async def verify_and_receive(self, notes: str, price_sats: int) -> bool:
        """
        Validate that notes cover price_sats, then redeem them.
        Validate is non-destructive; reissue is the actual redemption.
        Returns True on success.
        """
        amount_msat = await self.validate_notes(notes)
        if amount_msat is None:
            return False
        if amount_msat < price_sats * 1000:
            logger.warning(
                f"Ecash underpayment: got {amount_msat} msat, need {price_sats * 1000} msat"
            )
            return False
        received = await self.receive_notes(notes)
        return received is not None

    async def get_balance_sats(self) -> Optional[int]:
        """Return current federation wallet balance in sats."""
        if not self._enabled:
            return None
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.base_url}/v2/admin/info",
                    headers=self._headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                msat = resp.json().get("total_amount_msat", 0)
                return msat // 1000
        except Exception as e:
            logger.error(f"Fedimint balance error: {e}")
            return None
