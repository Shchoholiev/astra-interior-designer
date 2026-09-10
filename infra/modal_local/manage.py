"""Build, launch, verify, and transfer files for the standalone Cycles candidate."""

import argparse
import asyncio
import json
import time
from pathlib import Path

import modal
from image import APP_NAME, candidate_image

RUNTIME = "/opt/astra/local"


class SandboxStartupError(RuntimeError):
    def __init__(self, message, sandbox_id, exit_code):
        super().__init__(message)
        self.cleanup = {"sandbox_id": sandbox_id, "exit_code": exit_code}


async def read_health(sandbox):
    process = await sandbox.exec.aio(
        "python", f"{RUNTIME}/boot.py", "health", timeout=10, pty=True
    )
    output = await process.stdout.read.aio()
    await process.wait.aio()
    try:
        health = json.loads(output)
    except ValueError:
        health = {}
    return process.returncode, health


async def bounded_health(sandbox, timeout):
    # Modal's command timeout starts after allocation. Bound allocation and
    # transport too, so an unavailable GPU cannot bypass our readiness deadline.
    return await asyncio.wait_for(read_health(sandbox), timeout=timeout)


def execute(sandbox, command, *, timeout=1800, interactive=False, log=None):
    process = sandbox.exec(*command, timeout=timeout, pty=True)
    if interactive:
        process.attach()
    else:
        for chunk in process.stdout:
            print(chunk, end="", flush=True)
            if log:
                log.write(chunk)
                log.flush()
    process.wait()
    if process.returncode:
        raise RuntimeError(f"Sandbox command exited {process.returncode}")


def build(output):
    started = time.monotonic()
    app = modal.App.lookup(APP_NAME, create_if_missing=True)
    image = candidate_image().build(app)
    result = {
        "image_id": image.object_id,
        "build_seconds": round(time.monotonic() - started, 3),
    }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)
    return image


def start(
    image,
    *,
    timeout=3600,
    blender_only=False,
    environment_id=None,
    executor_secret=None,
    remote_url=None,
):
    if timeout <= 0 or timeout > 3600:
        raise ValueError("Choose a hard lifetime between 1 and 3600 seconds")
    env, secrets = {}, []
    command = ["python", f"{RUNTIME}/boot.py", "start"]
    if blender_only:
        command.append("--blender-only")
    else:
        if not environment_id or not executor_secret or not remote_url:
            raise ValueError(
                "An Agents API environment ID, session remote URL, "
                "and Modal executor secret are required"
            )
        env.update(ENVIRONMENT_ID=environment_id, AGENTS_REMOTE_URL=remote_url)
        secrets.append(modal.Secret.from_name(executor_secret))
    before = time.monotonic()
    sandbox = modal.Sandbox.create(
        *command,
        app=modal.App.lookup(APP_NAME, create_if_missing=True),
        image=image,
        gpu="RTX-PRO-6000",
        cpu=4,
        memory=16384,
        timeout=timeout,
        workdir="/workspace",
        env=env,
        secrets=secrets,
    )
    print("SANDBOX_CREATED " + sandbox.object_id, flush=True)
    try:
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if sandbox.poll() is not None:
                print(sandbox.stdout.read(), flush=True)
                raise RuntimeError("Sandbox stopped before readiness")
            try:
                returncode, health = asyncio.run(
                    bounded_health(sandbox, max(0.1, deadline - time.monotonic()))
                )
            except TimeoutError:
                break
            if returncode == 0 and health.get("blender_ready"):
                result = {
                    "sandbox_id": sandbox.object_id,
                    "ready_seconds": round(time.monotonic() - before, 3),
                    "health": health,
                }
                print("SANDBOX_READY " + json.dumps(result), flush=True)
                return sandbox, result
            time.sleep(0.5)
        raise TimeoutError("Sandbox did not become ready within 180 seconds")
    except BaseException as exc:
        try:
            sandbox.terminate(wait=True)
            terminal = sandbox.poll()
        finally:
            sandbox.detach()
        if isinstance(exc, Exception):
            raise SandboxStartupError(str(exc), sandbox.object_id, terminal) from exc
        raise


