# air-kya — native Hermes plugin

Port of the agent in [mocaverse/air-kya](https://github.com/mocaverse/air-kya) (`agent/air.ts`,
`agent/cli.ts`) to a native Hermes plugin. Same protocol, same endpoints, same headers; the
Worker, mock issuer and policies stay in that repo.

| Step | Repo (`npm run agent`) | Plugin |
|---|---|---|
| Delegate | `login` (AIR Console device code, `air-agent-broker`, `openid credentials.read credentials.verify`) | `hermes air login` |
| Inspect / revoke | `whoami`, `logout` | `hermes air whoami`, `logout`, `/air whoami`, tool `air_whoami` |
| Visit | `visit <site> [--mock p] [--json]` | `hermes air visit …`, tool `kya_visit` |
| Session proof | `${pubPem}:${userId}:${ts}`, DER ECDSA b64, strictly increasing ts | same |
| Partner | bundle → `AIR_PARTNER_ID` → AI Studio sandbox `8ab60850-…` | same |
| Scope | verify-only, fall back to read+verify | same |
| Presentation | `vp_token[programId][0]` or `verifiableCredential[0](.id)` | same |
| Site | `/.well-known/air-kya`, `POST /kya/challenge`, `GET /catalog` + `X-AIR-KYA` (empty when none) | same |

Hermes-specific: live `kya_visit` goes through Hermes' approval gate before AIR discloses
(`require_approval`, default on); the model never sees the presentation, key or tokens; key and
bundle live in the profile's `plugin-data/air-kya/` (0600), override with `AIR_KYA_AGENT_DIR`.

## Install

```bash
mkdir -p ~/.hermes/plugins && cp -r air-kya ~/.hermes/plugins/
hermes plugins validate ~/.hermes/plugins/air-kya --install-deps
hermes plugins doctor ~/.hermes/plugins/air-kya --ci
hermes plugins enable air-kya
```

## Use

```bash
# mock (in mocaverse/air-kya: npm run dev  +  npm run mock-air)
hermes air visit http://127.0.0.1:8787 --mock good        # eligible, 6 AGT-* SKUs
hermes air visit http://127.0.0.1:8787 --mock low-tier    # ineligible

# live sandbox (needs an AIR sandbox account holding Gold Membership, SD-JWT)
hermes air login                                          # approve at sandbox.agents.air3.com
hermes air visit https://air-kya-demo-merch.0xmythril.workers.dev
```

In chat: "visit Demo Merch as my agent and list the procurement SKUs".

## Tests

```bash
python -m pytest air-kya/tests -q          # offline, all AIR and site calls mocked
python3 air-kya/tests/e2e_local.py         # real Worker + mock AIR, all 11 profiles
```
