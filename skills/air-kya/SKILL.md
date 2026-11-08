---
name: air-kya
description: Use when a task needs an AIR KYA (Know-Your-Agent) gated store — one that publishes /.well-known/air-kya, like Demo Merch — to show the user's agent its agent catalog. Covers kya_visit, reading the viewer and reason, and what never to do with credentials.
---

# AIR KYA

The user can delegate their AIR identity (Moca Network) to this agent. KYA stores serve three
catalogs from one URL: **human** (no `X-AIR-KYA` header), **ineligible** (agent, proof missing or
failing), **eligible** (agent with a passing SD-JWT presentation). Only the claims the site asks
for leave AIR (Demo Merch live asks only for `tier`).

## Tools

- `air_whoami`: read-only. Delegated or not, AIR user id, partner, Console.
- `kya_visit(site, mock_profile?)`: discovery → `/kya/challenge` nonce → AIR verify-by-agent →
  `GET /catalog` with `X-AIR-KYA`. Returns `viewer`, `reason`, `verification`, `disclosed` claim
  names, `issue_url` when there is nothing to present, and `catalog`. Never the credential.
  - Live sites: omit `mock_profile`. The user is asked to approve the disclosure.
  - Local mock site (`environment: mock`): pass a profile (`good` → eligible; others are the
    rejection cases: `low-tier`, `expired`, `overshare`, `no-credential`, …).

## Reading the result

| Result | Meaning | Do |
|---|---|---|
| `viewer: eligible` | Verified; agent catalog | Continue the task with it |
| `verification: NotFound` | User holds no credential this site accepts | Tell the user; give `issue_url` if present. Verification never issues one |
| `verification: Non-Compliant` or `reason: condition_not_met:*` | Credential found, rule not met (e.g. Silver) | Work with the limited catalog; say which condition |
| other `reason` (`expired`, `untrusted_issuer`, `disclosure_mismatch`, `nonce_*`, …) | Site rejected the proof | Report the reason code; do not retry blindly |
| `code: policy_not_configured` | Site setup incomplete (`missing` lists what) | Report it; nothing to fix agent-side |
| `code: NOT_DELEGATED` | No delegation | Ask the user to run `hermes air login` in a terminal and approve in the AIR Console |
| `agent/session 401/403` | Key revoked or replaced | Same: `hermes air login` again |
| `retryable: true` (`CREDENTIAL_STORAGE_UNAVAILABLE`) | AIR storage outage | Retry once later; not the same as ineligible |
| `MOCK_REQUIRED` / `MOCK_REJECTED` | Mode mismatch | Add or drop `mock_profile` |

## Rules

- Never ask for, print or store the presentation, the agent key, the bundle or AIR tokens.
- Never run `hermes air login` yourself; delegation needs the user in the AIR Console.
- A refused approval means no. Do not retry it.
- Eligibility is not payment authority. Ordering and paying follow the store's own flow and the
  user's explicit go-ahead.
