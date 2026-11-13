"""AIR Agent KYA: site visit, ported from mocaverse/air-kya agent/cli.ts `visit`.

  1 GET  {site}/.well-known/air-kya       programId, fieldsToDisclose, environment, configured, issueUrl
  2 POST {site}/kya/challenge             one-time nonce (60 s), bound into the KB-JWT
  3 AIR  verify-by-agent                  holder-bound SD-JWT presentation (or mock AIR for environment=mock)
  4 GET  {site}/catalog  X-AIR-KYA: <presentation or "">   → X-AIR-Viewer / X-AIR-Reason / X-AIR-Disclosed

The presentation only goes to the origin that issued the nonce, and is never returned to the model.

The model chooses `site`, so site requests go through `site_client()`: every connection is resolved, refused unless
each address is public (loopback too in mock mode or with `allow_local_sites`), and made to the address that was
checked, so DNS rebinding can't reach a private service between the check and the connect.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Callable
from urllib.parse import urlsplit

import httpcore
import httpx

from . import air

MOCK_PROFILES = ["good", "low-tier", "wrong-class", "expired", "bad-signature", "untrusted-issuer",
                 "wrong-vct", "missing-disclosure", "overshare", "unbound", "no-credential"]


class VisitError(Exception):
    def __init__(self, message: str, **extra):
        super().__init__(message)
        self.extra = extra


LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
LOCAL_HINT = "Local sites are allowed only in mock mode or with the allow_local_sites setting."

Resolver = Callable[[str, int], list[str]]


def system_resolve(host: str, port: int) -> list[str]:
    return sorted({info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})


def address_allowed(address: str, *, allow_local: bool = False) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])  # drop an IPv6 zone id
    if allow_local and ip.is_loopback:
        return True
    return ip.is_global and not ip.is_multicast


def checked_addresses(host: str, port: int, *, allow_local: bool = False,
                      resolve: Resolver = system_resolve) -> list[str]:
    """All addresses `host` resolves to, or VisitError unless every one may be contacted."""
    try:
        addresses = resolve(host, port)
    except OSError as exc:
        raise VisitError(f"Cannot resolve {host}: {exc}", code="SITE_UNRESOLVABLE") from None
    if not addresses:
        raise VisitError(f"Cannot resolve {host}.", code="SITE_UNRESOLVABLE")
    for a in addresses:
        if not address_allowed(a, allow_local=allow_local):
            raise VisitError(f"{host} resolves to a non-public address ({a}); refusing to contact it."
                             + ("" if allow_local else f" {LOCAL_HINT}"), code="SITE_NOT_PUBLIC")
    return addresses


class PublicOnlyBackend(httpcore.NetworkBackend):
    """Resolves, checks, then connects to the checked IP (TLS still verifies the hostname via SNI)."""

    def __init__(self, *, allow_local: bool = False, resolve: Resolver = system_resolve,
                 inner: httpcore.NetworkBackend | None = None):
        self.allow_local = allow_local
        self.resolve = resolve
        self.inner = inner or httpcore.SyncBackend()

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        last: Exception | None = None
        for address in checked_addresses(host, port, allow_local=self.allow_local, resolve=self.resolve):
            try:
                return self.inner.connect_tcp(address, port, timeout=timeout, local_address=local_address,
                                              socket_options=socket_options)
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last = exc
        raise last  # type: ignore[misc]

    def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise httpcore.ConnectError("Unix sockets are not allowed for KYA sites.")

    def sleep(self, seconds: float) -> None:
        self.inner.sleep(seconds)


def site_client(*, allow_local: bool = False, timeout: float = 20.0, resolve: Resolver = system_resolve) -> httpx.Client:
    """Client for model-chosen sites. No env proxies (a proxy would resolve the host itself), no redirects."""
    transport = httpx.HTTPTransport(trust_env=False)
    pool = transport._pool
    if not isinstance(pool, httpcore.ConnectionPool) or not hasattr(pool, "_network_backend"):
        raise RuntimeError("Unsupported httpx/httpcore version: cannot pin site connections to checked addresses.")
    pool._network_backend = PublicOnlyBackend(allow_local=allow_local, resolve=resolve)
    return httpx.Client(transport=transport, timeout=timeout, follow_redirects=False, trust_env=False)


def site_base(url: str, *, allow_local: bool = False) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme not in ("https", "http") or not parts.netloc or parts.username or parts.password:
        raise VisitError(f"Not a usable site URL: {url!r}")
    try:
        host, port = parts.hostname, parts.port
    except ValueError:
        raise VisitError(f"Not a usable site URL: {url!r}") from None
    if not host:
        raise VisitError(f"Not a usable site URL: {url!r}")
    if parts.scheme == "http" and not (allow_local and host in LOCAL_HOSTS):
        raise VisitError(LOCAL_HINT if host in LOCAL_HOSTS else "Plain HTTP is allowed only for localhost. " + LOCAL_HINT,
                         code="SITE_NOT_PUBLIC")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not address_allowed(str(literal), allow_local=allow_local):
        raise VisitError(f"{host} is not a public address; refusing to contact it."
                         + ("" if allow_local else f" {LOCAL_HINT}"), code="SITE_NOT_PUBLIC")
    return f"{parts.scheme}://{parts.netloc}"


def visit(site: str, *, http: httpx.Client, site_http: httpx.Client | None = None, mock: str | None = None,
          env: air.AirEnv | None = None, delegation: air.Delegation | None = None,
          mock_air_url: str = air.MOCK_AIR_URL, allow_local: bool = False,
          log: Callable[[str], None] = lambda _: None) -> dict:
    """`http` talks to AIR; `site_http` (default: `http`) to the site and should come from `site_client()`."""
    if mock and mock not in MOCK_PROFILES:
        raise VisitError(f"mock must be one of {', '.join(MOCK_PROFILES)}")
    base = site_base(site, allow_local=allow_local or bool(mock))
    site_http = site_http or http
    env = env or air.air_env()

    disc_resp = site_http.get(f"{base}/.well-known/air-kya", headers={"accept": "application/json"})
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

    ch = site_http.post(f"{base}/kya/challenge", headers={"accept": "application/json"})
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
    res = site_http.get(f"{base}/catalog", headers={"X-AIR-KYA": outcome["sdJwt"] or "", "accept": "application/json"})
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
