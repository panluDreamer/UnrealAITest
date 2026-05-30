"""Transport layer — abstracts communication with UE runtime.

Three transports, chosen automatically by ``auto_resolve``:

1. **TCPProxyTransport** — connects to a running ``devbridge serve`` IPC port.
   The serve process holds the persistent device TCP connection and forwards
   our commands. This is the preferred transport for TCP-connected devices.

2. **ADBTransport** — the original ADB broadcast mechanism.  Works for
   Android devices over USB.  Fire-and-forget (no return values from
   ``exec_console``).

3. **EditorTransport** — direct TCP to the editor plugin (port 13090).
   Used when ``--editor`` flag is set, mainly for testing.

Priority: serve TCP > ADB > editor TCP.
"""

from __future__ import annotations

import json
import os
import socket
import sys
from typing import Optional

from . import config, output
from .adb import DeviceBridgeManager


# --------------------------------------------------------------------------- #
# Base
# --------------------------------------------------------------------------- #

class Transport:
    """Abstract base for device communication."""

    name: str = "base"

    def send_command(self, command: str, params: dict | None = None,
                     timeout: float = 30.0) -> dict:
        raise NotImplementedError

    def is_available(self) -> bool:
        raise NotImplementedError

    def label(self) -> str:
        return self.name


# --------------------------------------------------------------------------- #
# TCP Proxy (through devbridge serve)
# --------------------------------------------------------------------------- #

class TCPProxyTransport(Transport):
    """Send commands through a running ``devbridge serve`` IPC port."""

    name = "tcp-proxy"

    def __init__(self, ipc_host: str = "127.0.0.1", ipc_port: int = 8060):
        self.ipc_host = ipc_host
        self.ipc_port = ipc_port

    def send_command(self, command: str, params: dict | None = None,
                     timeout: float = 30.0) -> dict:
        params = params or {}
        payload = json.dumps({"command": command, "params": params}) + "\n"

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((self.ipc_host, self.ipc_port))
            sock.sendall(payload.encode("utf-8"))

            chunks: list[bytes] = []
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                if b"\n" in b"".join(chunks):
                    break

            raw = b"".join(chunks).split(b"\n")[0]
            return json.loads(raw)
        except ConnectionRefusedError:
            return {"success": False, "error": "devbridge serve not running (connection refused on IPC port)"}
        except socket.timeout:
            return {"success": False, "error": f"Timeout ({timeout}s) waiting for serve response"}
        except Exception as e:
            return {"success": False, "error": f"IPC error: {e}"}
        finally:
            sock.close()

    def is_available(self) -> bool:
        """Check if serve IPC port is accepting connections."""
        try:
            resp = self.send_command("ping", timeout=3.0)
            return resp.get("success", False)
        except Exception:
            return False

    def label(self) -> str:
        return f"tcp-proxy@{self.ipc_host}:{self.ipc_port}"


# --------------------------------------------------------------------------- #
# ADB (original)
# --------------------------------------------------------------------------- #

class ADBTransport(Transport):
    """Send commands via ADB broadcast (fire-and-forget)."""

    name = "adb"

    def __init__(self, mgr: DeviceBridgeManager, device_id: str):
        self.mgr = mgr
        self.device_id = device_id

    def send_command(self, command: str, params: dict | None = None,
                     timeout: float = 30.0) -> dict:
        params = params or {}
        # Map generic commands to DeviceBridgeManager methods
        if command == "ping":
            return {"success": True, "message": "pong (adb)"}
        elif command == "exec_console":
            return self.mgr.exec_console(params.get("command", ""), device_id=self.device_id, timeout=timeout)
        elif command == "exec_unlua":
            return self.mgr.exec_unlua(params.get("code", ""), device_id=self.device_id, timeout=timeout)
        elif command == "set_cvar":
            return self.mgr.set_cvar(params.get("name", ""), params.get("value", ""), device_id=self.device_id)
        elif command == "get_cvar":
            # ADB can't read CVars directly — route through exec_unlua
            return {"success": False, "error": "get_cvar not supported over ADB (use serve TCP mode)"}
        elif command == "get_log":
            return self.mgr.get_log(
                lines=int(params.get("count", 200)),
                filter_expr=params.get("filter_expr", ""),
                text_filter=params.get("filter", params.get("text_filter", "")),
                device_id=self.device_id,
            )
        elif command == "get_info":
            return self.mgr.device_info(device_id=self.device_id)
        else:
            return {"success": False, "error": f"Unknown command for ADB transport: {command}"}

    def is_available(self) -> bool:
        try:
            devices = self.mgr.list_devices()
            return any(d.is_ready for d in devices)
        except Exception:
            return False

    def label(self) -> str:
        return f"adb@{self.device_id}"


