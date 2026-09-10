"""Supervise Blender/Xvfb and an authenticated Agents API executor, with local state."""

import argparse
import json
import os
import signal
import socket
import socketserver
import subprocess
import threading
import time
from pathlib import Path

from common import ACTIVE_RENDER_STATES, classify_health, read_json, write_json

HERE = Path(__file__).resolve().parent
WORKSPACE = Path(os.environ.get("ASTRA_WORKSPACE", "/workspace"))
STATE = Path(os.environ.get("ASTRA_STATE_DIR", "/run/astra"))


def probe_blender(timeout=2):
    with socket.create_connection(("127.0.0.1", 9876), timeout=timeout) as stream:
        stream.sendall(b'{"type":"get_scene_info","params":{}}')
        data = b""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and len(data) < 8 * 1024 * 1024:
            stream.settimeout(max(0.01, deadline - time.monotonic()))
            chunk = stream.recv(65536)
            if not chunk:
                break
            data += chunk
            try:
                response = json.loads(data)
            except ValueError:
                continue
            return response.get("status") == "success" and isinstance(
                response.get("result", {}).get("objects"), list
            )
    return False


def initialize_workspace(configure_cli=False):
    for name in ("inputs", "assets", "scripts", "renders", "logs"):
        (WORKSPACE / name).mkdir(parents=True, exist_ok=True)
    STATE.mkdir(parents=True, exist_ok=True)
    STATE.chmod(0o700)
    files = [(HERE / "workspace-AGENTS.md", WORKSPACE / "AGENTS.md")]
    if configure_cli:
        files.append((HERE / "codex-config.toml", Path.home() / ".codex/config.toml"))
    for source, destination in files:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            with destination.open("x") as output:
                output.write(source.read_text())


