"""AIR Agent KYA: AIR client, ported from mocaverse/air-kya agent/air.ts.

  - delegation: AIR Console device-code grant binds a local P-256 key to the user's AIR account
  - session:    POST {airApi}/auth/agent/session, signed `${pubPem}:${userId}:${ts}`
  - verify:     POST {credentialApi}/v2/credentials/verify-by-agent
"""

from __future__ import annotations

import base64
import json
import os
import re
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

# Same defaults as agent/air.ts SANDBOX. AIR AI Studio's sandbox partner; the bundle's partnerId wins.
SANDBOX = {
    "console_url": "https://sandbox.agents.air3.com",
    "air_api_url": "https://air.api.sandbox.air3.com/v2",
    "credential_api_url": "https://credential-testnet.api.sandbox.air3.com",
    "partner_id": "8ab60850-bdfa-4e48-8afa-d67a3d715224",
}
MOCK_AIR_URL = "http://127.0.0.1:8799"  # `npm run mock-air`

# What the user grants: read + verify their credentials. No wallet signing, no checkout.
BIND_SCOPES = ["openid", "credentials.read", "credentials.verify"]
# Narrowest session handed to a merchant: verify only, so the site cannot list the user's credentials.
MERCHANT_SESSION_SCOPE = "openid credentials.verify"
FULL_SESSION_SCOPE = "openid credentials.read credentials.verify"
CLIENT_ID = "air-agent-broker"
USER_AGENT = "air-agent-kya-hermes/0.1"

KEY_FILE = "agent-key.pem"
BUNDLE_FILE = "bundle.json"


