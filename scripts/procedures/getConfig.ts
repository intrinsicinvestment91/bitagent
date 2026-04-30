import { compat } from "../deps.ts";

export const getConfig = compat.getConfig({
  "lnbits_url": {
    "name": "LNbits URL",
    "description": "URL of your LNbits instance (e.g. http://lnbits.embassy)",
    "type": "string",
    "nullable": false,
    "masked": false,
    "default": "",
  },
  "lnbits_api_key": {
    "name": "LNbits Admin API Key",
    "description": "Admin key from LNbits wallet — API info tab",
    "type": "string",
    "nullable": false,
    "masked": true,
    "default": "",
  },
  "nostr_private_key": {
    "name": "Nostr Private Key (optional)",
    "description": "64-char hex key for Nostr agent discovery. Leave empty to disable.",
    "type": "string",
    "nullable": true,
    "masked": true,
    "default": null,
  },
});
