"""Build the production runtime on the verified, named Blender software image.

No credential is read and no cloud operation runs when this module is imported.
Publishing is explicit and separate from building so integration checks can run first.
"""

import argparse
import json
from pathlib import Path

import modal

BASE_IMAGE = "astra-blender:probe2-20260910"
IMAGE_NAME = "astra-blender:v2"
APP_NAME = "astra-interior-designer-blender"
HERE = Path(__file__).resolve().parent


def production_image():
    return (
        modal.Image.from_name(BASE_IMAGE)
        .add_local_file(HERE / "runtime.py", "/opt/astra/runtime.py", copy=True)
        .add_local_file(
            HERE / "bootstrap_blender.py", "/opt/astra/bootstrap_blender.py", copy=True
        )
        .env(
            {
                "BLENDER_USER_SCRIPTS": "/opt/astra/blender-scripts",
                "BLENDER_HOST": "127.0.0.1",
                "BLENDER_PORT": "9876",
                "DISABLE_TELEMETRY": "true",
                "DISPLAY": ":99",
                "PYTHONUNBUFFERED": "1",
                "AWS_EC2_METADATA_DISABLED": "true",
            }
        )
        .run_commands(
            "useradd --uid 10001 --user-group --create-home "
            "--shell /bin/bash astra-agent",
            "mkdir -p /run/astra /run/astra-blender /workspace/inputs "
            "&& chmod 700 /run/astra /run/astra-blender "
            "&& chown 10001:10001 /run/astra-blender "
            "&& chmod 1777 /workspace && chmod 755 /workspace/inputs",
            "python -m py_compile /opt/astra/runtime.py "
            "/opt/astra/bootstrap_blender.py",
            "python /opt/astra/runtime.py --help",
            "blender --version && codex --version && codex exec-server --help",
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--publish", action="store_true", help="Publish after integration validation"
    )
    arguments = parser.parse_args()
    with modal.enable_output():
        app = modal.App.lookup(APP_NAME, create_if_missing=True)
        image = production_image().build(app)
        if arguments.publish:
            image.publish(IMAGE_NAME)
        print(
            json.dumps(
                {
                    "image_id": image.object_id,
                    "published_name": IMAGE_NAME if arguments.publish else None,
                }
            )
        )


if __name__ == "__main__":
    main()
