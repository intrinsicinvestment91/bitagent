import { compat } from "../deps.ts";

// The nullable string fields below carry no `default`. Omitting it is how the
// compatibility layer expresses "no value": its DefaultString type does not
// admit null, and an empty string would be a value rather than an absence.
export const getConfig = compat.getConfig({
  "payments_enabled": {
    "name": "Enable Lightning payments",
    "description":
      "Off by default. While off, every service on this node is free and is labelled free in /health and /services — no LNbits wallet is needed. Turn it on only once the LNbits fields below are filled in; the node refuses to start if payments are enabled without them.",
    "type": "boolean",
    "default": false,
  },
  "nostr_discovery_enabled": {
    "name": "Enable public Nostr discovery",
    "description":
      "Off by default. While off, this node opens no Nostr relay connections, publishes no announcements and generates no DHT traffic. Turning it on announces this agent publicly, and requires both the Nostr private key and the public URL below; the node refuses to start without them.",
    "type": "boolean",
    "default": false,
  },
  "lnbits_url": {
    "name": "LNbits URL",
    "description":
      "Required only when Lightning payments are enabled. URL of your LNbits instance — use http://lnbits.embassy if LNbits runs on this server. Leave empty in free mode.",
    "type": "string",
    "nullable": true,
    "masked": false,
  },
  "lnbits_api_key": {
    "name": "LNbits Admin API Key",
    "description":
      "Required only when Lightning payments are enabled. Found in LNbits under your wallet → API info → Admin key. Leave empty in free mode.",
    "type": "string",
    "nullable": true,
    "masked": true,
  },
  "nostr_private_key": {
    "name": "Nostr Private Key",
    "description":
      "Used only when public Nostr discovery is enabled, where it is required: 64 hex characters (a 32-byte secp256k1 secret) giving this node a stable identity across restarts. Leave empty while discovery is disabled.",
    "type": "string",
    "nullable": true,
    "masked": true,
  },
  "public_url": {
    "name": "Public URL",
    "description":
      "Required only when public Nostr discovery is enabled: the http(s) address callers outside this machine use to reach the node. It cannot be localhost or 127.0.0.1, because an announcement carrying a loopback address tells readers to call themselves. Leave empty while discovery is disabled.",
    "type": "string",
    "nullable": true,
    "masked": false,
  },
});