def collect(sandbox, output):
    output.mkdir(parents=True, exist_ok=True)
    paths = [
        (f"{RUNTIME}/{name}", name)
        for name in (
            "versions.json",
            "python-freeze.txt",
            "os-packages.txt",
            "node-packages.json",
        )
    ]
    paths += [
        (f"/workspace/{name}", name)
        for name in (
            "scene.blend",
            "renders/acceptance.json",
            "renders/smoke.png",
            "renders/smoke-status.json",
            "renders/smoke-viewport.png",
            "renders/factory-viewport.png",
            "renders/asset-viewport.png",
            "assets/polyhaven-apple.blend",
            "assets/polyhaven-apple.json",
            "logs/blender.log",
            "logs/display.log",
        )
    ]
    missing = []
    for remote, local in paths:
        try:
            sandbox.filesystem.copy_to_local(remote, output / local)
        except modal.exception.Error as exc:
            missing.append({"path": remote, "error": type(exc).__name__})
    return missing


def verify(image, output, *, check_assets=False):
    output.mkdir(parents=True, exist_ok=False)
    sandboxes = []
    report = {
        "image_id": image.object_id,
        "status": "running",
        "instances": {},
        "cleanup": [],
    }
    try:
        for name in ("probe-a", "probe-b"):
            sandbox, ready = start(image, blender_only=True)
            sandboxes.append((name, sandbox))
            report["instances"][name] = ready
            (output / "sandboxes.json").write_text(
                json.dumps({n: s.object_id for n, s in sandboxes})
            )
            # Validate each allocation immediately. A later scheduling delay
            # must not discard the primary's independent render/asset evidence.
            # Both copies remain alive for the isolation checks below.
            folder = output / name
            folder.mkdir()
            command = ["python", f"{RUNTIME}/verify.py", "--name", name]
            if name == "probe-b":
                command.append("--isolation-only")
            elif check_assets:
                command.append("--check-assets")
            with (folder / "mcp.log").open("w") as log:
                execute(sandbox, command, log=log)
        for name, sandbox in sandboxes:
            other = "probe-b" if name == "probe-a" else "probe-a"
            own_scene = f"{name!r} in __import__('bpy').data.objects"
            other_scene = f"{other!r} in __import__('bpy').data.objects"
            source = (
                "import asyncio; from pathlib import Path; "
                "from mcp_client import connect,evaluate; "
                f"assert Path('/workspace/{name}.txt').read_text()=={name!r}; "
                f"assert not Path('/workspace/{other}.txt').exists()\n"
                "async def check():\n"
                " async with connect() as client:\n"
                f"  assert await evaluate(client, {own_scene!r})\n"
                f"  assert not await evaluate(client, {other_scene!r})\n"
                "asyncio.run(check()); print('ISOLATION_PASSED')"
            )
            execute(sandbox, ["python", "-c", source], timeout=120)
        report["isolation"] = True
        report["status"] = "software_gpu_passed"
        report["agent_session"] = (
            "unverified; an authenticated session is needed for integration validation"
        )
    except BaseException as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        if isinstance(exc, SandboxStartupError):
            report["cleanup"].append(exc.cleanup)
        raise
    finally:
        for name, sandbox in sandboxes:
            try:
                report["instances"][name]["unavailable_artifacts"] = collect(
                    sandbox, output / name
                )
                acceptance = output / name / "renders/acceptance.json"
                if acceptance.exists():
                    report["instances"][name]["acceptance"] = json.loads(
                        acceptance.read_text()
                    )
            except Exception as exc:
                report["instances"][name]["collection_error"] = str(exc)
            try:
                sandbox.terminate(wait=True)
                report["cleanup"].append(
                    {
                        "name": name,
                        "sandbox_id": sandbox.object_id,
                        "exit_code": sandbox.poll(),
                    }
                )
            except Exception as exc:
                report["status"] = "failed"
                report["cleanup"].append(
                    {
                        "name": name,
                        "sandbox_id": sandbox.object_id,
                        "exit_code": None,
                        "error": str(exc),
                    }
                )
            finally:
                try:
                    sandbox.detach()
                except Exception:
                    pass
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print("VERIFICATION_REPORT " + str(output.resolve()), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    compile_image = commands.add_parser("build")
    compile_image.add_argument("--output", type=Path)
    launch = commands.add_parser("start")
    launch.add_argument("--image-id", required=True)
    launch.add_argument("--timeout", type=int, default=3600)
    launch.add_argument("--blender-only", action="store_true")
    launch.add_argument("--environment-id")
    launch.add_argument("--executor-secret")
    launch.add_argument(
        "--remote-url", help="The session environment.remote_url returned by Agents API"
    )
    check = commands.add_parser("verify")
    source = check.add_mutually_exclusive_group(required=True)
    source.add_argument("--build", action="store_true")
    source.add_argument("--image-id")
    check.add_argument("--output", type=Path, required=True)
    check.add_argument("--check-assets", action="store_true")
    run = commands.add_parser("exec")
    run.add_argument("--pty", action="store_true")
    run.add_argument("sandbox_id")
    run.add_argument("command", nargs=argparse.REMAINDER)
    for action in ("put", "get"):
        transfer = commands.add_parser(action)
        transfer.add_argument("sandbox_id")
        transfer.add_argument("source")
        transfer.add_argument("destination")
    for action in ("health", "stop", "reconnect-executor"):
        command = commands.add_parser(action)
        command.add_argument("sandbox_id")
    publish = commands.add_parser("publish")
    publish.add_argument("--image-id", required=True)
    publish.add_argument("--name", required=True)
    args = parser.parse_args()
    with modal.enable_output():
        if args.action == "build":
            build(args.output)
        elif args.action == "verify":
            image = build(None) if args.build else modal.Image.from_id(args.image_id)
            verify(image, args.output, check_assets=args.check_assets)
        elif args.action == "publish":
            if args.name == "astra-blender:v1":
                raise ValueError(
                    "Use a fresh candidate name; production v1 is protected"
                )
            modal.Image.from_id(args.image_id).publish(args.name)
            print(json.dumps({"image_id": args.image_id, "published_name": args.name}))
        elif args.action == "start":
            sandbox, _ = start(
                modal.Image.from_id(args.image_id),
                timeout=args.timeout,
                blender_only=args.blender_only,
                environment_id=args.environment_id,
                executor_secret=args.executor_secret,
                remote_url=args.remote_url,
            )
            sandbox.detach()
        else:
            sandbox = modal.Sandbox.from_id(args.sandbox_id)
            try:
                if args.action == "exec":
                    command = (
                        args.command[1:] if args.command[:1] == ["--"] else args.command
                    )
                    if not command:
                        parser.error("Provide a command after the sandbox ID")
                    execute(sandbox, command, interactive=args.pty)
                elif args.action == "put":
                    sandbox.filesystem.copy_from_local(args.source, args.destination)
                elif args.action == "get":
                    if Path(args.destination).exists():
                        raise FileExistsError(args.destination)
                    sandbox.filesystem.copy_to_local(args.source, args.destination)
                elif args.action == "stop":
                    sandbox.terminate(wait=True)
                    print(
                        json.dumps(
                            {
                                "sandbox_id": sandbox.object_id,
                                "exit_code": sandbox.poll(),
                            }
                        )
                    )
                else:
                    execute(
                        sandbox,
                        ["python", f"{RUNTIME}/boot.py", args.action],
                        timeout=60,
                    )
            finally:
                sandbox.detach()


if __name__ == "__main__":
    main()
