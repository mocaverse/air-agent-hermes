"""AIR Agent KYA: tool handlers, approval hook, `hermes air` CLI and `/air` slash command."""

from __future__ import annotations

import argparse
import json

import httpx

from . import air
from .kya import MOCK_PROFILES, VisitError, visit

DEFAULT_AGENT_LABEL = "Hermes (AIR Agent KYA)"
ENV_SETTINGS = ("partner_id", "console_url", "api_url", "credential_api_url")

_ctx = None


def bind_ctx(ctx) -> None:
    global _ctx
    _ctx = ctx


def setting(key: str, default):
    if _ctx is None:
        return default
    try:
        return _ctx.get_config(key, default=default)
    except Exception:
        return default


def _env() -> air.AirEnv:
    return air.air_env({k: setting(k, "") for k in ENV_SETTINGS})


def _dir():
    return air.agent_dir(setting("agent_dir", "") or None)


def _whoami() -> dict:
    d = air.load_delegation(_dir())
    env = _env()
    if not d:
        return {"delegated": False, "console": env.console_url, "hint": "Run `hermes air login` in a terminal."}
    return {"delegated": True, "userId": d.user_id, "partnerId": d.partner_id(env), "console": env.console_url}


def _run_visit(site: str, mock: str | None, log=lambda _: None) -> dict:
    with httpx.Client(timeout=20.0, follow_redirects=False) as http:
        return visit(site, http=http, mock=mock or None, env=_env(), delegation=air.load_delegation(_dir()),
                     mock_air_url=setting("mock_air_url", air.MOCK_AIR_URL), log=log)


# --------------------------------------------------------------------------- tools


def air_whoami(args: dict, **kwargs) -> str:
    try:
        return json.dumps(_whoami())
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def kya_visit(args: dict, **kwargs) -> str:
    site = (args.get("site") or "").strip()
    if not site:
        return json.dumps({"error": "site is required"})
    try:
        return json.dumps(_run_visit(site, args.get("mock_profile")), default=str)
    except VisitError as exc:
        return json.dumps({"error": str(exc), **exc.extra})
    except air.AirError as exc:
        return json.dumps({"error": str(exc), "code": exc.code, "retryable": exc.retryable})
    except httpx.HTTPError as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
    except Exception as exc:  # never raise into the agent loop
        return json.dumps({"error": f"unexpected: {exc}"})


# --------------------------------------------------------------------------- hook


def pre_tool_call(tool_name: str = "", args: dict | None = None, **kwargs):
    """Escalate live kya_visit to Hermes' human-approval gate before a real credential is disclosed."""
    if tool_name != "kya_visit" or not setting("require_approval", True):
        return None
    args = args or {}
    if args.get("mock_profile") or air.load_delegation(_dir()) is None:
        return None  # mock data, or nothing to disclose
    return {"action": "approve",
            "message": f"Let AIR share the claims {args.get('site', '?')} requests from your credential?"}


# --------------------------------------------------------------------------- CLI: hermes air ...


def cli_setup(subparser) -> None:
    subs = subparser.add_subparsers(dest="air_command")
    p_login = subs.add_parser("login", help="Delegate your AIR identity to this agent (AIR Console device code)")
    p_login.add_argument("--name", default=DEFAULT_AGENT_LABEL)
    subs.add_parser("whoami", help="Show the stored delegation")
    subs.add_parser("logout", help="Delete the local agent key (also revoke it in the AIR Console)")
    p_visit = subs.add_parser("visit", help="Enter a KYA site and print its catalog")
    p_visit.add_argument("site")
    p_visit.add_argument("--mock", choices=MOCK_PROFILES)
    p_visit.add_argument("--json", action="store_true")
    subparser.set_defaults(func=cli_handler)


def cli_handler(args: argparse.Namespace) -> None:
    cmd = getattr(args, "air_command", None)
    try:
        if cmd == "login":
            env = _env()
            directory = _dir()
            bundle = air.login(env, args.name, print, directory=directory)
            print(f"Delegated. userId={bundle['userId']} partnerId={bundle.get('partnerId') or env.partner_id}")
            print(f"Key and bundle stored in {directory} (0600). Revoke anytime in the AIR console.")
        elif cmd == "whoami":
            print(json.dumps(_whoami(), indent=2))
        elif cmd == "logout":
            air.logout(_dir())
            print("Local agent key removed. Also revoke the key in the AIR console.")
        elif cmd == "visit":
            quiet = args.json
            result = _run_visit(args.site, args.mock, log=(lambda _: None) if quiet else print)
            if quiet:
                print(json.dumps(result.get("catalog")))
            else:
                cat = result.get("catalog") or {}
                if cat.get("catalog"):
                    print(f"             catalog: {cat['catalog']}")
                for p in cat.get("products", []):
                    print(f"             {p['sku']:<19} {p['title']:<28} ${p['priceMinor'] / 100:.2f}")
        else:
            print("Usage: hermes air login [--name N] | whoami | logout | visit <siteUrl> [--mock <profile>] [--json]")
    except (air.AirError, VisitError, httpx.HTTPError) as exc:
        print(f"air: {exc}")


# --------------------------------------------------------------------------- slash: /air


def slash_air(raw_args: str) -> str:
    if (raw_args.strip() or "whoami") == "whoami":
        return json.dumps(_whoami(), indent=2)
    return "Usage: /air whoami   (login happens in a terminal: hermes air login)"