class AirError(Exception):
    def __init__(self, message: str, *, code: str = "", status: int = 0, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.status = status
        self.retryable = retryable


@dataclass
class AirEnv:
    console_url: str
    air_api_url: str
    credential_api_url: str
    partner_id: str


def air_env(overrides: dict | None = None) -> AirEnv:
    """Sandbox defaults, overridden by non-empty plugin settings (console_url, api_url, ...)."""
    o = {k: v for k, v in (overrides or {}).items() if isinstance(v, str) and v.strip()}
    return AirEnv(
        console_url=o.get("console_url") or SANDBOX["console_url"],
        air_api_url=o.get("api_url") or SANDBOX["air_api_url"],
        credential_api_url=o.get("credential_api_url") or SANDBOX["credential_api_url"],
        partner_id=o.get("partner_id") or SANDBOX["partner_id"],
    )


# --------------------------------------------------------------------------- storage


PLUGIN_ID = "air-agent-kya"
LEGACY_ID = "air-kya"  # plugin name before the AIR Agent KYA rename; its delegation is carried over once


def agent_dir(override: str | Path | None = None) -> Path:
    """The `agent_dir` setting, else this profile's Hermes plugin-data dir (survives plugin updates)."""
    if override:
        path = Path(override).expanduser()
    else:
        try:
            from plugins.plugin_storage import plugin_data_dir  # Hermes runtime

            path = Path(plugin_data_dir(PLUGIN_ID))
        except Exception:
            path = Path.home() / ".hermes" / "plugin-data" / PLUGIN_ID
        _migrate_legacy(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def _migrate_legacy(path: Path) -> None:
    """Copy a delegation made under the old `air-kya` name, so renaming needs no new login."""
    legacy = path.parent / LEGACY_ID
    if (path / BUNDLE_FILE).exists() or not ((legacy / BUNDLE_FILE).exists() and (legacy / KEY_FILE).exists()):
        return
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in (KEY_FILE, BUNDLE_FILE):
        _write_private(path / name, (legacy / name).read_bytes())


def _write_private(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def public_pem(key: ec.EllipticCurvePrivateKey) -> str:
    """SPKI PEM, trimmed: the exact string registered with the Console and signed in the session proof."""
    return key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode().strip()


def pem_body(pem: str) -> str:
    return re.sub(r"-----[^-]+-----|\s", "", pem)


@dataclass
class Delegation:
    bundle: dict
    key: ec.EllipticCurvePrivateKey
    public_key_pem: str = field(init=False)

    def __post_init__(self):
        self.public_key_pem = public_pem(self.key)

    @property
    def user_id(self) -> str:
        return self.bundle["userId"]

    def partner_id(self, env: AirEnv) -> str:
        return self.bundle.get("partnerId") or env.partner_id


def load_delegation(directory: Path | None = None) -> Delegation | None:
    directory = directory or agent_dir()
    try:
        bundle = json.loads((directory / BUNDLE_FILE).read_text())
        key = serialization.load_pem_private_key((directory / KEY_FILE).read_bytes(), password=None)
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
        return None
    if not bundle.get("userId"):
        return None
    return Delegation(bundle=bundle, key=key)


def logout(directory: Path | None = None) -> None:
    directory = directory or agent_dir()
    for name in (KEY_FILE, BUNDLE_FILE):
        p = directory / name
        if p.exists():
            p.unlink()


# --------------------------------------------------------------------------- http


def _post(http: httpx.Client, url: str, body: dict, headers: dict | None = None, form: bool = False):
    h = {"accept": "application/json", "user-agent": USER_AGENT, **(headers or {})}
    resp = http.post(url, data=body, headers=h) if form else http.post(url, json=body, headers=h)
    try:
        data = resp.json()
    except Exception:
        data = None
    return resp, data


# --------------------------------------------------------------------------- step 1: delegation


def login(env: AirEnv, agent_name: str, show: Callable[[str], None], *, http: httpx.Client | None = None,
          directory: Path | None = None, sleep: Callable[[float], None] = time.sleep) -> dict:
    """The user delegates identity to this agent via AIR Console (RFC 8628 device code)."""
    directory = directory or agent_dir()
    http = http or httpx.Client(timeout=15.0)
    key = ec.generate_private_key(ec.SECP256R1())
    pub = public_pem(key)

    resp, start = _post(http, f"{env.console_url}/api/oauth/device/code", {
        "client_id": CLIENT_ID, "scope": " ".join(BIND_SCOPES),
        "agent_public_key": pub, "agent_name": agent_name,
    }, form=True)
    if resp.status_code >= 400 or not (start or {}).get("device_code"):
        raise AirError(f"device/code {resp.status_code}: {resp.text[:300]}", status=resp.status_code)

    show("Approve this agent with your AIR (sandbox) account:")
    show(f"  Open: {start.get('verification_uri_complete') or start['verification_uri']}")
    show(f"  Code: {start['user_code']}   (expires in {round(start['expires_in'] / 60)} min)")
    show(f"  Grants: {', '.join(BIND_SCOPES)}  (no wallet signing)")

    interval = float(start.get("interval") or 5)
    deadline = time.time() + float(start["expires_in"])
    while time.time() < deadline:
        sleep(interval)
        resp, tok = _post(http, f"{env.console_url}/api/oauth/token", {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": start["device_code"], "client_id": CLIENT_ID,
        }, form=True)
        if resp.status_code < 400 and (tok or {}).get("userId"):
            if pem_body(tok.get("agentPublicKey", "")) != pem_body(pub):
                raise AirError("Console returned a different agent public key; refusing to store it.")
            pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption())
            _write_private(directory / KEY_FILE, pem)
            _write_private(directory / BUNDLE_FILE, json.dumps(tok, indent=2).encode())
            return tok
        error = (tok or {}).get("error")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue
        raise AirError(f"token poll {resp.status_code}: {error or resp.text[:200]}", status=resp.status_code)
    raise AirError("Device code expired before approval.")


# --------------------------------------------------------------------------- step 2: proof

# AIR rejects a reused `pubkey:userId:timestamp`, so keep timestamps strictly increasing.
_last_ts = 0


def signed_message(d: Delegation, now: float | None = None) -> dict:
    global _last_ts
    ts = max(int(now if now is not None else time.time()), _last_ts + 1)
    _last_ts = ts
    message = f"{d.public_key_pem}:{d.user_id}:{ts}"
    # DER-encoded ECDSA P-256 / SHA-256, base64 — what AIR's verifier expects.
    signature = base64.b64encode(d.key.sign(message.encode(), ec.ECDSA(hashes.SHA256()))).decode()
    return {"message": message, "signature": signature, "publicKey": d.public_key_pem}


def agent_session(env: AirEnv, d: Delegation, scope: str, *, http: httpx.Client) -> str:
    """Exchange the delegated key for a short-lived (15 min) agent JWT."""
    resp, data = _post(http, f"{env.air_api_url}/auth/agent/session",
                       {"signedMessage": signed_message(d), "scope": scope},
                       {"x-partner-id": d.partner_id(env)})
    data = data or {}
    token = data.get("accessToken") or (data.get("data") or {}).get("accessToken")
    if resp.status_code >= 400 or not isinstance(token, str):
        html = resp.text.lstrip().lower().startswith("<")
        hint = " — re-run `hermes air login` if this key was revoked or replaced." if resp.status_code in (401, 403) else ""
        detail = "blocked by AIR's CDN (HTML error page)" if html else resp.text[:300]
        raise AirError(f"agent/session {resp.status_code}: {detail}{hint}",
                       code=(data.get("code") or ""), status=resp.status_code)
    return token


def session(env: AirEnv, d: Delegation, *, http: httpx.Client, log: Callable[[str], None] = lambda _: None) -> str:
    """Narrowest session first; fall back if AIR only accepts the full bound scope."""
    try:
        return agent_session(env, d, MERCHANT_SESSION_SCOPE, http=http)
    except AirError as exc:
        log(f"verify-only session refused, using read+verify scope: {str(exc)[:80]}")
        return agent_session(env, d, FULL_SESSION_SCOPE, http=http)


def normalize_verify(raw: object, program_id: str) -> dict:
    """Status + SD-JWT presentation from every response shape agent/air.ts handles."""
    r = raw if isinstance(raw, dict) else {}
    body = r if ("verificationResult" in r or "vp_token" in r) else (r.get("data") or r)
    result = body.get("verificationResult") or {}
    if isinstance(result.get("status"), str):
        status = result["status"]
    elif body.get("verified") is True:
        status = "Compliant"
    else:
        status = str(body.get("reason") or body.get("status") or "unknown")
    vp_token = body.get("vp_token") or {}
    from_vp_token = (vp_token.get(program_id) or [None])[0]
    if from_vp_token is None:
        flat = [v for vals in vp_token.values() for v in (vals or [])]
        from_vp_token = flat[0] if flat else None
    from_vp = ((result.get("verifiablePresentation") or {}).get("verifiableCredential") or [None])[0]
    if isinstance(from_vp, dict):
        from_vp = from_vp.get("id")
    sd_jwt = next((v for v in (from_vp_token, from_vp) if isinstance(v, str)), None)
    return {"status": status, "sdJwt": sd_jwt}


def verify_by_agent(credential_api_url: str, access_token: str, *, program_id: str,
                    fields_to_disclose: list[str] | None, nonce: str | None, http: httpx.Client) -> dict:
    """Ask AIR to verify the user's credential against the site's program (holder-bound to its nonce)."""
    body: dict = {"programId": program_id}
    if fields_to_disclose:
        body["fieldsToDisclose"] = fields_to_disclose
    if nonce:
        body["nonce"] = nonce
    resp, data = _post(http, f"{credential_api_url}/v2/credentials/verify-by-agent", body,
                       {"authorization": f"Bearer {access_token}"})
    if resp.status_code >= 400:
        code = (data or {}).get("code") or (data or {}).get("error") or ""
        raise AirError(f"verify-by-agent {resp.status_code}: {resp.text[:300]}", code=code,
                       status=resp.status_code,
                       retryable=resp.status_code in (502, 503, 504) or code == "CREDENTIAL_STORAGE_UNAVAILABLE")
    return normalize_verify(data, program_id)


def disclosed_names(value: str) -> list[str]:
    """Claim names in the presentation's disclosures, for display only (the site verifies)."""
    compact = re.sub(r"^data:application/(dc|vc)\+sd-jwt,", "", value)
    names = []
    for d in compact.split("~")[1:-1]:
        try:
            parsed = json.loads(base64.urlsafe_b64decode(d + "=" * (-len(d) % 4)))
            if isinstance(parsed, list) and len(parsed) > 1 and isinstance(parsed[1], str):
                names.append(parsed[1])
        except Exception:
            pass
    return names
