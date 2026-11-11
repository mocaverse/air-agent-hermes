"""Tool schemas: what the model reads."""

from .kya import MOCK_PROFILES

AIR_WHOAMI = {
    "name": "air_whoami",
    "description": (
        "Show whether this agent holds an AIR delegation (Moca Network): AIR user id, partner id and Console. "
        "Read-only. Use when unsure whether kya_visit can present a credential."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

KYA_VISIT = {
    "name": "kya_visit",
    "description": (
        "Enter an AIR KYA (Know-Your-Agent) gated store as the user's verified agent and return its catalog. "
        "Reads the site's /.well-known/air-kya, gets a one-time nonce from /kya/challenge, asks AIR verify-by-agent "
        "for an SD-JWT presentation disclosing only the fields the site requests, and sends it as X-AIR-KYA to "
        "/catalog. Returns the viewer class (human / ineligible / eligible), the site's reason code, the claim "
        "names disclosed and the catalog; never the credential itself. Live sites ask the user before disclosing."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "site": {"type": "string", "description": "Site base URL, e.g. https://air-kya-demo-staging.0xmythril.workers.dev"},
            "mock_profile": {
                "type": "string",
                "enum": MOCK_PROFILES,
                "description": "Only for a local site in mock mode (`npm run dev` + `npm run mock-air`). Omit for live sites.",
            },
        },
        "required": ["site"],
    },
}
