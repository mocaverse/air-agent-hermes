"""Site visit, ported from mocaverse/air-kya agent/cli.ts `visit`.

  1 GET  {site}/.well-known/air-kya       programId, fieldsToDisclose, environment, configured, issueUrl
  2 POST {site}/kya/challenge             one-time nonce (60 s), bound into the KB-JWT
  3 AIR  verify-by-agent                  holder-bound SD-JWT presentation (or mock AIR for environment=mock)
  4 GET  {site}/catalog  X-AIR-KYA: <presentation or "">   → X-AIR-Viewer / X-AIR-Reason / X-AIR-Disclosed

The presentation only goes to the origin that issued the nonce, and is never returned to the model.
"""

from __future__ import annotations

from typing import Callable
from urllib.parse import urlsplit

import httpx

from . import air

MOCK_PROFILES = ["good", "low-tier", "wrong-class", "expired", "bad-signature", "untrusted-issuer",
                 "wrong-vct", "missing-disclosure", "overshare", "unbound", "no-credential"]


class VisitError(Exception):
    def __init__(self, message: str, **extra):
        super().__init__(message)
        self.extra = extra


def site_base(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme not in ("https", "http") or not parts.netloc or parts.username or parts.password:
        raise VisitError(f"Not a usable site URL: {url!r}")
    if parts.scheme == "http" and parts.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise VisitError("Plain HTTP is allowed only for localhost.")
    return f"{parts.scheme}://{parts.netloc}"


def visit(site: str, *, http: httpx.Client, mock: str | None = None, env: air.AirEnv | None = None,
          delegation: air.Delegation | None = None, mock_air_url: str = air.MOCK_AIR_URL,
          log: Callable[[str], None] = lambda _: None) -> dict:
    base = site_base(site)
    env = env or air.air_env()
    if mock and mock not in MOCK_PROFILES:
        raise VisitError(f"mock must be one of {', '.join(MOCK_PROFILES)}")

    disc_resp = http.get(f"{base}/.well-known/air-kya", headers={"accept": "application/json"})
    if disc_resp.status_code == 404:
        raise VisitError("Site publishes no /.well-known/air-kya; it is not AIR KYA gated.", code="NOT_KYA_SITE")
    disc_resp.raise_for_status()
    disc = disc_resp.json()
    program_id = disc.get("programId") or ""
    fields = disc.get("fieldsToDisclose") or []
    log(f"1 discover   {disc.get('environment')} programId={program_id or '(unset)'} fields={','.join(fields)}")
    if disc.get("configured") is False:
        raise VisitError(f"The site's AIR policy is not configured yet (missing {', '.join(disc.get('missing') or [])}).",
                         code="policy_not_configured", missing=disc.get("missing"))
    if disc.get("environment") == "mock" and not mock:
        raise VisitError("This site trusts only the local mock issuer; pass a mock profile.", code="MOCK_REQUIRED")
    if disc.get("environment") != "mock" and mock:
        raise VisitError("This site trusts a live AIR issuer; mock presentations would be rejected.", code="MOCK_REJECTED")

    ch = http.post(f"{base}/kya/challenge", headers={"accept": "application/json"})
    ch.raise_for_status()
    nonce = ch.json().get("nonce")
    if not nonce:
        raise VisitError("Site returned no nonce.")
    log(f"2 challenge  nonce={nonce[:8]}…")

    if mock:
        outcome = air.verify_by_agent(mock_air_url, f"mock-agent:{mock}", program_id=program_id,
                                      fields_to_disclose=fields, nonce=nonce, http=http)
        log(f"3 AIR (mock) verify-by-agent → {outcome['status']}")
    elif delegation is None:
        # Not delegated: nothing to present. Still enter as an agent and get the no-proof catalog.
        outcome = {"status": "not_delegated", "sdJwt": None}
        log("3 AIR        skipped: no delegation (run `hermes air login` for the verified catalog)")
    else:
        token = air.session(env, delegation, http=http, log=lambda m: log(f"             ({m})"))
        outcome = air.verify_by_agent(env.credential_api_url, token, program_id=program_id,
                                      fields_to_disclose=fields, nonce=nonce, http=http)
        log(f"3 AIR        verify-by-agent → {outcome['status']}"
            + (" + holder-bound SD-JWT presentation" if outcome["sdJwt"] else ""))

    result: dict = {
        "site": base,
        "environment": disc.get("environment"),
        "program_id": program_id,
        "requested_fields": fields,
        "verification": outcome["status"],
        "presented": bool(outcome["sdJwt"]),
    }
    if outcome["sdJwt"]:
        result["disclosed"] = air.disclosed_names(outcome["sdJwt"])
        log(f"             discloses {', '.join(result['disclosed']) or 'nothing'}; nothing else leaves AIR")
    elif outcome["status"] == "not_delegated":
        result["note"] = ("Agent is not delegated, so it saw the catalog for unverified visitors. The user can run "
                          "`hermes air login` in a terminal and approve in the AIR Console to unlock the verified catalog.")
    else:
        if outcome["status"] == "Compliant":
            result["note"] = "AIR said Compliant but returned no SD-JWT presentation; the site cannot act on a bare status."
        if disc.get("issueUrl"):
            result["issue_url"] = disc["issueUrl"]
            log(f"             no credential to present; the user can claim it at {disc['issueUrl']}")

    # No presentation still identifies us as an agent, with nothing to show.
    res = http.get(f"{base}/catalog", headers={"X-AIR-KYA": outcome["sdJwt"] or "", "accept": "application/json"})
    result["http_status"] = res.status_code
    result["viewer"] = res.headers.get("X-AIR-Viewer")
    result["reason"] = res.headers.get("X-AIR-Reason")
    result["site_disclosed"] = res.headers.get("X-AIR-Disclosed")
    log(f"4 catalog    viewer={result['viewer']} reason={result['reason']}")
    try:
        result["catalog"] = res.json()
    except Exception:
        result["catalog"] = res.text[:5000]
    return result
