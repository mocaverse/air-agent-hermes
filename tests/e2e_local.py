"""AIR Agent KYA end-to-end against the real KYA demo site (mocaverse/air-kya Worker) in mock mode.

In mocaverse/air-kya:   npm run dev      (Worker, :8787)
                        npm run mock-air (mock AIR, :8799)
Then, from this repo:   python3 tests/e2e_local.py [http://127.0.0.1:8787]
"""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("air_agent_kya", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
pkg = importlib.util.module_from_spec(spec)
sys.modules["air_agent_kya"] = pkg
spec.loader.exec_module(pkg)
from air_agent_kya import tools  # noqa: E402
from air_agent_kya.kya import MOCK_PROFILES  # noqa: E402

SITE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8787"
EXPECT = {"good": "eligible"}

failed = 0
for profile in MOCK_PROFILES:
    out = json.loads(tools.kya_visit({"site": SITE, "mock_profile": profile}))
    want = EXPECT.get(profile, "ineligible")
    ok = out.get("viewer") == want
    failed += not ok
    print(f"{'PASS' if ok else 'FAIL'} {profile:<19} viewer={out.get('viewer')} reason={out.get('reason') or out.get('error')}")
print("\nall profiles as expected" if not failed else f"\n{failed} unexpected")
sys.exit(1 if failed else 0)
