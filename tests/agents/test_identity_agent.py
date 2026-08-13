"""IdentityAgent tests.

Registration goes through the real payment gate and the real ledger, backed by
the fake LNbits from conftest — so these also cover the single-use and
service-binding behaviour of a paid registration.
"""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from src.agents.identity_agent import IdentityAgent
from src.agents.identity_agent.store import upsert_identity_metadata

# Registration now requires a real 64-hex Nostr key; the endpoint used to accept
# any string, including another node's handle namespace.
PUBKEY_A = "a" * 64
PUBKEY_B = "b" * 64
PUBKEY_C = "c" * 64
RELAYS = ["wss://relay.damus.io"]


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "identity_agent.db"


@pytest.fixture
def agent(db_path, paid_gate):
    return IdentityAgent(db_path=db_path)


async def _register(agent, fake_lnbits, pubkey, handle, domain="example.com"):
    """Run the full quote → pay → verify registration handshake."""
    quote = await agent.register_nip05(
        pubkey=pubkey, handle=handle, domain=domain, relays=RELAYS
    )
    fake_lnbits.settle(quote["payment_hash"])
    return await agent.register_nip05(
        pubkey=pubkey,
        handle=handle,
        domain=domain,
        relays=RELAYS,
        payment_hash=quote["payment_hash"],
    )


class TestMetadata:
    def test_exposes_agent_metadata_and_pricing(self, agent):
        info = agent.get_info()

        assert info["name"] == "IdentityAgent"
        assert "version" in info
        assert info["pricing"]["identity.register_nip05"] == 1000
        assert info["pricing"]["identity.get_identity"] == 10
        assert info["pricing"]["identity.list_verified"] == 25
        assert info["pricing"]["identity.search"] == 25
        assert info["pricing"]["identity.get_trust_signal"] == 10

    def test_all_required_service_names_exist(self, agent):
        required = {
            "identity.register_nip05",
            "identity.get_identity",
            "identity.list_verified",
            "identity.search",
            "identity.get_trust_signal",
        }
        assert required.issubset(set(agent.list_services()))


class TestRegistration:
    async def test_returns_an_invoice_when_unpaid(self, agent):
        result = await agent.register_nip05(
            pubkey=PUBKEY_A, handle="alice", domain="example.com", relays=RELAYS
        )

        assert result["payment_required"] is True
        assert result["amount_sats"] == 1000
        assert "payment_request" in result
        assert "payment_hash" in result

    async def test_marks_identity_verified_after_payment(self, agent, fake_lnbits):
        verified = await _register(agent, fake_lnbits, PUBKEY_A, "bob")

        assert verified["status"] == "verified"
        assert verified["nip05"] == "bob@example.com"
        assert verified["pubkey"] == PUBKEY_A

    async def test_sets_an_expiry_on_the_registration(self, agent, fake_lnbits):
        # expires_at was previously never set, so registrations were perpetual
        # despite the resolver honouring the column.
        verified = await _register(agent, fake_lnbits, PUBKEY_A, "bob")

        expires = datetime.fromisoformat(verified["expires_at"])
        assert expires > datetime.now(timezone.utc)

    async def test_an_unpaid_registration_is_not_verified(self, agent):
        await agent.register_nip05(
            pubkey=PUBKEY_A, handle="alice", domain="example.com", relays=RELAYS
        )

        identity = await agent.get_identity(pubkey=PUBKEY_A)
        assert identity["verified"] is False

    async def test_blocks_duplicate_handle_domain(self, agent, fake_lnbits):
        await _register(agent, fake_lnbits, PUBKEY_A, "carol")

        duplicate = await agent.register_nip05(
            pubkey=PUBKEY_B, handle="carol", domain="example.com", relays=RELAYS
        )

        assert "error" in duplicate
        assert "already registered" in duplicate["error"]

    async def test_a_pending_registration_holds_the_handle(self, agent):
        await agent.register_nip05(
            pubkey=PUBKEY_A, handle="dave", domain="example.com", relays=RELAYS
        )

        second = await agent.register_nip05(
            pubkey=PUBKEY_B, handle="dave", domain="example.com", relays=RELAYS
        )

        assert "in progress" in second["error"]

    async def test_an_abandoned_quote_releases_the_handle(self, agent, db_path):
        """Unpaid quotes must not squat handles forever.

        A pending row is written before payment and UNIQUE(handle, domain) then
        blocks everyone else, so without reclamation an attacker could lock every
        handle on the node for free.
        """
        await agent.register_nip05(
            pubkey=PUBKEY_A, handle="eve", domain="example.com", relays=RELAYS
        )
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE identities SET quote_expires_at = ? WHERE pubkey = ?",
                ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), PUBKEY_A),
            )
            conn.commit()

        second = await agent.register_nip05(
            pubkey=PUBKEY_B, handle="eve", domain="example.com", relays=RELAYS
        )

        assert second.get("payment_required") is True

    async def test_a_replayed_registration_payment_is_refused(self, agent, fake_lnbits):
        await _register(agent, fake_lnbits, PUBKEY_A, "frank")
        used_hash = next(iter(fake_lnbits.paid))

        replay = await agent.register_nip05(
            pubkey=PUBKEY_A,
            handle="frank",
            domain="example.com",
            relays=RELAYS,
            payment_hash=used_hash,
        )

        assert replay.get("error") == "already_consumed"


