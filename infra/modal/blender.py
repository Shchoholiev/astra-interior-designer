"""Pinned official Blender distribution for the Modal tooling image."""

import modal

BLENDER_VERSION = "5.2.1"
ARCHIVE = f"blender-{BLENDER_VERSION}-linux-x64.tar.xz"
RELEASE = "https://download.blender.org/release/Blender5.2"


def blender_image():
    return (
        modal.Image.debian_slim(python_version="3.12")
        .apt_install(
            "ca-certificates",
            "curl",
            "xz-utils",
            "xorg",
            "libxkbcommon0",
            "libegl1",
            "libgl1",
            "libsm6",
            "libxi6",
            "libxrender1",
        )
        .run_commands(
            f"curl -fSL --retry 3 {RELEASE}/{ARCHIVE} -o /tmp/{ARCHIVE}",
            f"curl -fSL --retry 3 {RELEASE}/blender-{BLENDER_VERSION}.sha256 "
            f"-o /tmp/blender.sha256",
            f"cd /tmp && grep ' {ARCHIVE}$' blender.sha256 | sha256sum -c -",
            f"mkdir -p /opt/blender /workspace && tar -xJf /tmp/{ARCHIVE} "
            "-C /opt/blender --strip-components=1",
            "ln -s /opt/blender/blender /usr/local/bin/blender",
            f"rm /tmp/{ARCHIVE} /tmp/blender.sha256",
            "blender --background --factory-startup --version",
        )
        .env({"NVIDIA_DRIVER_CAPABILITIES": "all"})
    )
