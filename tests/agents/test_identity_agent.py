import unittest
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from src.agents.identity_agent import IdentityAgent
from src.agents.identity_agent.store import upsert_identity_metadata


class _MockWallet:
    def __init__(self):
        self.created: list[dict] = []
        self._paid: set[str] = set()

    def create_invoice(self, amount: int, memo: str = "") -> dict:
        payment_hash = f"hash_{len(self.created) + 1}"
        invoice = {"payment_hash": payment_hash, "bolt11": f"ln_invoice_{payment_hash}"}
        self.created.append({"amount": amount, "memo": memo, "invoice": invoice})
        return invoice

    def check_invoice(self, checking_id: str) -> bool:
        return checking_id in self._paid

    def mark_paid(self, checking_id: str) -> None:
        self._paid.add(checking_id)


class TestIdentityAgent(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "identity_agent.db"
        self.wallet = _MockWallet()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_exposes_agent_metadata_and_pricing(self):
        agent = IdentityAgent(db_path=self.db_path, wallet=self.wallet)
        info = agent.get_info()

        self.assertEqual(info["name"], "IdentityAgent")
        self.assertIn("version", info)
        self.assertIn("services", info)
        self.assertIn("pricing", info)

        self.assertEqual(info["pricing"]["identity.register_nip05"], 1000)
        self.assertEqual(info["pricing"]["identity.get_identity"], 10)
        self.assertEqual(info["pricing"]["identity.list_verified"], 25)
        self.assertEqual(info["pricing"]["identity.search"], 25)
        self.assertEqual(info["pricing"]["identity.get_trust_signal"], 10)

    def test_all_required_service_names_exist(self):
        agent = IdentityAgent(db_path=self.db_path, wallet=self.wallet)
        service_names = set(agent.list_services())

        required = {
            "identity.register_nip05",
            "identity.get_identity",
            "identity.list_verified",
            "identity.search",
            "identity.get_trust_signal",
        }
        self.assertTrue(required.issubset(service_names))

    def test_register_nip05_returns_invoice_when_unpaid(self):
        agent = IdentityAgent(db_path=self.db_path, wallet=self.wallet)
        result = self._run(
            agent.register_nip05(
                pubkey="pubkey_invoice",
                handle="alice",
                domain="example.com",
                relays=["wss://relay.damus.io"],
            )
        )

        self.assertTrue(result["payment_required"])
        self.assertEqual(result["amount_sats"], 1000)
        self.assertIn("payment_request", result)
        self.assertIn("payment_hash", result)

    def test_register_nip05_marks_identity_verified_after_payment(self):
        agent = IdentityAgent(db_path=self.db_path, wallet=self.wallet)
        pending = self._run(
            agent.register_nip05(
                pubkey="pubkey_paid",
                handle="bob",
                domain="example.com",
                relays=["wss://relay.damus.io"],
            )
        )
        self.wallet.mark_paid(pending["payment_hash"])

        verified = self._run(
            agent.register_nip05(
                pubkey="pubkey_paid",
                handle="bob",
                domain="example.com",
                relays=["wss://relay.damus.io"],
                payment_hash=pending["payment_hash"],
            )
        )

        self.assertEqual(verified["status"], "verified")
        self.assertEqual(verified["nip05"], "bob@example.com")
        self.assertEqual(verified["pubkey"], "pubkey_paid")

    def test_register_nip05_blocks_duplicate_handle_domain(self):
        agent = IdentityAgent(db_path=self.db_path, wallet=self.wallet)
        first = self._run(
            agent.register_nip05(
                pubkey="pubkey_first",
                handle="carol",
                domain="example.com",
                relays=["wss://relay.damus.io"],
            )
        )
        self.assertTrue(first["payment_required"])

        duplicate = self._run(
            agent.register_nip05(
                pubkey="pubkey_second",
                handle="carol",
                domain="example.com",
                relays=["wss://relay.damus.io"],
            )
        )
        self.assertIn("error", duplicate)
        self.assertIn("already exists", duplicate["error"])

    def test_get_identity_by_pubkey_returns_machine_readable_output(self):
        agent = IdentityAgent(db_path=self.db_path, wallet=self.wallet)
        pending = self._run(
            agent.register_nip05(
                pubkey="pubkey_identity",
                handle="alice",
                domain="example.com",
                relays=["wss://relay.damus.io"],
            )
        )
        self.wallet.mark_paid(pending["payment_hash"])
        self._run(
            agent.register_nip05(
                pubkey="pubkey_identity",
                handle="alice",
                domain="example.com",
                relays=["wss://relay.damus.io"],
                payment_hash=pending["payment_hash"],
            )
        )
        upsert_identity_metadata(
            pubkey="pubkey_identity",
            category="dev",
            tags=["nostr", "lightning", "agent"],
            trust_score=0.75,
            db_path=self.db_path,
        )

        identity = self._run(agent.get_identity(pubkey="pubkey_identity"))
        self.assertEqual(identity["pubkey"], "pubkey_identity")
        self.assertEqual(identity["handle"], "alice")
        self.assertEqual(identity["nip05"], "alice@example.com")
        self.assertTrue(identity["verified"])
        self.assertEqual(identity["category"], "dev")
        self.assertEqual(identity["tags"], ["nostr", "lightning", "agent"])
        self.assertEqual(identity["trust_score"], 0.95)

    def test_get_trust_signal_is_deterministic_and_has_warning(self):
        agent = IdentityAgent(db_path=self.db_path, wallet=self.wallet)
        pending = self._run(
            agent.register_nip05(
                pubkey="pubkey_trust",
                handle="trusty",
                domain="example.com",
                relays=["wss://relay.damus.io"],
            )
        )
        self.wallet.mark_paid(pending["payment_hash"])
        self._run(
            agent.register_nip05(
                pubkey="pubkey_trust",
                handle="trusty",
                domain="example.com",
                relays=["wss://relay.damus.io"],
                payment_hash=pending["payment_hash"],
            )
        )
        upsert_identity_metadata(
            pubkey="pubkey_trust",
            category="dev",
            tags=["nostr", "lightning", "agent"],
            trust_score=0.75,
            db_path=self.db_path,
        )

        trust_a = self._run(agent.get_trust_signal(pubkey="pubkey_trust"))
        trust_b = self._run(agent.get_trust_signal(pubkey="pubkey_trust"))
        self.assertEqual(trust_a, trust_b)
        self.assertEqual(trust_a["pubkey"], "pubkey_trust")
        self.assertTrue(trust_a["trusted"])
        self.assertEqual(trust_a["trust_score"], 0.95)
        self.assertEqual(
            trust_a["basis"],
            ["paid_nip05", "active_registration", "category_present", "tags_present"],
        )
        self.assertEqual(trust_a["warning"], "Trust score is heuristic and not KYC.")

    def test_expired_user_scores_lower(self):
        agent = IdentityAgent(db_path=self.db_path, wallet=self.wallet)
        pending = self._run(
            agent.register_nip05(
                pubkey="pubkey_expired",
                handle="old",
                domain="example.com",
                relays=["wss://relay.damus.io"],
            )
        )
        self.wallet.mark_paid(pending["payment_hash"])
        self._run(
            agent.register_nip05(
                pubkey="pubkey_expired",
                handle="old",
                domain="example.com",
                relays=["wss://relay.damus.io"],
                payment_hash=pending["payment_hash"],
            )
        )
        upsert_identity_metadata(
            pubkey="pubkey_expired",
            category="dev",
            tags=["nostr", "lightning", "agent"],
            trust_score=0.1,
            db_path=self.db_path,
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE identities SET expires_at = ? WHERE pubkey = ?",
                ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), "pubkey_expired"),
            )
            conn.commit()

        trust = self._run(agent.get_trust_signal(pubkey="pubkey_expired"))
        self.assertEqual(trust["trust_score"], 0.7)
        self.assertNotIn("active_registration", trust["basis"])

    def test_trust_score_capped_at_one(self):
        agent = IdentityAgent(db_path=self.db_path, wallet=self.wallet)
        pending = self._run(
            agent.register_nip05(
                pubkey="pubkey_cap",
                handle="cap",
                domain="example.com",
                relays=["wss://relay.damus.io"],
            )
        )
        self.wallet.mark_paid(pending["payment_hash"])
        self._run(
            agent.register_nip05(
                pubkey="pubkey_cap",
                handle="cap",
                domain="example.com",
                relays=["wss://relay.damus.io"],
                payment_hash=pending["payment_hash"],
            )
        )
        upsert_identity_metadata(
            pubkey="pubkey_cap",
            category="dev",
            tags=["a", "b", "c", "d", "e", "f"],
            trust_score=0.0,
            db_path=self.db_path,
        )

        trust = self._run(agent.get_trust_signal(pubkey="pubkey_cap"))
        self.assertEqual(trust["trust_score"], 1.0)

    def _run(self, coro):
        import asyncio

        return asyncio.run(coro)


if __name__ == "__main__":
    unittest.main()
