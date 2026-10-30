"""Exercise credential/keyfile creation and failure recovery without a database."""
import base64
from pathlib import Path
import re
import stat
import subprocess
import sys

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "bootstrap_dev.py"


def run(output):
    return subprocess.run([sys.executable, str(SCRIPT), "--output", str(output)], capture_output=True, text=True)


def test_bootstrap_creates_independent_protected_mongodb_credentials(tmp_path):
    output = tmp_path / ".env"
    assert run(output).returncode == 0
    values = dict(line.split("=", 1) for line in output.read_text().splitlines() if line and not line.startswith("#"))
    passwords = [values[name] for name in ("MONGO_ROOT_PASSWORD", "MONGODB_OWNER_PASSWORD", "MONGODB_RUNTIME_PASSWORD")]
    assert len(set(passwords)) == 3
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{32,}", value) for value in passwords)
    assert values["MONGODB_DATABASE"] == "asic_tracker_dev"
    keyfile = tmp_path / "secrets" / "mongodb-keyfile"
    assert len(base64.b64decode(keyfile.read_text(), validate=False)) == 512
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert stat.S_IMODE(keyfile.stat().st_mode) == 0o600


def test_bootstrap_rerun_preserves_existing_credentials_and_keyfile(tmp_path):
    output = tmp_path / ".env"
    assert run(output).returncode == 0
    keyfile = tmp_path / "secrets" / "mongodb-keyfile"
    before = output.read_bytes(), keyfile.read_bytes()
    result = run(output)
    assert result.returncode != 0
    assert "left unchanged" in result.stderr
    assert (output.read_bytes(), keyfile.read_bytes()) == before


def test_existing_keyfile_failure_removes_only_new_env_file(tmp_path):
    output = tmp_path / ".env"
    keyfile = tmp_path / "secrets" / "mongodb-keyfile"
    keyfile.parent.mkdir()
    keyfile.write_text("existing-owned-key")
    assert run(output).returncode != 0
    assert not output.exists()
    assert keyfile.read_text() == "existing-owned-key"
