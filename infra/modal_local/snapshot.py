"""Build-time software checks and retained package snapshots."""

import importlib.metadata
import json
import platform
import shutil
import subprocess
from pathlib import Path

base = Path("/opt/astra/local")
versions = {
    name: importlib.metadata.version(name)
    for name in ("blender-mcp", "mcp", "requests", "Pillow")
}
assert versions == {
    "blender-mcp": "1.9.1",
    "mcp": "1.30.0",
    "requests": "2.34.2",
    "Pillow": "12.1.1",
}
for command in (
    ("blender", "--version"),
    ("codex", "--version"),
    ("node", "--version"),
    ("npm", "--version"),
):
    versions[command[0]] = subprocess.check_output(command, text=True).strip()
assert versions["codex"] == "codex-cli 0.153.4"
assert "5.2.1" in versions["blender"]
for args in (
    ("codex", "exec-server", "--help"),
    ("codex", "exec", "--help"),
    ("codex", "mcp", "--help"),
    ("codex", "login", "--help"),
):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL)
versions["python"] = platform.python_version()
config = Path.home() / ".codex/config.toml"
config.parent.mkdir(parents=True, exist_ok=True)
created_config = not config.exists()
if created_config:
    shutil.copyfile(base / "codex-config.toml", config)
versions["codex_mcp"] = json.loads(
    subprocess.check_output(["codex", "mcp", "get", "blender", "--json"], text=True)
)
if created_config:
    config.unlink()
versions["platform"] = platform.platform()
versions["ocio_configs"] = [
    str(path)
    for path in Path("/opt/blender").glob("*/datafiles/colormanagement/config.ocio")
]
assert versions["ocio_configs"], "Bundled OCIO missing"
for name, command in (
    ("python-freeze.txt", ["python", "-m", "pip", "freeze"]),
    ("os-packages.txt", ["dpkg-query", "-W"]),
    ("node-packages.json", ["npm", "list", "--global", "--json"]),
):
    (base / name).write_text(subprocess.check_output(command, text=True))
(base / "versions.json").write_text(json.dumps(versions, indent=2) + "\n")
print(json.dumps(versions), flush=True)
