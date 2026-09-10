"""Stage allowlisted API sources and the locked private SDK without credentials.

Only the printed directory is uploaded. Pass --dockerfile for a Docker build
context. The private SDK comes from uv.lock's commit, not a dirty checkout.
"""

import argparse
import io
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path


def stage_application(
    project: Path, output: Path, *, include_dockerfile: bool = False
) -> None:
    sources = [project / name for name in ("pyproject.toml", "uv.lock", "BACKEND.md")]
    sources.extend(sorted((project / "src").rglob("*.py")))
    sources.extend(sorted((project / "src").rglob("py.typed")))
    dockerfile = project / "infra" / "deployment" / "Dockerfile"
    if include_dockerfile:
        sources.append(dockerfile)
    for source in sources:
        relative = source.relative_to(project)
        if any(
            part.startswith(".") or part == "__pycache__" for part in relative.parts
        ):
            raise ValueError(f"Unexpected hidden source: {relative}")
        if any(
            path.is_symlink()
            for path in (source, *source.parents)
            if path != project.parent
        ):
            raise ValueError(f"Build input must not be a symlink: {relative}")
        if not source.is_file():
            raise ValueError(f"Missing application build input: {relative}")
    for source in sources:
        relative = (
            Path("Dockerfile") if source == dockerfile else source.relative_to(project)
        )
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def archive_sdk(repository: Path, revision: str, output: Path) -> None:
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("The SDK must be pinned to a full Git commit in uv.lock")
    archive = subprocess.check_output(
        [
            "git",
            "-C",
            str(repository),
            "archive",
            "--format=tar",
            revision,
        ]
    )
    output.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        bundle.extractall(output, filter="data")


def prepare(
    project: Path, sdk_source: Path | None, *, include_dockerfile: bool = False
) -> Path:
    lock = tomllib.loads((project / "uv.lock").read_text())
    package = next(item for item in lock["package"] if item["name"] == "agent-api-sdk")
    url, revision = package["source"]["git"].rsplit("#", 1)
    if url != "https://github.com/OpenAI-Early-Access/agents-api-python-preview.git":
        raise ValueError("Unexpected SDK repository in uv.lock")
    if sdk_source is None:
        cache = Path(subprocess.check_output(["uv", "cache", "dir"], text=True).strip())
        candidates = list((cache / "git-v0" / "checkouts").glob(f"*/{revision[:7]}"))
        if len(candidates) != 1:
            raise ValueError(
                "Pass --sdk-source with a local checkout of the locked SDK"
            )
        sdk_source = candidates[0]

    output = Path(tempfile.mkdtemp(prefix="astra-backend-build-"))
    try:
        stage_application(project, output, include_dockerfile=include_dockerfile)
        with tempfile.TemporaryDirectory(prefix="astra-sdk-source-") as temporary:
            source = Path(temporary) / "sdk"
            archive_sdk(sdk_source, revision, source)
            subprocess.run(
                [
                    "uv",
                    "build",
                    "--wheel",
                    "--out-dir",
                    str(output / "wheels"),
                    str(source),
                ],
                check=True,
                stdout=sys.stderr,
            )
        wheels = list((output / "wheels").glob("*.whl"))
        expected = f"agent_api_sdk-{package['version']}-py3-none-any.whl"
        if len(wheels) != 1 or wheels[0].name != expected:
            raise ValueError(
                "Expected one portable wheel matching the locked SDK version"
            )
        (output / "wheels" / ".gitignore").unlink(missing_ok=True)
    except BaseException:
        shutil.rmtree(output)
        raise
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument("--sdk-source", type=Path)
    parser.add_argument(
        "--dockerfile",
        action="store_true",
        help="Include infra/deployment/Dockerfile as the build context's Dockerfile",
    )
    arguments = parser.parse_args()
    print(
        prepare(
            arguments.project.resolve(),
            arguments.sdk_source,
            include_dockerfile=arguments.dockerfile,
        )
    )
