"""Stage allowlisted API sources for the backend container build.

Only the printed directory is uploaded. Pass --dockerfile to include the
Dockerfile in the generated build context.
"""

import argparse
import shutil
import subprocess
import tempfile
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


def prepare(project: Path, *, include_dockerfile: bool = False) -> Path:
    output = Path(tempfile.mkdtemp(prefix="astra-backend-build-"))
    try:
        stage_application(project, output, include_dockerfile=include_dockerfile)
        subprocess.run(
            [
                "uv",
                "export",
                "--project",
                str(project),
                "--frozen",
                "--no-dev",
                "--no-emit-project",
                "--no-header",
                "--no-annotate",
                "--output-file",
                str(output / "requirements.txt"),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
    except BaseException:
        shutil.rmtree(output)
        raise
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument(
        "--dockerfile",
        action="store_true",
        help="Include infra/deployment/Dockerfile as the build context's Dockerfile",
    )
    arguments = parser.parse_args()
    print(
        prepare(
            arguments.project.resolve(),
            include_dockerfile=arguments.dockerfile,
        )
    )
