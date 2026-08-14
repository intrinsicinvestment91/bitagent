#!/usr/bin/env python3
"""
Live deployment testing script for BitAgent on Start9.
Tests all endpoints and security features.
"""

import sys

import requests


class BitAgentLiveTester:
    def __init__(self, base_url: str, api_keys: dict[str, str]):
        self.base_url = base_url.rstrip("/")
        self.api_keys = api_keys
        self.session = requests.Session()

    def test_health(self) -> bool:
        """Test health endpoint."""
        print("🏥 Testing health endpoint...")
        try:
            response = self.session.get(f"{self.base_url}/health")
            if response.status_code == 200:
                print("✅ Health check passed")
                return True
            else:
                print(f"❌ Health check failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Health check error: {e}")
            return False

    def test_wallet_balance(self) -> bool:
        """Test wallet balance endpoint."""
        print("💰 Testing wallet balance...")
        try:
            response = self.session.get(f"{self.base_url}/wallet/balance")
            if response.status_code == 200:
                data = response.json()
                balance = data.get("balance_sats", 0)
                print(f"✅ Wallet balance: {balance} sats")
                return True
            else:
                print(f"❌ Wallet balance failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Wallet balance error: {e}")
            return False

    def test_agent_status(self) -> bool:
        """Test agent status endpoint."""
        print("🤖 Testing agent status...")
        try:
            response = self.session.get(f"{self.base_url}/agents/status")
            if response.status_code == 200:
                data = response.json()
                agents = data.get("agents", {})
                print(f"✅ Agent status: {len(agents)} agents running")
                for agent_name, status in agents.items():
                    print(f"   - {agent_name}: {status.get('status', 'unknown')}")
                return True
            else:
                print(f"❌ Agent status failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Agent status error: {e}")
            return False

    def test_authentication_required(self) -> bool:
        """Test that authentication is required."""
        print("🔐 Testing authentication requirements...")
        endpoints = [
            "/polyglot/translate",
            "/polyglot/transcribe",
            "/coordinator/translate_audio",
            "/coordinator/chain_tasks",
        ]

        all_passed = True
        for endpoint in endpoints:
            try:
                response = self.session.post(f"{self.base_url}{endpoint}", json={})
                if response.status_code == 401:
                    print(f"✅ {endpoint} - Authentication required")
                else:
                    print(
                        f"❌ {endpoint} - Authentication NOT required (status: {response.status_code})"
                    )
                    all_passed = False
            except Exception as e:
                print(f"⚠️  {endpoint} - Error testing: {e}")
                all_passed = False

        return all_passed

    def test_payment_required(self) -> bool:
        """Test that payment is required."""
        print("💳 Testing payment requirements...")

        if "polyglot" not in self.api_keys:
            print("❌ No PolyglotAgent API key available")
            return False

        headers = {"Authorization": f"Bearer {self.api_keys['polyglot']}"}

        try:
            # Test without payment hash
            response = self.session.post(
                f"{self.base_url}/polyglot/translate",
                headers=headers,
                json={"text": "Hello", "source_lang": "en", "target_lang": "es"},
            )

            if response.status_code == 402:
                print("✅ Payment required when no payment hash provided")
                return True
            else:
                print(f"❌ Payment not required (status: {response.status_code})")
                return False
        except Exception as e:
            print(f"❌ Payment test error: {e}")
            return False

    def test_polyglot_translation(self) -> bool:
        """Test PolyglotAgent translation."""
        print("🌍 Testing PolyglotAgent translation...")

        if "polyglot" not in self.api_keys:
            print("❌ No PolyglotAgent API key available")
            return False

        headers = {"Authorization": f"Bearer {self.api_keys['polyglot']}"}

        try:
            # Test with mock payment hash
            response = self.session.post(
                f"{self.base_url}/polyglot/translate",
                headers=headers,
                json={
                    "text": "Hello world",
                    "source_lang": "en",
                    "target_lang": "es",
                    "payment_hash": "test_hash",
                },
            )

            if response.status_code in [200, 402]:  # 402 is payment required
                print("✅ PolyglotAgent translation endpoint working")
                return True
            else:
                print(f"❌ PolyglotAgent translation failed (status: {response.status_code})")
                return False
        except Exception as e:
            print(f"❌ PolyglotAgent translation error: {e}")
            return False

    def test_coordinator_tasks(self) -> bool:
        """Test CoordinatorAgent task chaining."""
        print("🔗 Testing CoordinatorAgent task chaining...")

        if "coordinator" not in self.api_keys:
            print("❌ No CoordinatorAgent API key available")
            return False

        headers = {"Authorization": f"Bearer {self.api_keys['coordinator']}"}

        try:
            response = self.session.post(
                f"{self.base_url}/coordinator/chain_tasks",
                headers=headers,
                json={
                    "tasks": [{"service": "test", "parameters": {"param": "value"}}],
                    "payment_hash": "test_hash",
                },
            )

            if response.status_code in [200, 402]:  # 402 is payment required
                print("✅ CoordinatorAgent task chaining endpoint working")
                return True
            else:
                print(f"❌ CoordinatorAgent task chaining failed (status: {response.status_code})")
                return False
        except Exception as e:
            print(f"❌ CoordinatorAgent task chaining error: {e}")
            return False

    def test_streamfinder(self) -> bool:
        """Test StreamfinderAgent."""
        print("🎬 Testing StreamfinderAgent...")

        try:
            response = self.session.post(
                f"{self.base_url}/a2a",
                json={
                    "method": "streamfinder.search",
                    "params": {"query": "Oppenheimer", "payment_hash": "test_hash"},
                },
            )

            if response.status_code in [200, 402]:  # 402 is payment required
                print("✅ StreamfinderAgent endpoint working")
                return True
            else:
                print(f"❌ StreamfinderAgent failed (status: {response.status_code})")
                return False
        except Exception as e:
            print(f"❌ StreamfinderAgent error: {e}")
            return False

    def test_input_validation(self) -> bool:
        """Test input validation."""
        print("🛡️ Testing input validation...")

        if "polyglot" not in self.api_keys:
            print("❌ No PolyglotAgent API key available")
            return False

        headers = {"Authorization": f"Bearer {self.api_keys['polyglot']}"}

        try:
            # Test oversized input
            response = self.session.post(
                f"{self.base_url}/polyglot/translate",
                headers=headers,
                json={
                    "text": "x" * 20000,  # Too long
                    "source_lang": "en",
                    "target_lang": "es",
                    "payment_hash": "test_hash",
                },
            )

            if response.status_code == 422:  # Validation error
                print("✅ Input validation working - oversized input rejected")
                return True
            else:
                print(f"❌ Input validation failed (status: {response.status_code})")
                return False
        except Exception as e:
            print(f"❌ Input validation error: {e}")
            return False

    def run_all_tests(self) -> bool:
        """Run all tests."""
        print("🚀 Starting BitAgent Live Deployment Tests...\n")

        tests = [
            self.test_health,
            self.test_wallet_balance,
            self.test_agent_status,
            self.test_authentication_required,
            self.test_payment_required,
            self.test_polyglot_translation,
            self.test_coordinator_tasks,
            self.test_streamfinder,
            self.test_input_validation,
        ]

        passed = 0
        total = len(tests)

        for test in tests:
            try:
                if test():
                    passed += 1
                print()  # Add spacing between tests
            except Exception as e:
                print(f"❌ Test failed with exception: {e}\n")

        print("📊 Test Results:")
        print(f"   Passed: {passed}/{total}")
        print(f"   Success Rate: {(passed / total) * 100:.1f}%")

        if passed == total:
            print("\n🎉 All tests passed! Your BitAgent system is working perfectly!")
            return True
        else:
            print(f"\n⚠️  {total - passed} tests failed. Check the issues above.")
            return False


def load_api_keys(filename: str = "api_keys.txt") -> dict[str, str]:
    """Load API keys from file."""
    api_keys = {}
    try:
        with open(filename) as f:
            for line in f:
                if ":" in line:
                    agent, key = line.strip().split(":", 1)
                    api_keys[agent.strip().lower().replace("agent", "")] = key.strip()
    except FileNotFoundError:
        print(f"❌ API keys file {filename} not found")
        print("   Run the deployment script to generate API keys")
    except Exception as e:
        print(f"❌ Error loading API keys: {e}")

    return api_keys


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description="Test BitAgent live deployment")
    parser.add_argument(
        "--url", default="http://localhost:8000", help="Base URL of BitAgent service"
    )
    parser.add_argument("--keys", default="api_keys.txt", help="API keys file")

    args = parser.parse_args()

    # Load API keys
    api_keys = load_api_keys(args.keys)

    if not api_keys:
        print("❌ No API keys loaded. Cannot run authenticated tests.")
        print("   Run the deployment script to generate API keys first.")
        return False

    # Create tester
    tester = BitAgentLiveTester(args.url, api_keys)

    # Run tests
    return tester.run_all_tests()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