# --------------------------------------------------------------------------- #
# Editor TCP (direct to editor plugin, for testing)
# --------------------------------------------------------------------------- #

class EditorTransport(Transport):
    """Direct TCP connection to the editor's UnrealEngineAIAssist plugin."""

    name = "editor"

    def __init__(self, host: str = "127.0.0.1", port: int = 13090):
        self.host = host
        self.port = port

    def send_command(self, command: str, params: dict | None = None,
                     timeout: float = 30.0) -> dict:
        params = params or {}
        payload = json.dumps({"command": command, "params": params}) + "\n"

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((self.host, self.port))
            sock.sendall(payload.encode("utf-8"))

            chunks: list[bytes] = []
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                if b"\n" in b"".join(chunks):
                    break

            raw = b"".join(chunks).split(b"\n")[0]
            return json.loads(raw)
        except ConnectionRefusedError:
            return {"success": False, "error": f"Editor not running on {self.host}:{self.port}"}
        except socket.timeout:
            return {"success": False, "error": f"Editor timeout ({timeout}s)"}
        except Exception as e:
            return {"success": False, "error": f"Editor connection error: {e}"}
        finally:
            sock.close()

    def is_available(self) -> bool:
        try:
            resp = self.send_command("ping", timeout=3.0)
            return resp.get("success", False)
        except Exception:
            return False

    def label(self) -> str:
        return f"editor@{self.host}:{self.port}"


# --------------------------------------------------------------------------- #
# Session file reading
# --------------------------------------------------------------------------- #

def _read_serve_session() -> dict | None:
    """Read serve_session.json left by a running ``devbridge serve``."""
    from .paths import plugin_root
    pdir = plugin_root()
    if not pdir:
        return None
    path = os.path.join(pdir, ".claude", "devbridge", "serve_session.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        # Verify the serve process is still alive
        pid = data.get("pid")
        if pid and not _pid_alive(pid):
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def _pid_alive(pid: int) -> bool:
    """Check if a process is still running (cross-platform)."""
    if sys.platform == "win32":
        # On Windows, os.kill(pid, 0) throws for valid processes too.
        # Use ctypes to call OpenProcess with PROCESS_QUERY_LIMITED_INFORMATION.
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


# --------------------------------------------------------------------------- #
# Auto-resolve
# --------------------------------------------------------------------------- #

def auto_resolve(ctx=None, explicit_device: str = "") -> Transport:
    """Pick the best available transport.

    Priority:
      1. TCP proxy (serve running + device connected) — best for WiFi/network
      2. ADB — USB-connected Android device
      3. Editor TCP — direct to editor (testing)

    If ctx has ``--editor`` flag, force editor transport.
    """
    # 1. Check serve session
    session = _read_serve_session()
    if session and session.get("device_connected"):
        ipc_port = session.get("ipc_port", 8060)
        transport = TCPProxyTransport(ipc_port=ipc_port)
        if transport.is_available():
            return transport

    # 2. Check ADB
    try:
        mgr = DeviceBridgeManager()
        default_dev = config.get("default_device", "")
        if default_dev:
            mgr.set_default_device(default_dev)
        dev = mgr.resolve_device(explicit_device or (ctx.obj.get("device", "") if ctx else ""))
        return ADBTransport(mgr, dev)
    except (ValueError, Exception):
        pass

    # 3. Check editor
    editor = EditorTransport()
    if editor.is_available():
        return editor

    # Nothing available
    return _FailTransport()


class _FailTransport(Transport):
    """Placeholder when no transport is available."""
    name = "none"

    def send_command(self, command: str, params: dict | None = None,
                     timeout: float = 30.0) -> dict:
        return {
            "success": False,
            "error": (
                "No device connection available. Options:\n"
                "  1. Run `devbridge serve` and connect a device via AIAssistDeviceBridge\n"
                "  2. Connect an Android device via USB\n"
                "  3. Start UE Editor for editor-mode testing"
            ),
        }

    def is_available(self) -> bool:
        return False