class Supervisor:
    def __init__(self, blender_only=False):
        self.blender_only = blender_only
        self.children = {}
        self.stop = threading.Event()
        self.executor_lock = threading.Lock()
        self.logs = []
        self.started = time.time()

    def alive(self, name):
        child = self.children.get(name)
        return child is not None and child.poll() is None

    def check_essential_children(self):
        dead = [name for name in ("blender", "display") if not self.alive(name)]
        if dead:
            raise RuntimeError("Essential process exited: " + ", ".join(dead))

    def spawn(self, name, command, *, executor=False):
        environment = dict(os.environ)
        if not executor:
            for key in list(environment):
                if key.startswith(("AWS_", "OPENAI_", "MODAL_", "CODEX_")):
                    environment.pop(key)
        log = (WORKSPACE / "logs" / f"{name}.log").open("a", buffering=1)
        self.logs.append(log)
        process = subprocess.Popen(
            command,
            cwd=WORKSPACE,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self.children[name] = process
        write_json(
            STATE / "processes.json",
            {
                "supervisor": os.getpid(),
                "started_at": self.started,
                "children": {key: child.pid for key, child in self.children.items()},
            },
        )
        return process

    def start_executor(self):
        required = ("ENVIRONMENT_ID", "AGENTS_REMOTE_URL", "CODEX_API_KEY")
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise RuntimeError(
                "Missing runtime executor configuration: " + ", ".join(missing)
            )
        return self.spawn(
            "executor",
            [
                "codex",
                "exec-server",
                "--remote",
                os.environ["AGENTS_REMOTE_URL"],
                "--environment-id",
                os.environ["ENVIRONMENT_ID"],
            ],
            executor=True,
        )

    @staticmethod
    def terminate(child):
        # The leader may have exited while its MCP/shell children are still
        # alive. Every process is spawned in its own session, so this group
        # belongs to us even after the leader has been reaped.
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        if child.poll() is None:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait(timeout=5)

    def reconnect(self):
        if self.blender_only:
            raise RuntimeError(
                "This sandbox was explicitly started in Blender-only test mode"
            )
        with self.executor_lock:
            if self.stop.is_set():
                raise RuntimeError("Sandbox is stopping")
            if not self.alive("blender"):
                raise RuntimeError("Blender has exited")
            if "executor" in self.children:
                self.terminate(self.children["executor"])
            process = self.start_executor()
            return {
                "executor_pid": process.pid,
                "blender_pid": self.children["blender"].pid,
            }

    def health(self):
        command = read_json(STATE / "command.json")
        render = read_json(STATE / "render.json")
        busy = command.get("busy") or render.get("status") in ACTIVE_RENDER_STATES
        ready = False
        if self.alive("blender") and self.alive("display") and not busy:
            try:
                ready = probe_blender()
            except (OSError, ValueError):
                pass
        state = classify_health(
            self.alive("blender"), self.alive("display"), command, render, ready
        )
        return {
            "blender_state": state,
            "blender_ready": state == "ready",
            "blender_busy": state == "busy",
            "executor_running": self.alive("executor"),
            "mode": "blender-only" if self.blender_only else "agents-api",
            "render": render,
            "command": command,
            "pids": {name: process.pid for name, process in self.children.items()},
        }

    def run(self):
        initialize_workspace(configure_cli=self.blender_only)
        if not self.blender_only:
            missing = [
                key
                for key in ("ENVIRONMENT_ID", "AGENTS_REMOTE_URL", "CODEX_API_KEY")
                if not os.environ.get(key)
            ]
            if missing:
                raise RuntimeError(
                    "Missing runtime executor configuration: " + ", ".join(missing)
                )
        sock = STATE / "control.sock"
        if sock.exists():
            raise RuntimeError(
                "Supervisor control socket already exists; inspect the existing runtime"
            )
        supervisor = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                try:
                    self.connection.settimeout(15)
                    request = json.loads(self.rfile.readline(4096))
                    if request.get("action") == "health":
                        result = supervisor.health()
                    elif request.get("action") == "reconnect-executor":
                        result = supervisor.reconnect()
                    elif request.get("action") == "stop":
                        supervisor.stop.set()
                        result = {"stopping": True}
                    else:
                        raise ValueError("Unknown control action")
                except Exception as exc:
                    result = {"error": str(exc)}
                self.wfile.write(json.dumps(result).encode() + b"\n")

        class Server(socketserver.ThreadingUnixStreamServer):
            daemon_threads = True

        server = Server(str(sock), Handler)
        sock.chmod(0o600)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, lambda *_: self.stop.set())
        try:
            # Prior process state cannot make a new Blender look busy or ready.
            for name in ("command.json", "render.json", "blender.json", "ready.json"):
                (STATE / name).unlink(missing_ok=True)
            self.spawn(
                "display",
                ["Xvfb", ":99", "-screen", "0", "1280x720x24", "-nolisten", "tcp"],
            )
            deadline = time.monotonic() + 15
            while not Path("/tmp/.X11-unix/X99").exists():
                if not self.alive("display") or time.monotonic() > deadline:
                    raise RuntimeError("Virtual display failed to start")
                time.sleep(0.1)
            self.spawn(
                "blender",
                [
                    "blender",
                    "--factory-startup",
                    "-noaudio",
                    "--disable-autoexec",
                    "--python-exit-code",
                    "1",
                    "--python",
                    str(HERE / "bootstrap_blender.py"),
                ],
            )
            deadline = time.monotonic() + 120
            while not self.stop.is_set():
                if not self.alive("blender") or not self.alive("display"):
                    raise RuntimeError("Blender/display exited during startup")
                try:
                    if probe_blender():
                        break
                except (OSError, ValueError):
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError("Blender did not answer a real scene query")
                time.sleep(0.2)
            if self.stop.is_set():
                return
            if not self.blender_only:
                self.start_executor()
            write_json(STATE / "ready.json", self.health())
            print("ASTRA_READY", flush=True)
            while not self.stop.wait(0.25):
                # Executor exit is recoverable through reconnect-executor. Keep
                # the native scene alive while the session owner reconnects it.
                self.check_essential_children()
        finally:
            self.stop.set()
            server.shutdown()
            server.server_close()
            # An in-flight reconnect finishes before we take the final child
            # snapshot. Subsequent reconnects see stop and cannot spawn.
            with self.executor_lock:
                for child in reversed(list(self.children.values())):
                    try:
                        self.terminate(child)
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        print(
                            f"Cleanup failed for child {child.pid}: {exc}", flush=True
                        )
                for log in self.logs:
                    log.close()
            sock.unlink(missing_ok=True)
            write_json(
                STATE / "stopped.json",
                {name: child.poll() for name, child in self.children.items()},
            )
            for name in self.children:
                log_path = WORKSPACE / "logs" / f"{name}.log"
                print(
                    f"--- {name} log tail ---\n"
                    f"{log_path.read_text(errors='replace')[-12000:]}",
                    flush=True,
                )


def control(action):
    with socket.socket(socket.AF_UNIX) as stream:
        stream.settimeout(30)
        stream.connect(str(STATE / "control.sock"))
        stream.sendall(json.dumps({"action": action}).encode() + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = stream.recv(65536)
            if not chunk:
                break
            data += chunk
        return json.loads(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("start", "health", "stop", "reconnect-executor")
    )
    parser.add_argument(
        "--blender-only",
        action="store_true",
        help="Explicit software/GPU test mode, without an executor",
    )
    args = parser.parse_args()
    try:
        if args.action == "start":
            Supervisor(args.blender_only).run()
            return
        result = control(args.action)
        print(json.dumps(result), flush=True)
        if "error" in result:
            raise SystemExit(1)
        if args.action == "health":
            good = result["blender_ready"] and (
                result["executor_running"] or result["mode"] == "blender-only"
            )
            raise SystemExit(0 if good else 2)
    except (OSError, RuntimeError) as exc:
        print(
            json.dumps(
                {
                    "error": str(exc),
                    "blender_state": "dead",
                    "blender_ready": False,
                    "executor_running": False,
                }
            ),
            flush=True,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
