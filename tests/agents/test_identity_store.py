import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.agents.identity_agent.store import (
    create_pending_identity,
    get_identity_by_handle,
    get_identity_by_pubkey,
    init_db,
    list_verified,
    mark_paid_and_verified,
    search_identities,
)


class TestIdentityStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "identity_agent.db"
        init_db(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_and_fetch_identity(self):
        created_id = create_pending_identity(
            pubkey="pubkey_1",
            handle="alice",
            domain="example.com",
            payment_hash="hash_1",
            relays=["wss://relay.example.com"],
            db_path=self.db_path,
        )
        self.assertGreater(created_id, 0)

        by_pubkey = get_identity_by_pubkey("pubkey_1", db_path=self.db_path)
        self.assertIsNotNone(by_pubkey)
        self.assertEqual(by_pubkey["nip05"], "alice@example.com")
        self.assertFalse(by_pubkey["verified"])
        self.assertEqual(by_pubkey["relays"], ["wss://relay.example.com"])

        by_handle = get_identity_by_handle("alice", "example.com", db_path=self.db_path)
        self.assertIsNotNone(by_handle)
        self.assertEqual(by_handle["pubkey"], "pubkey_1")

    def test_mark_verified_and_list_verified(self):
        create_pending_identity(
            pubkey="pubkey_2",
            handle="bob",
            domain="example.com",
            payment_hash="hash_2",
            db_path=self.db_path,
        )
        updated = mark_paid_and_verified("pubkey_2", db_path=self.db_path)
        self.assertTrue(updated)

        identity = get_identity_by_pubkey("pubkey_2", db_path=self.db_path)
        self.assertTrue(identity["paid"])
        self.assertTrue(identity["verified"])

        verified = list_verified(db_path=self.db_path)
        self.assertEqual(len(verified), 1)
        self.assertEqual(verified[0]["pubkey"], "pubkey_2")

    def test_search_identities(self):
        create_pending_identity(
            pubkey="pubkey_3",
            handle="carol",
            domain="sats.net",
            payment_hash="hash_3",
            db_path=self.db_path,
        )
        create_pending_identity(
            pubkey="pubkey_4",
            handle="dave",
            domain="example.org",
            payment_hash="hash_4",
            db_path=self.db_path,
        )
        mark_paid_and_verified("pubkey_4", db_path=self.db_path)

        results_by_handle = search_identities("car", db_path=self.db_path)
        self.assertEqual(len(results_by_handle), 1)
        self.assertEqual(results_by_handle[0]["pubkey"], "pubkey_3")

        results_by_domain = search_identities("example", db_path=self.db_path)
        self.assertEqual(len(results_by_domain), 1)
        self.assertEqual(results_by_domain[0]["pubkey"], "pubkey_4")

    def test_duplicate_handle_domain_rejected(self):
        create_pending_identity(
            pubkey="pubkey_5",
            handle="erin",
            domain="nostr.example",
            payment_hash="hash_5",
            db_path=self.db_path,
        )

        with self.assertRaises(sqlite3.IntegrityError):
            create_pending_identity(
                pubkey="pubkey_6",
                handle="erin",
                domain="nostr.example",
                payment_hash="hash_6",
                db_path=self.db_path,
            )


if __name__ == "__main__":
    unittest.main()
