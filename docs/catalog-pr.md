# PR text for the Hermes plugin catalog

**Title:** Add air-agent-kya (AIR Agent KYA) to the plugin catalog

**Body:**

Adds `plugin-catalog/air-agent-kya.yaml`, pinned to `<sha>` of
https://github.com/MocaNetwork/air-agent-hermes (submitted by the repository owner, rule 5).

### What it does
Know-Your-Agent with AIR (Moca Network). The user delegates their AIR identity to Hermes once
(`hermes air login`: AIR Console device code, P-256 agent key, `credentials.verify`, no wallet
signing). The `kya_visit` tool then enters stores that publish `/.well-known/air-kya`, asks AIR for a
one-time SD-JWT presentation bound to the store's nonce that discloses only the requested claims, and
returns the catalog that credential unlocks. Agents that aren't delegated get the public catalog.

### Surfaces used
- Tools: `kya_visit`, `air_whoami` (`ctx.register_tool`)
- Hook: `pre_tool_call`: returns `{"action": "approve"}` for live `kya_visit` so Hermes's approval
  gate asks before disclosure (never auto-approves; rule 12)
- CLI: `hermes air login|whoami|logout|visit` (`ctx.register_cli_command`)
- Slash command: `/air whoami` (`ctx.register_command`)
- Skill: `air-agent-kya:air-agent-kya` (`ctx.register_skill`)
- Storage: `plugin_data_dir("air-agent-kya")`
- Settings: `config_schema` (endpoints, approval toggle, `allow_local_sites`); no `requires_env`, no secrets

### Disclosures (rule 13)
- **Network:** AIR Console `sandbox.agents.air3.com` (login only); AIR API `air.api.sandbox.air3.com`;
  AIR credential API `credential-testnet.api.sandbox.air3.com`; each KYA site the agent is asked to
  visit (`GET /.well-known/air-kya`, `POST /kya/challenge`, `GET /catalog`). https only, public
  addresses only (resolved, checked and pinned per connection); localhost only in mock mode or with
  `allow_local_sites`.
- **Stored credentials:** P-256 agent private key + AIR delegation bundle in the plugin's own
  plugin-data dir, mode 0600; `hermes air logout` deletes them.
- **Reads outside its data:** once, the old `air-kya` plugin-data dir, to carry over a delegation
  made before the rename.
- **Disclosure of user data:** only the SD-JWT claims the site requests, only after approval, only to
  the origin that issued the nonce. The model never receives the presentation, key or tokens.
- **None:** shell, subprocess, background threads/processes, telemetry, `.env`/credential-store reads.

### Unattended runs (rule 12)
`kya_visit` escalates to Hermes's approval gate; under cron/gateway it is handled by Hermes (no
auto-approve). Login is a user-run terminal command that exits when the device code expires.

### Checks
- `hermes plugins validate . --install-deps`: <paste result>
- CI: unit tests + e2e against the real KYA demo Worker and mock AIR (11 profiles)
- Dependencies: `httpx>=0.27,<1`, `cryptography>=42,<47` (old compatible floors, upper bounds; CI
  installs with a 3-day `--exclude-newer` quarantine)
