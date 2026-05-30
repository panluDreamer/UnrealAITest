"""
Device Bridge — ADB-based communication with UE4 games running on Android devices.

Leverages UE4's built-in broadcast receiver: the engine registers a BroadcastReceiver
for android.intent.action.RUN that pipes the "cmd" extra through GEngine->Exec().
This means any UE console command — including UFUNCTION(Exec) functions like
ExecDoString — can be invoked remotely via:

    adb shell am broadcast -a android.intent.action.RUN -e cmd '<console_command>'

No custom C++ runtime module is needed.

Originally lived at Skills/ue-python-script/mcp_server/device_bridge.py; moved here
as part of the devbridge CLI refactor (MCP server no longer imports it).
"""

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# ADB path auto-detection
# ---------------------------------------------------------------------------

def _find_adb() -> str:
    """Find the adb executable. Checks ANDROID_HOME, PATH, common locations."""
    # 1. Explicit env override
    env_adb = os.environ.get("ADB_PATH", "").strip()
    if env_adb and os.path.isfile(env_adb):
        return env_adb

    # 2. ANDROID_HOME / ANDROID_SDK_ROOT
    for env_var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        sdk = os.environ.get(env_var, "").strip()
        if sdk:
            candidate = os.path.join(sdk, "platform-tools", "adb.exe" if os.name == "nt" else "adb")
            if os.path.isfile(candidate):
                return candidate

    # 3. On PATH
    adb_name = "adb.exe" if os.name == "nt" else "adb"
    found = shutil.which(adb_name)
    if found:
        return found

    # 4. Common Windows locations
    if os.name == "nt":
        for base in [
            os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk"),
            os.path.expandvars(r"%USERPROFILE%\AppData\Local\Android\Sdk"),
            r"C:\Android\sdk",
        ]:
            candidate = os.path.join(base, "platform-tools", "adb.exe")
            if os.path.isfile(candidate):
                return candidate

    return "adb"  # Fallback: hope it's on PATH


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DeviceInfo:
    """Represents a connected Android device."""
    device_id: str
    state: str = ""        # "device", "offline", "unauthorized", "no permissions"
    model: str = ""
    product: str = ""
    transport_id: str = ""

    @property
    def is_ready(self) -> bool:
        return self.state == "device"


@dataclass
class BroadcastResult:
    """Result of an ADB broadcast command."""
    success: bool
    raw_output: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# ADBWrapper
# ---------------------------------------------------------------------------

