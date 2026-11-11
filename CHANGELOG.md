# Changelog

## 0.1.0

First release as **AIR Agent KYA**.

- Renamed to **AIR Agent KYA**: plugin `air-agent-kya` (was `air-kya`), skill `air-agent-kya`,
  toolset `air_agent_kya`. Commands (`hermes air …`, `/air`) and tools (`kya_visit`, `air_whoami`)
  are unchanged.
- An existing delegation under the old `air-kya` plugin-data dir is copied over on first use, so no
  new `hermes air login` is needed.
- Endpoint and storage overrides moved from environment variables (`AIR_PARTNER_ID`,
  `AIR_CONSOLE_URL`, `AIR_API_URL`, `AIR_CREDENTIAL_API_URL`, `AIR_KYA_AGENT_DIR`) to plugin settings
  (`partner_id`, `console_url`, `api_url`, `credential_api_url`, `agent_dir`). Defaults unchanged.
- `requires_hermes: ">=0.23.0"`, author, LICENSE, CI, disclosures and catalog entry draft added.

## Pre-release history (as `air-kya`)

### air-kya 0.2.1

- An agent that isn't delegated now gets the site's no-proof (Standard) catalog with a hint, instead
  of a `NOT_DELEGATED` error.
- `hermes air visit` prints the catalog name (Standard / VIP).

### air-kya 0.2.0

- Rewritten to match mocaverse/air-kya `agent/`: AIR Console device-code login, SPKI PEM session
  proof, `/.well-known/air-kya`, `POST /kya/challenge`, `X-AIR-KYA`, mock profiles.

### air-kya 0.1.0

- First draft (superseded).
