"""What tools/deploy.py puts in the package. Running the ACARS client from source leaves a 900+ MB Edge profile and
local flight state next to the code; none of it may ship, or the deploy trips its size guard (or worse, uploads it)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import deploy  # noqa: E402


def _wanted(rel):
    return deploy.wanted(deploy.ROOT / rel)


def test_local_acars_runtime_files_are_not_packaged():
    for rel in ("acars_client/window-profile/Default/Cache/data_1",
                "acars_client/window-profile/component_crx_cache/x.crx",
                "acars_client/flight_state.pkl", "acars_client/acars.log", "acars_client/pac-acars.pid",
                "acars_client/config.json", "acars_client/build/dist/PAC ACARS.exe"):
        assert not _wanted(rel), rel


def test_venv_folders_are_not_packaged():
    assert not _wanted(".venv/Lib/site-packages/x.py")
    assert not _wanted("venv/Lib/site-packages/x.py")


def test_program_files_and_reference_data_still_ship():
    for rel in ("app.py", "analysis.py", "static/app.js", "acars_client/client.py", "acars_client/ui.html",
                "deploy/update.sh", "data/routes.json", "data/runways.json"):
        assert _wanted(rel), rel


def test_pilot_data_still_never_ships():
    for rel in ("data/logbook.db", "data/bot_secret", "data/settings.json", "data/secret_key"):
        assert not _wanted(rel), rel
