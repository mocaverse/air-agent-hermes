# air-kya — native Hermes plugin

Port of the agent in [mocaverse/air-kya](https://github.com/mocaverse/air-kya) (`agent/air.ts`,
`agent/cli.ts`) to a native Hermes plugin. Same protocol, same endpoints, same headers; the
Worker, mock issuer and policies stay in that repo.

## Commands

### Terminal: `hermes air …`

| Command | What it does |
|---|---|
| `hermes air login [--name <label>]` | Delegate your AIR identity to this agent. Prints an AIR Console URL + code; approve it there. Generates the P-256 agent key and stores key + bundle (0600). Default label: `Hermes (air-kya)` |
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
| `kya_visit` | `site`, optional `mock_profile` | Full KYA handshake, returns `viewer`, `reason`, `verification`, disclosed claim names and the catalog. Never returns the credential. Live sites trigger an approval prompt before AIR discloses |
| `air_whoami` | — | Read-only delegation status |

Example prompts: *"What does Demo Merch sell and at what prices? https://air-kya-demo-merch.0xmythril.workers.dev"*,
*"Check Demo Merch's catalog again."*

### Plugin management

| Command | What it does |
|---|---|
| `hermes plugins validate ~/.hermes/plugins/air-kya --install-deps` | Check the manifest, load the plugin, install deps (same check catalog CI runs) |
| `hermes plugins doctor ~/.hermes/plugins/air-kya --ci` | Health check |
| `hermes plugins enable air-kya` / `disable air-kya` | Turn the plugin on / off |
| `hermes plugins update air-kya` | Update (delegation in plugin-data survives) |

## Install

```bash
mkdir -p ~/.hermes/plugins
unzip -o air-kya.zip -d ~/.hermes/plugins/        # or: cp -r air-kya ~/.hermes/plugins/
hermes plugins validate ~/.hermes/plugins/air-kya --install-deps
hermes plugins enable air-kya
hermes air --help
```

## Quick start

```bash
# live sandbox (AIR account holding Gold Membership, SD-JWT)
hermes air visit https://air-kya-demo-merch.0xmythril.workers.dev   # not delegated → Standard catalog
hermes air login                                                    # approve in the AIR Console
hermes air visit https://air-kya-demo-merch.0xmythril.workers.dev   # → VIP catalog

# local mock (in mocaverse/air-kya: npm run dev + npm run mock-air)
hermes air visit http://127.0.0.1:8787 --mock good        # eligible → VIP
hermes air visit http://127.0.0.1:8787 --mock low-tier    # ineligible → Standard
```

## Outcomes

| Result | Meaning |
|---|---|
| `viewer: eligible` | Verified agent → VIP catalog |
| `verification: not_delegated` | No delegation; agent sent an empty proof → Standard catalog |
| `verification: NotFound` | The delegated AIR account has no credential matching the site's program |
| `verification: Non-Compliant` / `reason: condition_not_met:*` | Credential found, rule not met (e.g. Silver tier) |
| `code: policy_not_configured` | Site's AIR policy incomplete (`missing` lists what) |
| `MOCK_REQUIRED` / `MOCK_REJECTED` | Site mode and `--mock` don't match |
| `agent/session 401/403` | Key revoked or replaced → `hermes air login` again |
| `retryable: true` | AIR storage outage (`CREDENTIAL_STORAGE_UNAVAILABLE`); retry later |

## Configuration

All optional. Defaults match `agent/air.ts` (sandbox); the delegation bundle's `partnerId` wins.

| Env var | Default |
|---|---|
| `AIR_PARTNER_ID` | AIR AI Studio sandbox partner `8ab60850-bdfa-4e48-8afa-d67a3d715224` |
| `AIR_CONSOLE_URL` | `https://sandbox.agents.air3.com` |
| `AIR_API_URL` | `https://air.api.sandbox.air3.com/v2` |
| `AIR_CREDENTIAL_API_URL` | `https://credential-testnet.api.sandbox.air3.com` |
| `AIR_KYA_AGENT_DIR` | This profile's `plugin-data/air-kya/` |

Plugin settings: `require_approval` (default `true`; ask before live disclosure),
`mock_air_url` (default `http://127.0.0.1:8799`).

## Protocol parity with the repo

| Step | Repo (`npm run agent`) | Plugin |
|---|---|---|
| Delegate | `login` (AIR Console device code, `air-agent-broker`, `openid credentials.read credentials.verify`) | `hermes air login` |
| Session proof | `${pubPem}:${userId}:${ts}`, DER ECDSA b64, strictly increasing ts | same |
| Partner | bundle → `AIR_PARTNER_ID` → AI Studio sandbox | same |
| Scope | verify-only, fall back to read+verify | same |
| Presentation | `vp_token[programId][0]` or `verifiableCredential[0](.id)` | same |
| Site | `/.well-known/air-kya`, `POST /kya/challenge`, `GET /catalog` + `X-AIR-KYA` (empty when none) | same |

Hermes-specific: live `kya_visit` goes through Hermes' approval gate; the model never sees the
presentation, key or tokens; an agent that isn't delegated still gets the no-proof catalog.

## Layout

```
air-kya/
├── plugin.yaml          manifest: tools, hook, deps, settings
├── __init__.py          register(ctx)
├── schemas.py           tool schemas (model-facing)
├── tools.py             handlers, approval hook, `hermes air` CLI, `/air`
├── air.py               AIR client: device-code login, P-256 key, session, verify-by-agent
├── kya.py               site visit: discovery → challenge → AIR → catalog
├── skills/air-kya/      when/how the model uses it
└── tests/               test_flow.py (offline), e2e_local.py (real Worker + mock AIR)
```

## Tests

```bash
python -m pytest air-kya/tests -q          # offline, all AIR and site calls mocked
python3 air-kya/tests/e2e_local.py         # real Worker + mock AIR, all 11 profiles
```
