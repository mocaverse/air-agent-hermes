# AIR Agent KYA — Hermes plugin

Lets your Hermes agent prove who it acts for. You delegate your AIR identity (Moca Network) to the
agent once, approving it in the AIR Console. When the agent visits a Know-Your-Agent (KYA) store, AIR
issues a one-time proof that discloses only the claim the store asks for (for example your membership
tier). The store checks it and returns the catalog your credential unlocks: public pricing for
everyone, VIP for verified members. You approve each disclosure, the agent never sees your
credential, and it can't sign or spend.

Native port of the agent in [mocaverse/air-kya](https://github.com/mocaverse/air-kya)
(`agent/air.ts`, `agent/cli.ts`). Same protocol, endpoints and headers; the KYA demo site, mock
issuer and policies live in that repo.

- Plugin: `air-agent-kya` · Requires Hermes `>=0.23.0` · License: MIT
- Demo store: https://kya.demo.air3.com

## Install

```bash
hermes plugins install mocaverse/air-agent-hermes --no-enable
hermes plugins enable air-agent-kya          # asks you to approve the Python dependencies
hermes air --help
```

From a local checkout:

```bash
cp -r air-agent-hermes ~/.hermes/plugins/air-agent-kya
hermes plugins validate ~/.hermes/plugins/air-agent-kya --install-deps
hermes plugins enable air-agent-kya
```

Upgrading from `air-kya` (≤0.2.1): disable and remove the old plugin, install this one. Your
delegation is carried over; no new login needed.

## Quick start

```bash
hermes air visit https://kya.demo.air3.com   # not delegated → public (Standard) catalog
hermes air login                             # approve in the AIR Console
hermes air visit https://kya.demo.air3.com   # → VIP catalog (needs Gold Membership, SD-JWT)
```

In chat: *"What does Demo Merch sell and at what prices? https://kya.demo.air3.com"*, then after
`hermes air login`: *"Check Demo Merch's catalog again."*

## Commands

### Terminal: `hermes air …`

| Command | What it does |
|---|---|
| `hermes air login [--name <label>]` | Delegate your AIR identity to this agent. Prints an AIR Console URL + code; approve it there. Generates the P-256 agent key and stores key + bundle (0600). Default label: `Hermes (AIR Agent KYA)` |
| `hermes air whoami` | Show the stored delegation: `delegated`, `userId`, `partnerId`, Console URL |
| `hermes air logout` | Delete the local agent key and bundle. Also revoke the key in the AIR Console |
| `hermes air visit <siteUrl>` | Enter a KYA store and print the 4-step trace (discover → challenge → AIR → catalog) and its catalog |
| `hermes air visit <siteUrl> --mock <profile>` | Same, against a local mock-mode site using `npm run mock-air` |
| `hermes air visit <siteUrl> --json` | Print only the catalog JSON |
| `hermes air --help` | List commands |

Mock profiles: `good` (eligible), `low-tier`, `wrong-class`, `expired`, `bad-signature`,
`untrusted-issuer`, `wrong-vct`, `missing-disclosure`, `overshare`, `unbound`, `no-credential`.

### In chat

| Command | What it does |
|---|---|
| `/air whoami` | Delegation status (same as `hermes air whoami`) |

Login is deliberately terminal-only, so the model can never delegate itself.

### Agent tools (the model calls these)

| Tool | Args | What it does |
|---|---|---|
| `kya_visit` | `site`, optional `mock_profile` | Full KYA handshake; returns `viewer`, `reason`, `verification`, disclosed claim names and the catalog. Never returns the credential. Live sites trigger an approval prompt before AIR discloses |
| `air_whoami` | — | Read-only delegation status |

The bundled skill `air-agent-kya:air-agent-kya` tells the model when to use them and how to read
the outcomes.

### Plugin management

| Command | What it does |
|---|---|
| `hermes plugins validate <path> --install-deps` | Check the manifest, load the plugin, install deps (same check catalog CI runs) |
| `hermes plugins doctor <path> --ci` | Health check |
| `hermes plugins enable air-agent-kya` / `disable air-agent-kya` | Turn the plugin on / off |
| `hermes plugins update air-agent-kya` | Update; your delegation in plugin-data survives |

## Outcomes

| Result | Meaning |
|---|---|
| `viewer: eligible` | Verified agent → VIP catalog |
| `verification: not_delegated` | No delegation; agent sent an empty proof → public catalog |
| `verification: NotFound` | The delegated AIR account has no credential matching the site's program |
| `verification: Non-Compliant` / `reason: condition_not_met:*` | Credential found, rule not met (e.g. Silver tier) |
| `code: policy_not_configured` | Site's AIR policy incomplete (`missing` lists what) |
| `MOCK_REQUIRED` / `MOCK_REJECTED` | Site mode and `--mock` don't match |
| `agent/session 401/403` | Key revoked or replaced → `hermes air login` again |
| `retryable: true` | AIR storage outage (`CREDENTIAL_STORAGE_UNAVAILABLE`); retry later |

## Settings

All optional; set them in Hermes Desktop → Plugins → AIR Agent KYA, or under
`plugins.entries.air-agent-kya.settings` in Hermes config. Empty endpoint settings use the AIR
sandbox (same defaults as `agent/air.ts`); the delegation bundle's `partnerId` wins over `partner_id`.

| Setting | Default |
|---|---|
| `require_approval` | `true`: ask before a live `kya_visit` discloses claims |
| `partner_id` | AIR AI Studio sandbox partner `8ab60850-bdfa-4e48-8afa-d67a3d715224` |
| `console_url` | `https://sandbox.agents.air3.com` |
| `api_url` | `https://air.api.sandbox.air3.com/v2` |
| `credential_api_url` | `https://credential-testnet.api.sandbox.air3.com` |
| `agent_dir` | This profile's `plugin-data/air-agent-kya/` |
| `mock_air_url` | `http://127.0.0.1:8799` (mock-mode sites only) |

## Disclosures

What this plugin does that you may want to know before installing:

- **Network calls:** the AIR Console (`sandbox.agents.air3.com`, during `hermes air login` only), the
  AIR API (`air.api.sandbox.air3.com`) and AIR credential API
  (`credential-testnet.api.sandbox.air3.com`), and each KYA site the agent visits
  (`/.well-known/air-kya`, `/kya/challenge`, `/catalog`). https only; plain http only for localhost.
- **Stored credentials:** a P-256 agent private key and the AIR delegation bundle, in the plugin's own
  plugin-data directory, mode 0600. `hermes air logout` deletes them; revoke the key in the AIR
  Console too.
- **What leaves AIR:** only the SD-JWT claims a site requests, only after you approve (default), and
  only to the origin that issued the nonce. The model never receives the presentation, key or tokens.
- **Reads outside its own data:** once, the old `air-kya` plugin-data directory, to carry over a
  delegation made before the rename.
- **Does not:** run shell commands or subprocesses, start background processes, read `.env` or other
  credential stores, sign transactions, or send telemetry.

## Protocol parity with mocaverse/air-kya

| Step | Repo (`npm run agent`) | Plugin |
|---|---|---|
| Delegate | `login` (AIR Console device code, `air-agent-broker`, `openid credentials.read credentials.verify`) | `hermes air login` |
| Session proof | `${pubPem}:${userId}:${ts}`, DER ECDSA b64, strictly increasing ts | same |
| Partner | bundle → configured partner → AI Studio sandbox | same |
| Scope | verify-only, fall back to read+verify | same |
| Presentation | `vp_token[programId][0]` or `verifiableCredential[0](.id)` | same |
| Site | `/.well-known/air-kya`, `POST /kya/challenge`, `GET /catalog` + `X-AIR-KYA` (empty when none) | same |

## Layout

```
air-agent-hermes/
├── plugin.yaml               manifest: tools, hook, deps, settings, requires_hermes
├── __init__.py               register(ctx)
├── schemas.py                tool schemas (model-facing)
├── tools.py                  handlers, approval hook, `hermes air` CLI, `/air`
├── air.py                    AIR client: device-code login, P-256 key, session, verify-by-agent
├── kya.py                    site visit: discovery → challenge → AIR → catalog
├── skills/air-agent-kya/     when/how the model uses it
├── tests/                    test_flow.py (offline), e2e_local.py (real Worker + mock AIR)
├── docs/                     catalog entry draft + catalog PR text
└── .github/workflows/ci.yml  unit + e2e
```

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q              # offline, all AIR and site calls mocked

# e2e: in mocaverse/air-kya run `npm run dev` and `npm run mock-air`, then
python3 tests/e2e_local.py             # all 11 mock profiles against the real Worker
```

## Releasing

1. Bump `version` in `plugin.yaml`, add a `CHANGELOG.md` entry, merge to `main` with CI green.
2. Direct installs (`hermes plugins install mocaverse/air-agent-hermes`) pick it up on
   `hermes plugins update air-agent-kya`.
3. Hermes catalog: open a PR to `NousResearch/hermes-agent` bumping `sha` (full 40-char commit) and
   `version` in `plugin-catalog/air-agent-kya.yaml`. First listing: see `docs/catalog-entry.yaml`
   and `docs/catalog-pr.md`.

## License

MIT — see [LICENSE](LICENSE).