class ADBWrapper:
    """Wraps adb commands for Android device interaction."""

    def __init__(self, adb_path: str = ""):
        self.adb_path = adb_path or _find_adb()

    def _run(self, args: list[str], timeout: float = 15.0) -> tuple[str, str, int]:
        """Run an adb command. Returns (stdout, stderr, returncode)."""
        cmd = [self.adb_path] + args
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            return result.stdout, result.stderr, result.returncode
        except FileNotFoundError:
            return "", f"ADB not found at '{self.adb_path}'. Install Android SDK platform-tools or set ADB_PATH / ANDROID_HOME.", 1
        except subprocess.TimeoutExpired:
            return "", f"ADB command timed out ({timeout}s): {' '.join(cmd)}", 1

    def _run_for_device(self, device_id: str, args: list[str],
                        timeout: float = 15.0) -> tuple[str, str, int]:
        """Run an adb command targeting a specific device."""
        device_args = ["-s", device_id] if device_id else []
        return self._run(device_args + args, timeout=timeout)

    def version(self, timeout: float = 5.0) -> str:
        """Return the `adb version` first line, or empty string on failure."""
        stdout, _, rc = self._run(["version"], timeout=timeout)
        if rc != 0:
            return ""
        return stdout.splitlines()[0].strip() if stdout else ""

    # --- Device discovery ---

    def devices(self) -> list[DeviceInfo]:
        """List connected Android devices."""
        stdout, _, rc = self._run(["devices", "-l"])
        if rc != 0:
            return []

        devices: list[DeviceInfo] = []
        for line in stdout.strip().splitlines()[1:]:  # Skip "List of devices attached"
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue

            dev = DeviceInfo(device_id=parts[0], state=parts[1])

            # Parse key:value pairs like model:Pixel_7 product:panther transport_id:1
            for part in parts[2:]:
                if ":" in part:
                    key, _, val = part.partition(":")
                    if key == "model":
                        dev.model = val
                    elif key == "product":
                        dev.product = val
                    elif key == "transport_id":
                        dev.transport_id = val

            devices.append(dev)

        return devices

    # --- Console command via broadcast ---

    def send_broadcast(self, device_id: str, command: str,
                       timeout: float = 30.0) -> BroadcastResult:
        """Send a UE console command to the device via Android broadcast intent."""
        # Escape single quotes for the shell-wrapped payload
        escaped_cmd = command.replace("'", "'\\''")
        shell_cmd = f"am broadcast -a android.intent.action.RUN -e cmd '{escaped_cmd}'"

        stdout, stderr, rc = self._run_for_device(
            device_id, ["shell", shell_cmd], timeout=timeout
        )

        if rc != 0:
            return BroadcastResult(
                success=False,
                raw_output=stdout,
                error=stderr.strip() or f"adb shell failed with code {rc}",
            )

        output = (stdout + stderr).strip()
        success = "Broadcast completed" in output or rc == 0
        return BroadcastResult(success=success, raw_output=output)

    # --- Logcat ---

    def logcat(self, device_id: str, lines: int = 200,
               filter_expr: str = "", timeout: float = 30.0) -> tuple[str, str]:
        """Read recent logcat lines. Returns (output, error).

        filter_expr is appended verbatim (e.g. "-s UE4:V" or "-s LogTemp:V *:S").
        Also supports piping a `--pid=N` element in filter_expr.
        """
        args = ["logcat", "-d", "-t", str(lines)]
        if filter_expr:
            args.extend(filter_expr.split())

        stdout, stderr, rc = self._run_for_device(device_id, args, timeout=timeout)
        if rc != 0:
            return "", stderr.strip()
        return stdout, ""

    def logcat_clear(self, device_id: str) -> bool:
        """Clear the logcat buffer."""
        _, _, rc = self._run_for_device(device_id, ["logcat", "-c"], timeout=5.0)
        return rc == 0

    def logcat_buffer_sizes(self, device_id: str) -> str:
        """Return the raw output of `adb logcat -g` (ring buffer sizes)."""
        stdout, _, rc = self._run_for_device(device_id, ["logcat", "-g"], timeout=5.0)
        return stdout if rc == 0 else ""

    def logcat_set_buffer(self, device_id: str, size: str) -> bool:
        """Grow the main logcat ring buffer. `size` is e.g. "16M"."""
        _, _, rc = self._run_for_device(
            device_id, ["logcat", "-G", size], timeout=5.0
        )
        return rc == 0

    # --- Shell ---

    def shell(self, device_id: str, command: str,
              timeout: float = 15.0) -> tuple[str, str, int]:
        """Execute a shell command on device. Returns (stdout, stderr, returncode)."""
        return self._run_for_device(device_id, ["shell", command], timeout=timeout)

    # --- File operations ---

    def push(self, device_id: str, local_path: str,
             remote_path: str, timeout: float = 30.0) -> bool:
        _, _, rc = self._run_for_device(
            device_id, ["push", local_path, remote_path], timeout=timeout
        )
        return rc == 0

    def pull(self, device_id: str, remote_path: str,
             local_path: str, timeout: float = 30.0) -> bool:
        _, _, rc = self._run_for_device(
            device_id, ["pull", remote_path, local_path], timeout=timeout
        )
        return rc == 0

    # --- Screenshot ---

    def screencap(self, device_id: str, local_path: str,
                  timeout: float = 30.0) -> bool:
        """Capture a screenshot. Two-step (screencap+pull) with exec-out fallback."""
        remote_path = "/data/local/tmp/_screenshot.png"

        _, _, rc1 = self._run_for_device(
            device_id,
            ["shell", "screencap", "-p", remote_path],
            timeout=timeout,
        )
        if rc1 == 0:
            os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
            _, _, rc2 = self._run_for_device(
                device_id,
                ["pull", remote_path, local_path],
                timeout=timeout,
            )
            self._run_for_device(device_id, ["shell", "rm", "-f", remote_path], timeout=5)
            if rc2 == 0 and os.path.isfile(local_path) and os.path.getsize(local_path) > 100:
                return True

        # Fallback: exec-out pipe
        cmd = [self.adb_path]
        if device_id:
            cmd.extend(["-s", device_id])
        cmd.extend(["exec-out", "screencap", "-p"])
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=timeout)
            if result.returncode != 0 or not result.stdout or len(result.stdout) < 100:
                return False
            os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
            with open(local_path, "wb") as f:
                f.write(result.stdout)
            return True
        except (subprocess.TimeoutExpired, OSError):
            return False

    # --- Device info ---

    def getprop(self, device_id: str, prop: str = "", timeout: float = 10.0) -> str:
        """Read a system property (or all if prop is empty)."""
        args = ["shell", "getprop"]
        if prop:
            args.append(prop)
        stdout, _, rc = self._run_for_device(device_id, args, timeout=timeout)
        return stdout.strip() if rc == 0 else ""

    def pidof(self, device_id: str, package: str, timeout: float = 5.0) -> Optional[int]:
        """Return the PID of the given package, or None if not running."""
        stdout, _, rc = self._run_for_device(
            device_id, ["shell", "pidof", package], timeout=timeout
        )
        if rc != 0:
            return None
        txt = stdout.strip()
        if not txt:
            return None
        # pidof may return multiple PIDs separated by whitespace; take first.
        try:
            return int(txt.split()[0])
        except (ValueError, IndexError):
            return None


