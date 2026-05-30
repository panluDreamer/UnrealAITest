"""``devbridge serve`` — TCP server that accepts device connections.

The device-side UnrealEngineAIAssistRuntime C++ module connects *to us*
(like Unreal Insights ``-tracehost``), so the developer's machine
(stable IP on office network) acts as the server.

Protocol: same newline-delimited JSON as the editor bridge.
  Device sends handshake:  {"event":"connected","module":"DeviceBridge",...}\\n
  Host sends commands:     {"command":"ping","params":{}}\\n
  Device sends responses:  {"success":true,"message":"pong"}\\n

The command loop is interactive: once a device connects, the user (or AI
agent) can issue commands through the same process via ``devbridge --tcp``
flag, or through the returned connection object programmatically.

In practice, ``devbridge serve`` is a long-lived blocking process (like
``devbridge logcat --follow``).  Press Ctrl+C to stop.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import sys
import threading
import time
from typing import Optional

import click

from .. import output
from ..paths import plugin_root

# Default port — chosen within common enterprise WiFi allowed range (8000-8100)
DEFAULT_PORT = 8059
DEFAULT_IPC_PORT = 8060
# File written when a device is connected, so other devbridge instances can
# discover the TCP transport without ``--tcp`` flags.
_SESSION_FILE_NAME = "serve_session.json"


# --------------------------------------------------------------------------- #
# DeviceConnection — wraps a connected device socket
# --------------------------------------------------------------------------- #

class DeviceConnection:
    """Synchronous request/response over a connected device socket."""

    def __init__(self, sock: socket.socket, addr: tuple, handshake: dict):
        self.sock = sock
        self.addr = addr
        self.handshake = handshake
        self.platform: str = handshake.get("platform", "Unknown")
        self.engine_version: str = handshake.get("engine_version", "")
        self.module_version: str = handshake.get("version", "")
        self._lock = threading.Lock()

    @property
    def label(self) -> str:
        return f"{self.platform}@{self.addr[0]}:{self.addr[1]}"

    def send_command(self, command: str, params: dict | None = None,
                     timeout: float = 30.0) -> dict:
        """Send a command and wait for the JSON response."""
        params = params or {}
        payload = json.dumps({"command": command, "params": params}) + "\n"

        with self._lock:
            try:
                self.sock.settimeout(timeout)
                self.sock.sendall(payload.encode("utf-8"))

                # Read until newline
                chunks: list[bytes] = []
                while True:
                    chunk = self.sock.recv(65536)
                    if not chunk:
                        return {"success": False, "error": "Connection closed by device"}
                    chunks.append(chunk)
                    if b"\n" in b"".join(chunks):
                        break

                raw = b"".join(chunks).split(b"\n")[0]
                return json.loads(raw)
            except socket.timeout:
                return {"success": False, "error": f"Timeout ({timeout}s) waiting for response"}
            except (ConnectionError, OSError) as e:
                return {"success": False, "error": f"Connection error: {e}"}

    def ping(self) -> bool:
        resp = self.send_command("ping", timeout=5.0)
        return resp.get("success", False)

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# Session file — so other devbridge processes can discover the serve instance
# --------------------------------------------------------------------------- #

def _session_file_path() -> str:
    pdir = plugin_root()
    if not pdir:
        return ""
    return os.path.join(pdir, ".claude", "devbridge", _SESSION_FILE_NAME)


def _write_session(port: int, ipc_port: int, device: Optional[DeviceConnection]) -> None:
    path = _session_file_path()
    if not path:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {
        "pid": os.getpid(),
        "port": port,
        "ipc_port": ipc_port,
        "device_connected": device is not None,
    }
    if device:
        data["device_label"] = device.label
        data["device_platform"] = device.platform
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _remove_session() -> None:
    path = _session_file_path()
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def read_session() -> dict | None:
    """Read the session file left by a running ``devbridge serve``. Returns None if absent."""
    path = _session_file_path()
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


# --------------------------------------------------------------------------- #
# IPC server thread — accepts commands from other devbridge processes
# --------------------------------------------------------------------------- #

class _IPCServer:
    """Local-only TCP server that proxies commands to the connected device.

    Other ``devbridge`` processes read serve_session.json, discover the IPC port,
    connect here, send a JSON command, and get the response back.
    """

    def __init__(self, ipc_port: int, get_device):
        self.ipc_port = ipc_port
        self._get_device = get_device  # callable returning Optional[DeviceConnection]
        self._server: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self) -> bool:
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._server.bind(("127.0.0.1", self.ipc_port))
        except OSError:
            return False
        self._server.listen(10)
        self._server.settimeout(1.0)
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._running = False
        if self._server:
            try:
                self._server.close()
            except OSError:
                pass
        if self._thread:
            self._thread.join(timeout=3)

    def _accept_loop(self) -> None:
        while self._running:
            try:
                conn, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            # Handle each IPC client in a short-lived thread
            threading.Thread(target=self._handle_ipc_client, args=(conn,), daemon=True).start()

    def _handle_ipc_client(self, conn: socket.socket) -> None:
        conn.settimeout(30.0)
        try:
            # Read one JSON line
            data = b""
            while b"\n" not in data:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                data += chunk

            msg = data.split(b"\n")[0].decode("utf-8")
            device = self._get_device()

            if device is None:
                resp = json.dumps({"success": False, "error": "No device connected to serve"})
            else:
                # Parse command and forward to device
                try:
                    obj = json.loads(msg)
                    cmd = obj.get("command", "")
                    params = obj.get("params", {})
                    resp_dict = device.send_command(cmd, params)
                    resp = json.dumps(resp_dict, ensure_ascii=False)
                except json.JSONDecodeError:
                    resp = json.dumps({"success": False, "error": "Invalid JSON"})
                except Exception as e:
                    resp = json.dumps({"success": False, "error": str(e)})

            conn.sendall((resp + "\n").encode("utf-8"))
        except (socket.timeout, OSError):
            pass
        finally:
            conn.close()


# --------------------------------------------------------------------------- #
# Click command
# --------------------------------------------------------------------------- #

@click.command(
    name="serve",
    help=(
        "Start a TCP server and wait for a device to connect.\n\n"
        "On device, connect via console command:\n"
        "  AIAssistDeviceBridge <host_ip>:8059\n\n"
        "Or via launch arg / ue4commandline.txt:\n"
        "  -AIAssistDeviceBridgeHost=<host_ip>:8059\n\n"
        "Modes:\n"
        "  (default)  Interactive REPL after device connects.\n"
        "  --daemon   Run headless in background. Other devbridge processes\n"
        "             auto-route commands through the IPC port.\n"
        "  --stop     Kill a running daemon and exit.\n\n"
        "Press Ctrl+C to stop (interactive or daemon foreground)."
    ),
)
@click.option("--port", "-p", type=int, default=DEFAULT_PORT,
              help=f"TCP port to listen on (default {DEFAULT_PORT}).")
@click.option("--host", default="0.0.0.0",
              help="Bind address (default 0.0.0.0).")
@click.option("--one-shot", is_flag=True, default=False,
              help="Accept one connection, run one command loop, then exit.")
@click.option("--ipc-port", type=int, default=DEFAULT_IPC_PORT,
              help=f"Local IPC port for other devbridge processes (default {DEFAULT_IPC_PORT}).")
@click.option("--daemon", "-D", is_flag=True, default=False,
              help="Headless mode: no REPL, just accept devices and serve IPC. Stays in foreground (use & or run_in_background)."
              )
@click.option("--stop", "stop_daemon", is_flag=True, default=False,
              help="Kill a running serve process (reads PID from session file) and exit.")
@click.pass_context
def serve(ctx: click.Context, port: int, host: str, one_shot: bool,
          ipc_port: int, daemon: bool, stop_daemon: bool) -> None:
    json_mode = ctx.obj.get("json", False)

    # --stop: kill existing serve
    if stop_daemon:
        session = read_session()
        if not session:
            output.emit({"success": False, "error": "No running serve process found"}, json_mode=json_mode,
                        text="devbridge serve: no running process to stop.")
            return
        pid = session.get("pid")
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                output.emit({"success": True, "killed_pid": pid}, json_mode=json_mode,
                            text=f"devbridge serve: stopped (pid {pid})")
            except (OSError, ProcessLookupError):
                output.emit({"success": False, "error": f"Process {pid} not found (stale session)"}, json_mode=json_mode,
                            text=f"devbridge serve: process {pid} already gone, cleaning session.")
        _remove_session()
        return

    # Create server socket
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server.bind((host, port))
    except OSError as e:
        output.fail(f"Cannot bind to {host}:{port}: {e}", json_mode=json_mode)
        return

    server.listen(5)
    server.settimeout(1.0)  # 1s accept timeout for Ctrl+C responsiveness

    # Print startup info
    # Try to detect the machine's LAN IP for the user to copy-paste
    local_ip = _get_local_ip()

    # Start IPC server for other devbridge processes
    device_holder: list[Optional[DeviceConnection]] = [None]  # mutable ref for closure
    ipc = _IPCServer(ipc_port, lambda: device_holder[0])
    if not ipc.start():
        output.warn(f"Cannot bind IPC port 127.0.0.1:{ipc_port} — other devbridge processes won't be able to route through serve.")
        ipc_port = 0

    _write_session(port, ipc_port, None)

    if json_mode:
        output.emit({
            "event": "listening",
            "host": host,
            "port": port,
            "ipc_port": ipc_port,
            "local_ip": local_ip,
            "connect_cmd": f"AIAssistDeviceBridge {local_ip}:{port}",
        }, json_mode=True)
    else:
        sys.stderr.write(
            f"devbridge serve: listening on {host}:{port}  (IPC: 127.0.0.1:{ipc_port})\n"
            f"  On device, run:  AIAssistDeviceBridge {local_ip}:{port}\n"
            f"  Waiting for connection... (Ctrl+C to stop)\n"
        )

    device: Optional[DeviceConnection] = None

    try:
        while True:
            # Accept loop
            while device is None:
                try:
                    conn, addr = server.accept()
                except socket.timeout:
                    continue
                except KeyboardInterrupt:
                    raise

                # Read handshake
                conn.settimeout(10.0)
                try:
                    data = b""
                    while b"\n" not in data:
                        chunk = conn.recv(4096)
                        if not chunk:
                            break
                        data += chunk

                    if not data:
                        conn.close()
                        continue

                    handshake = json.loads(data.split(b"\n")[0])
                    device = DeviceConnection(conn, addr, handshake)
                    device_holder[0] = device
                    _write_session(port, ipc_port, device)

                    if json_mode:
                        output.emit({
                            "event": "device_connected",
                            "device": device.label,
                            "handshake": handshake,
                        }, json_mode=True)
                    else:
                        sys.stderr.write(
                            f"  Device connected: {device.label}\n"
                            f"  Platform: {device.platform}, Engine: {device.engine_version}\n"
                            f"  Ready. Type commands (or Ctrl+C to stop).\n\n"
                        )
                except (json.JSONDecodeError, socket.timeout, OSError) as e:
                    sys.stderr.write(f"  Connection from {addr} failed: {e}\n")
                    conn.close()
                    continue

            # After device connects: REPL or daemon wait
            if daemon:
                # Daemon mode: no REPL, just keep accepting IPC commands
                # Block until device disconnects (poll connection health)
                try:
                    while device and device.ping():
                        time.sleep(2.0)
                except KeyboardInterrupt:
                    raise
                except (ConnectionError, OSError):
                    pass
            else:
                # Interactive command loop
                try:
                    _interactive_loop(ctx, device, json_mode)
                except KeyboardInterrupt:
                    raise
                except (ConnectionError, OSError):
                    pass

            # Device disconnected
            if device:
                if not json_mode:
                    sys.stderr.write(f"\n  Device {device.label} disconnected.\n")
                device.close()
                device = None
                device_holder[0] = None
                _write_session(port, ipc_port, None)

                if one_shot:
                    break

                if not json_mode:
                    sys.stderr.write("  Waiting for new connection...\n")

    except KeyboardInterrupt:
        if not json_mode:
            sys.stderr.write("\ndevbridge serve: shutting down.\n")
    finally:
        if device:
            device.close()
        ipc.stop()
        server.close()
        _remove_session()


def _interactive_loop(ctx: click.Context, device: DeviceConnection,
                      json_mode: bool) -> None:
    """Read commands from stdin and send them to the device.

    Non-interactive (piped) mode: reads JSON commands from stdin.
    Interactive (tty) mode: simple REPL with tab-completion-free prompts.
    """
    is_tty = hasattr(sys.stdin, "isatty") and sys.stdin.isatty()

    while True:
        # Read input
        try:
            if is_tty:
                line = input(f"devbridge({device.platform})> ").strip()
            else:
                line = sys.stdin.readline()
                if not line:
                    break  # EOF
                line = line.strip()
        except EOFError:
            break

        if not line:
            continue

        if line.lower() in ("exit", "quit", "q"):
            break

        # Parse: either raw JSON or shorthand
        cmd_name, params = _parse_input(line)
        if not cmd_name:
            if not json_mode:
                sys.stderr.write(f"  Unknown input. Try: ping, exec_console <cmd>, "
                                 f"exec_unlua <code>, get_cvar <name>, set_cvar <name> <val>, "
                                 f"get_log [count], get_info\n")
            continue

        resp = device.send_command(cmd_name, params)

        if json_mode:
            output.emit(resp, json_mode=True)
        else:
            _print_response(cmd_name, resp)


def _parse_input(line: str) -> tuple[str, dict]:
    """Parse interactive input into (command, params).

    Supports both raw JSON and shorthand syntax:
      ping
      exec_console stat fps
      exec_unlua return 1+1
      get_cvar r.ShadowQuality
      set_cvar r.ShadowQuality 0
      get_log 50
      get_info
    """
    # Try JSON first
    if line.startswith("{"):
        try:
            obj = json.loads(line)
            return obj.get("command", ""), obj.get("params", {})
        except json.JSONDecodeError:
            pass

    parts = line.split(None, 1)
    cmd = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""

    if cmd == "ping":
        return "ping", {}
    elif cmd in ("exec_console", "cmd"):
        return "exec_console", {"command": rest}
    elif cmd in ("exec_unlua", "lua"):
        return "exec_unlua", {"code": rest}
    elif cmd in ("get_cvar",):
        return "get_cvar", {"name": rest.strip()}
    elif cmd in ("set_cvar",):
        kv = rest.split(None, 1)
        if len(kv) == 2:
            return "set_cvar", {"name": kv[0], "value": kv[1]}
        return "", {}
    elif cmd in ("get_log", "log"):
        count = 100
        try:
            count = int(rest) if rest else 100
        except ValueError:
            pass
        return "get_log", {"count": count}
    elif cmd in ("get_info", "info"):
        return "get_info", {}
    else:
        return "", {}


def _print_response(cmd: str, resp: dict) -> None:
    """Pretty-print a response for human-readable mode."""
    ok = resp.get("success", False)
    tag = "[OK]" if ok else "[FAIL]"

    if cmd == "ping":
        sys.stdout.write(f"  {tag} {resp.get('message', '')}\n")
    elif cmd == "get_cvar":
        if ok:
            sys.stdout.write(f"  {tag} {resp.get('name', '')} = {resp.get('value', '')}\n")
        else:
            sys.stdout.write(f"  {tag} {resp.get('error', '')}\n")
    elif cmd == "set_cvar":
        if ok:
            sys.stdout.write(f"  {tag} {resp.get('name', '')}: {resp.get('previous', '')} -> {resp.get('value', '')}\n")
        else:
            sys.stdout.write(f"  {tag} {resp.get('error', '')}\n")
    elif cmd in ("exec_console", "exec_unlua"):
        out = resp.get("output", "")
        if ok:
            if out:
                sys.stdout.write(f"  {tag}\n{out}\n")
            else:
                sys.stdout.write(f"  {tag} (no output)\n")
        else:
            sys.stdout.write(f"  {tag} {resp.get('error', '')}\n")
    elif cmd == "get_log":
        entries = resp.get("entries", [])
        sys.stdout.write(f"  {tag} {len(entries)} log entries\n")
        for e in entries[-10:]:  # Show last 10 inline
            verb = e.get("verbosity", "info")
            cat = e.get("category", "")
            msg = e.get("message", "")
            prefix = {"error": "ERR", "warning": "WRN"}.get(verb, "   ")
            sys.stdout.write(f"    [{prefix}] [{cat}] {msg}\n")
        if len(entries) > 10:
            sys.stdout.write(f"    ... ({len(entries) - 10} more entries)\n")
    elif cmd == "get_info":
        if ok:
            for k, v in resp.items():
                if k != "success" and v:
                    sys.stdout.write(f"  {k}: {v}\n")
        else:
            sys.stdout.write(f"  {tag} {resp.get('error', '')}\n")
    else:
        sys.stdout.write(f"  {json.dumps(resp, indent=2, ensure_ascii=False)}\n")


def _get_local_ip() -> str:
    """Best-effort detection of LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"
