"""Build a pinned Blender/MCP/executor image containing only tooling."""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from infra.modal.blender import blender_image  # noqa: E402

APP_NAME = "astra-interior-designer-blender"
RUNTIME_FILES = {
    "common.py",
    "boot.py",
    "bootstrap_blender.py",
    "render.py",
    "mcp_client.py",
    "verify.py",
    "snapshot.py",
    "codex-config.toml",
    "workspace-AGENTS.md",
}


def candidate_image():
    image = (
        blender_image()
        .apt_install("xvfb", "git", "ripgrep", "unzip", "nodejs", "npm")
        .pip_install_from_requirements(str(HERE / "requirements.lock"))
        .run_commands(
            "npm install --global @openai/codex@0.153.4",
            "mkdir -p /opt/astra/local /opt/astra/blender-scripts/addons "
            "/opt/astra/blender-python /run/astra /workspace",
            'python -c "import importlib.resources,shutil; '
            "shutil.copyfile(str(importlib.resources.files('blender_mcp')"
            ".joinpath('bundled/addon.py')), "
            "'/opt/astra/blender-scripts/addons/blender_mcp.py')\"",
            "python -m pip install --target /opt/astra/blender-python "
            "requests==2.34.2 certifi==2026.7.22 charset-normalizer==3.5.1 "
            "idna==3.19 urllib3==2.7.0",
        )
        .env(
            {
                "BLENDER_USER_SCRIPTS": "/opt/astra/blender-scripts",
                "BLENDER_HOST": "127.0.0.1",
                "BLENDER_PORT": "9876",
                "DISPLAY": ":99",
                "DISABLE_TELEMETRY": "true",
                "PYTHONUNBUFFERED": "1",
                "NVIDIA_DRIVER_CAPABILITIES": "all",
                "PYTHONPATH": "/opt/astra/local",
            }
        )
    )
    image = image.add_local_dir(
        HERE,
        "/opt/astra/local",
        ignore=lambda path: str(path) not in RUNTIME_FILES,
        copy=True,
    )
    return image.run_commands(
        "python /opt/astra/local/snapshot.py",
        "python -m compileall -q /opt/astra/local",
        "test ! -e /opt/astra/fixtures",
        "test ! -e /workspace/scene.blend",
    )
