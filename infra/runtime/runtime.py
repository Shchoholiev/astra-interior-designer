"""Session-local Blender/executor supervisor and S3 workspace synchronization."""

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import socketserver
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Config:
    session_id: str
    environment_id: str
    bucket: str
    prefix: str
    region: str
    remote_url: str
    workspace: Path = Path("/workspace")
    state_dir: Path = Path("/run/astra")

    @classmethod
    def from_env(cls, env):
        required = (
            "SESSION_ID",
            "ENVIRONMENT_ID",
            "S3_BUCKET",
            "S3_PREFIX",
            "AWS_REGION",
            "AGENTS_REMOTE_URL",
            "CODEX_API_KEY",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
        )
        if missing := [name for name in required if not env.get(name)]:
            raise ValueError("Missing runtime configuration: " + ", ".join(missing))
        session_id = env["SESSION_ID"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", session_id):
            raise ValueError("Invalid session identifier")
        if env["S3_PREFIX"] != f"sandboxes/{session_id}/":
            raise ValueError("S3 prefix must belong to the session")
        remote = urlsplit(env["AGENTS_REMOTE_URL"])
        if remote.scheme != "https" or not remote.hostname or remote.username:
            raise ValueError("Agents remote must be an HTTPS URL without credentials")
        return cls(
            session_id,
            env["ENVIRONMENT_ID"],
            env["S3_BUCKET"],
            env["S3_PREFIX"],
            env["AWS_REGION"],
            env["AGENTS_REMOTE_URL"],
        )


@contextlib.contextmanager
def destination_parent(root, relative):
    """Resolve only ordinary directories, keeping atomic writes relative to an fd."""
    parts = relative.split("/")
    if "\\" in relative or any(part in ("", ".", "..") for part in parts):
        raise ValueError("Invalid workspace object path")
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            try:
                os.mkdir(part, mode=0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            try:
                child = os.open(
                    part,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=descriptor,
                )
            except OSError as error:
                raise ValueError(
                    "Workspace directories must not be symlinks"
                ) from error
            os.close(descriptor)
            descriptor = child
        try:
            existing = os.stat(parts[-1], dir_fd=descriptor, follow_symlinks=False)
            if not stat.S_ISREG(existing.st_mode):
                raise ValueError("Workspace destination must be a regular file")
        except FileNotFoundError:
            pass
        yield descriptor, parts[-1]
    finally:
        os.close(descriptor)


def valid_glb(stream):
    """Require a complete GLB 2 container with embedded rather than external assets."""
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)
    if size < 20:
        return False
    magic, version, total = struct.unpack("<4sII", stream.read(12))
    if magic != b"glTF" or version != 2 or total != size:
        return False
    first = True
    while stream.tell() < size:
        header = stream.read(8)
        if len(header) != 8:
            return False
        length, kind = struct.unpack("<I4s", header)
        if length % 4 or stream.tell() + length > size:
            return False
        if first:
            if kind != b"JSON" or length > 32 * 1024 * 1024:
                return False
            try:
                document = json.loads(stream.read(length))
                if document.get("asset", {}).get("version") != "2.0":
                    return False
                for item in document.get("buffers", []) + document.get("images", []):
                    if "uri" in item and not item["uri"].startswith("data:"):
                        return False
            except (ValueError, AttributeError, TypeError):
                return False
            first = False
        else:
            stream.seek(length, os.SEEK_CUR)
    stream.seek(0)
    return not first


def signature(info):
    return info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


class WorkspaceSync:
    def __init__(self, config, client):
        self.config = config
        self.client = client
        self.input_etags = {}
        self.pending_scene = None
        self.uploaded_scene = None
        self.uploaded_hash = None

    def download(self, key, relative, etag, *, scene=False):
        with destination_parent(self.config.workspace, relative) as (parent, name):
            temporary = f".astra-download-{uuid.uuid4().hex}"
            descriptor = os.open(
                temporary,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent,
            )
            try:
                with os.fdopen(descriptor, "w+b") as output:
                    response = self.client.get_object(
                        Bucket=self.config.bucket,
                        Key=key,
                        IfMatch=etag,
                    )
                    with contextlib.closing(response["Body"]) as body:
                        shutil.copyfileobj(body, output, length=1024 * 1024)
                    output.flush()
                    os.fsync(output.fileno())
                    if scene:
                        if not valid_glb(output):
                            raise ValueError("Persisted scene is not a complete GLB")
                        self.uploaded_hash = hashlib.file_digest(
                            output, "sha256"
                        ).digest()
                os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
            finally:
                try:
                    os.unlink(temporary, dir_fd=parent)
                except FileNotFoundError:
                    pass

    def sync_inputs(self):
        prefix = self.config.prefix + "inputs/"
        pages = self.client.get_paginator("list_objects_v2").paginate(
            Bucket=self.config.bucket,
            Prefix=prefix,
        )
        for page in pages:
            for item in page.get("Contents", []):
                key = item["Key"]
                if not key.startswith(prefix):
                    raise ValueError("S3 returned an object outside this session")
                if key.endswith("/"):
                    continue
                relative = "inputs/" + key[len(prefix) :]
                if self.input_etags.get(key) == item["ETag"]:
                    continue
                self.download(key, relative, item["ETag"])
                self.input_etags[key] = item["ETag"]

    def restore(self):
        self.config.workspace.mkdir(parents=True, exist_ok=True)
        self.sync_inputs()
        key = self.config.prefix + "scene.glb"
        # A prefix-constrained ListBucket grant can list this exact key without
        # relying on HEAD's ambiguous 403 response for an absent initial scene.
        pages = self.client.get_paginator("list_objects_v2").paginate(
            Bucket=self.config.bucket,
            Prefix=key,
        )
        for page in pages:
            for item in page.get("Contents", []):
                if item["Key"] == key:
                    self.download(key, "scene.glb", item["ETag"], scene=True)
                    return

    def publish_scene(self, *, force=False):
        scene = self.config.workspace / "scene.glb"
        try:
            info = scene.lstat()
        except FileNotFoundError:
            return
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("Scene must be a regular file, not a symlink")
        current = signature(info)
        if current == self.uploaded_scene:
            return
        if current != self.pending_scene and not force:
            self.pending_scene = current
            return
        descriptor = os.open(scene, os.O_RDONLY | os.O_NOFOLLOW)
        with (
            os.fdopen(descriptor, "rb") as source,
            tempfile.TemporaryFile(
                dir=self.config.state_dir,
            ) as snapshot,
        ):
            if signature(os.fstat(source.fileno())) != current:
                return
            shutil.copyfileobj(source, snapshot, length=1024 * 1024)
            if signature(os.fstat(source.fileno())) != current:
                return
            try:
                if signature(scene.lstat()) != current:
                    return
            except FileNotFoundError:
                return
            if not valid_glb(snapshot):
                return  # Blender may be in the middle of writing the export.
            digest = hashlib.file_digest(snapshot, "sha256").digest()
            if digest != self.uploaded_hash:
                snapshot.seek(0)
                self.client.put_object(
                    Bucket=self.config.bucket,
                    Key=self.config.prefix + "scene.glb",
                    Body=snapshot,
                    ContentType="model/gltf-binary",
                )
                self.uploaded_hash = digest
            self.uploaded_scene = current


def probe_blender(*, timeout=2, port=9876):
    deadline = time.monotonic() + timeout
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as connection:
        connection.sendall(b'{"type":"get_scene_info","params":{}}')
        data = bytearray()
        while len(data) < 16 * 1024 * 1024:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Blender scene probe timed out")
            connection.settimeout(remaining)
            chunk = connection.recv(65536)
            if not chunk:
                raise ConnectionError("Blender closed the scene probe")
            data.extend(chunk)
            try:
                response = json.loads(data)
            except (ValueError, UnicodeDecodeError):
                continue
            if response.get("status") != "success" or not isinstance(
                response.get("result"),
                dict,
            ):
                raise RuntimeError("Blender scene probe failed")
            return
        raise RuntimeError("Blender scene probe exceeded response limit")


class ControlHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(25)
        command = self.rfile.readline(128).decode().strip()
        supervisor = self.server.supervisor
        try:
            if command == "health":
                result = supervisor.health()
            elif command == "reconnect-executor":
                supervisor.reconnect_executor()
                result = {
                    "executor_running": supervisor.running("executor"),
                    "ok": True,
                }
            else:
                result = {"ok": False, "error": "Unknown runtime command"}
        except Exception as error:
            result = {"ok": False, "error": type(error).__name__}
        self.wfile.write(json.dumps(result).encode() + b"\n")


class ControlServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True


class Supervisor:
    def __init__(self, config, client):
        self.config = config
        self.sync = WorkspaceSync(config, client)
        self.children = {}
        self.process_lock = threading.RLock()
        self.probe_lock = threading.Lock()
        self.stopping = threading.Event()
        self.storage_error = None

    def running(self, name):
        child = self.children.get(name)
        return child is not None and child.poll() is None

    def spawn(self, name, command):
        environment = dict(os.environ)
        if name != "executor":
            for key in (
                "CODEX_API_KEY",
                "AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY",
                "AWS_SESSION_TOKEN",
            ):
                environment.pop(key, None)
        # Inherit stdout/stderr directly so provider logs retain child failures.
        self.children[name] = subprocess.Popen(
            command,
            cwd=self.config.workspace,
            env=environment,
            start_new_session=True,
        )

    def start_executor(self):
        self.spawn(
            "executor",
            [
                "codex",
                "exec-server",
                "--remote",
                self.config.remote_url,
                "--environment-id",
                self.config.environment_id,
            ],
        )

    @staticmethod
    def stop_child(child):
        # The executor can exit before its command descendants. Always clean up
        # the process group we created, including when its leader has exited.
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            child.wait(timeout=8)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait(timeout=3)

    def stop_children(self):
        with self.process_lock:
            for child in reversed(list(self.children.values())):
                self.stop_child(child)

    def reconnect_executor(self):
        with self.process_lock:
            if self.stopping.is_set() or not all(
                self.running(n) for n in ("xvfb", "blender")
            ):
                raise RuntimeError(
                    "Cannot reconnect without the live Blender workspace"
                )
            if child := self.children.get("executor"):
                self.stop_child(child)
            self.start_executor()
            if not self.running("executor"):
                raise RuntimeError("Executor exited during reconnect")

    def blender_busy(self):
        try:
            return (
                json.loads(
                    (self.config.state_dir / "blender-command.json").read_text()
                ).get("busy")
                is True
            )
        except (OSError, ValueError):
            return False

    def health(self):
        with self.process_lock:
            blender_alive = self.running("blender")
            result = {
                "blender_ready": False,
                "blender_busy": False,
                "blender_state": "starting",
                "executor_running": self.running("executor"),
                "xvfb_running": self.running("xvfb"),
                "storage_error": self.storage_error,
            }
            if "blender" in self.children and not blender_alive:
                result["blender_state"] = "dead"
                return result
            if not blender_alive or not result["xvfb_running"]:
                return result
        if self.blender_busy():
            result.update(blender_state="busy", blender_busy=True)
            return result
        # Do not enqueue a second probe behind a slow first probe.
        if not self.probe_lock.acquire(blocking=False):
            result["blender_state"] = "checking"
            return result
        try:
            probe_blender()
            result.update(blender_state="ready", blender_ready=True)
        except TimeoutError:
            busy = self.blender_busy()
            result.update(
                blender_state="busy" if busy else "unresponsive", blender_busy=busy
            )
        except (OSError, RuntimeError, ValueError):
            result["blender_state"] = "unresponsive"
        finally:
            self.probe_lock.release()
        return result

    def storage_loop(self):
        while not self.stopping.wait(2):
            try:
                self.sync.sync_inputs()
                self.sync.publish_scene()
                self.storage_error = None
            except Exception as error:
                self.storage_error = type(error).__name__
                print("ASTRA_STORAGE_RETRY " + self.storage_error, flush=True)

    def wait_for(self, condition, timeout, message):
        deadline = time.monotonic() + timeout
        while not condition():
            if self.stopping.is_set() or any(
                child.poll() is not None for child in self.children.values()
            ):
                raise RuntimeError("Essential process exited during startup")
            if time.monotonic() >= deadline:
                raise RuntimeError(message)
            self.stopping.wait(0.2)

    def run(self):
        self.config.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.config.workspace.mkdir(parents=True, exist_ok=True)
        # Keep ownership for the supervisor's full lifetime; reject duplicate starts.
        with (self.config.state_dir / "supervisor.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            control_path = self.config.state_dir / "control.sock"
            control_path.unlink(missing_ok=True)
            with ControlServer(str(control_path), ControlHandler) as control:
                control.supervisor = self
                os.chmod(control_path, 0o600)
                control_thread = threading.Thread(
                    target=control.serve_forever, daemon=True
                )
                control_thread.start()
                storage_thread = None
                try:
                    self.sync.restore()
                    (self.config.workspace / "inputs").mkdir(exist_ok=True)
                    self.spawn(
                        "xvfb",
                        [
                            "Xvfb",
                            ":99",
                            "-screen",
                            "0",
                            "1280x720x24",
                            "-nolisten",
                            "tcp",
                        ],
                    )
                    self.wait_for(
                        lambda: Path("/tmp/.X11-unix/X99").exists(),
                        15,
                        "Xvfb startup timed out",
                    )
                    self.spawn(
                        "blender",
                        [
                            "blender",
                            "--factory-startup",
                            "-noaudio",
                            "--python-exit-code",
                            "1",
                            "--python",
                            "/opt/astra/bootstrap_blender.py",
                        ],
                    )
                    self.wait_for(
                        lambda: self.health()["blender_ready"],
                        120,
                        "Blender startup timed out",
                    )
                    self.start_executor()
                    storage_thread = threading.Thread(
                        target=self.storage_loop, daemon=True
                    )
                    storage_thread.start()
                    print("ASTRA_RUNTIME_READY", flush=True)
                    while not self.stopping.wait(0.25):
                        with self.process_lock:
                            exited = {
                                name: child.poll()
                                for name, child in self.children.items()
                                if child.poll() is not None
                            }
                        if exited:
                            raise RuntimeError(
                                "Essential process exited: " + json.dumps(exited)
                            )
                finally:
                    self.stopping.set()
                    control.shutdown()
                    self.stop_children()
                    if storage_thread is not None:
                        storage_thread.join(timeout=25)
                    if storage_thread is None or not storage_thread.is_alive():
                        try:
                            self.sync.publish_scene(force=True)
                        except Exception as error:
                            print(
                                "ASTRA_FINAL_UPLOAD_FAILED " + type(error).__name__,
                                flush=True,
                            )
                    control_path.unlink(missing_ok=True)


def control_request(command, state_dir=Path("/run/astra")):
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(25 if command == "reconnect-executor" else 5)
        connection.connect(str(state_dir / "control.sock"))
        connection.sendall(command.encode() + b"\n")
        with connection.makefile("rb") as reader:
            result = json.loads(reader.readline(65536))
    print(json.dumps(result), flush=True)
    if command == "health":
        return (
            0 if result.get("blender_ready") and result.get("executor_running") else 2
        )
    return 0 if result.get("ok") else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("start", "health", "reconnect-executor"))
    command = parser.parse_args().command
    try:
        if command != "start":
            return control_request(command)
        config = Config.from_env(os.environ)
        import boto3
        from botocore.config import Config as BotoConfig

        client = boto3.client(
            "s3",
            region_name=config.region,
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
            aws_session_token=os.environ["AWS_SESSION_TOKEN"],
            config=BotoConfig(
                connect_timeout=5, read_timeout=10, retries={"total_max_attempts": 2}
            ),
        )
        supervisor = Supervisor(config, client)
        signal.signal(signal.SIGTERM, lambda *_: supervisor.stopping.set())
        signal.signal(signal.SIGINT, lambda *_: supervisor.stopping.set())
        supervisor.run()
        return 0
    except Exception as error:
        # Configuration errors contain variable names only, never credential values.
        print(
            json.dumps(
                {"blender_ready": False, "executor_running": False, "error": str(error)}
            ),
            flush=True,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