# ---------------------------------------------------------------------------
# DeviceBridgeManager
# ---------------------------------------------------------------------------

class DeviceBridgeManager:
    """Manages device discovery and provides high-level operations."""

    def __init__(self, output_dir: str = ""):
        self.adb = ADBWrapper()
        self._devices: dict[str, DeviceInfo] = {}
        self._default_device: str = ""
        self.output_dir = output_dir

    def set_output_dir(self, output_dir: str):
        self.output_dir = output_dir

    def set_default_device(self, device_id: str) -> None:
        """Explicitly set the preferred default device (honoured by resolve_device)."""
        self._default_device = device_id

    # --- Device management ---

    def list_devices(self) -> list[DeviceInfo]:
        """Discover all connected Android devices and cache the list."""
        devices = self.adb.devices()
        self._devices = {d.device_id: d for d in devices}

        ready = [d for d in devices if d.is_ready]
        if len(ready) == 1 and not self._default_device:
            self._default_device = ready[0].device_id
        elif self._default_device and self._default_device not in self._devices:
            self._default_device = ""  # Previous default disconnected

        return devices

    def resolve_device(self, device_id: str = "") -> str:
        """Resolve a device_id: provided > explicit default > auto-discover."""
        if device_id:
            return device_id

        if self._default_device:
            return self._default_device

        devices = self.list_devices()
        ready = [d for d in devices if d.is_ready]
        if not ready:
            if devices:
                states = ", ".join(f"{d.device_id}({d.state})" for d in devices)
                raise ValueError(
                    f"No ready Android devices. Found: {states}. "
                    "Check USB debugging is enabled and authorized."
                )
            raise ValueError(
                "No Android devices connected. "
                "Connect a device via USB and enable USB debugging."
            )
        if len(ready) > 1:
            ids = ", ".join(d.device_id for d in ready)
            raise ValueError(
                f"Multiple devices connected: {ids}. "
                "Pass -d/--device to choose one or run `devbridge use <id>`."
            )
        self._default_device = ready[0].device_id
        return self._default_device

    # --- High-level operations ---

    def exec_console(self, command: str, device_id: str = "",
                     timeout: float = 30.0) -> dict:
        """Execute a UE console command on device via am broadcast."""
        try:
            dev = self.resolve_device(device_id)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        result = self.adb.send_broadcast(dev, command, timeout=timeout)
        return {
            "success": result.success,
            "device_id": dev,
            "command": command,
            "broadcast_output": result.raw_output,
            "error": result.error if not result.success else "",
        }

    def exec_unlua(self, code: str, device_id: str = "",
                   timeout: float = 30.0) -> dict:
        """Execute UnLua code on device via ExecDoString. Fire-and-forget.

        To read the return value, call get_log() or use the higher-level
        `devbridge lua` command which does clear-before-send + grep RetVal.
        """
        console_cmd = f"ExecDoString {code}"

        try:
            dev = self.resolve_device(device_id)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        result = self.adb.send_broadcast(dev, console_cmd, timeout=timeout)
        return {
            "success": result.success,
            "device_id": dev,
            "code": code,
            "broadcast_output": result.raw_output,
            "error": result.error if not result.success else "",
        }

    def set_cvar(self, name: str, value: str, device_id: str = "") -> dict:
        """Set a CVar on device."""
        return self.exec_console(f"{name} {value}", device_id=device_id)

    def get_log(self, lines: int = 200, filter_expr: str = "",
                text_filter: str = "", device_id: str = "") -> dict:
        """Read logcat from device.

        Large output (>2000 chars) is dumped to self.output_dir if set.
        """
        try:
            dev = self.resolve_device(device_id)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        output, error = self.adb.logcat(dev, lines=lines, filter_expr=filter_expr)
        if error:
            return {"success": False, "error": error, "device_id": dev}

        if text_filter and output:
            filtered_lines = [
                line for line in output.splitlines()
                if text_filter.lower() in line.lower()
            ]
            output = "\n".join(filtered_lines)

        all_lines = output.splitlines()
        total_lines = len(all_lines)

        if len(output) > 2000 and self.output_dir:
            os.makedirs(self.output_dir, exist_ok=True)
            ts = int(time.time())
            filename = f"device_log_{dev}_{ts}.txt"
            filepath = os.path.join(self.output_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(output)

            summary_lines = all_lines[:10] + ["..."] + all_lines[-5:] if total_lines > 15 else all_lines
            return {
                "success": True,
                "device_id": dev,
                "total_lines": total_lines,
                "log_summary": "\n".join(summary_lines),
                "log_file_path": filepath,
                "hint": f"Full log ({total_lines} lines) at: {filepath}",
            }

        return {
            "success": True,
            "device_id": dev,
            "total_lines": total_lines,
            "log_output": output,
        }

    def screenshot(self, device_id: str = "", out_path: str = "") -> dict:
        """Capture a screenshot from device.

        If out_path is given, use it. Else save under self.output_dir with a
        timestamped filename.
        """
        try:
            dev = self.resolve_device(device_id)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        if out_path:
            filepath = os.path.abspath(out_path)
        else:
            if not self.output_dir:
                return {"success": False, "error": "Output directory not configured"}
            os.makedirs(self.output_dir, exist_ok=True)
            ts = int(time.time())
            filepath = os.path.join(self.output_dir, f"device_screenshot_{dev}_{ts}.png")

        ok = self.adb.screencap(dev, filepath)
        if not ok:
            return {
                "success": False,
                "error": "Screenshot capture failed. Is the device connected and screen on?",
                "device_id": dev,
            }

        return {
            "success": True,
            "device_id": dev,
            "file_path": filepath,
        }

    def device_info(self, device_id: str = "") -> dict:
        """Get device information (model, OS, screen, GPU, etc.)."""
        try:
            dev = self.resolve_device(device_id)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        adb = self.adb
        info = {
            "success": True,
            "device_id": dev,
            "model": adb.getprop(dev, "ro.product.model"),
            "manufacturer": adb.getprop(dev, "ro.product.manufacturer"),
            "android_version": adb.getprop(dev, "ro.build.version.release"),
            "sdk_version": adb.getprop(dev, "ro.build.version.sdk"),
            "build_fingerprint": adb.getprop(dev, "ro.build.fingerprint"),
            "cpu_abi": adb.getprop(dev, "ro.product.cpu.abi"),
            "gpu_renderer": "",
            "screen_resolution": "",
            "screen_density": adb.getprop(dev, "ro.sf.lcd_density"),
        }

        gpu_out, _, _ = adb.shell(dev, "dumpsys SurfaceFlinger | grep GLES")
        if gpu_out:
            info["gpu_renderer"] = gpu_out.strip()

        size_out, _, _ = adb.shell(dev, "wm size")
        if size_out:
            info["screen_resolution"] = size_out.strip()

        return info