class TestValidation:
    @pytest.mark.parametrize(
        "pubkey,handle,domain,expected",
        [
            ("not-hex", "alice", "example.com", "pubkey"),
            (PUBKEY_A, "Alice Smith!", "example.com", "handle"),
            (PUBKEY_A, "alice", "not a domain", "domain"),
        ],
    )
    async def test_rejects_malformed_input(self, agent, pubkey, handle, domain, expected):
        result = await agent.register_nip05(
            pubkey=pubkey, handle=handle, domain=domain, relays=RELAYS
        )

        assert expected in result["error"]

    async def test_missing_fields_are_rejected(self, agent):
        result = await agent.register_nip05(pubkey="", handle="", domain="")
        assert "error" in result


class TestTrust:
    async def test_get_identity_returns_machine_readable_output(
        self, agent, fake_lnbits, db_path
    ):
        await _register(agent, fake_lnbits, PUBKEY_A, "alice")
        upsert_identity_metadata(
            pubkey=PUBKEY_A,
            category="dev",
            tags=["nostr", "lightning", "agent"],
            trust_score=0.75,
            db_path=db_path,
        )

        identity = await agent.get_identity(pubkey=PUBKEY_A)

        assert identity["pubkey"] == PUBKEY_A
        assert identity["handle"] == "alice"
        assert identity["nip05"] == "alice@example.com"
        assert identity["verified"] is True
        assert identity["category"] == "dev"
        assert identity["tags"] == ["nostr", "lightning", "agent"]
        assert identity["trust_score"] == 0.95

    async def test_trust_signal_is_deterministic_and_warns(self, agent, fake_lnbits, db_path):
        await _register(agent, fake_lnbits, PUBKEY_A, "trusty")
        upsert_identity_metadata(
            pubkey=PUBKEY_A,
            category="dev",
            tags=["nostr", "lightning", "agent"],
            trust_score=0.75,
            db_path=db_path,
        )

        first = await agent.get_trust_signal(pubkey=PUBKEY_A)
        second = await agent.get_trust_signal(pubkey=PUBKEY_A)

        assert first == second
        assert first["pubkey"] == PUBKEY_A
        assert first["trusted"] is True
        assert first["trust_score"] == 0.95
        assert first["basis"] == [
            "paid_nip05",
            "active_registration",
            "category_present",
            "tags_present",
        ]
        assert first["warning"] == "Trust score is heuristic and not KYC."

    async def test_expired_registration_scores_lower(self, agent, fake_lnbits, db_path):
        await _register(agent, fake_lnbits, PUBKEY_A, "old")
        upsert_identity_metadata(
            pubkey=PUBKEY_A,
            category="dev",
            tags=["nostr", "lightning", "agent"],
            trust_score=0.1,
            db_path=db_path,
        )
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE identities SET expires_at = ? WHERE pubkey = ?",
                ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), PUBKEY_A),
            )
            conn.commit()

        trust = await agent.get_trust_signal(pubkey=PUBKEY_A)

        assert trust["trust_score"] == 0.7
        assert "active_registration" not in trust["basis"]

    async def test_trust_score_capped_at_one(self, agent, fake_lnbits, db_path):
        await _register(agent, fake_lnbits, PUBKEY_C, "cap")
        upsert_identity_metadata(
            pubkey=PUBKEY_C,
            category="dev",
            tags=["a", "b", "c", "d", "e", "f", "g"],
            trust_score=0.9,
            db_path=db_path,
        )

        trust = await agent.get_trust_signal(pubkey=PUBKEY_C)

        assert trust["trust_score"] <= 1.0

    async def test_unknown_pubkey_is_untrusted(self, agent):
        trust = await agent.get_trust_signal(pubkey=PUBKEY_B)

        assert trust["trusted"] is False
        assert trust["trust_score"] == 0.0
