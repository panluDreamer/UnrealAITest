#!/usr/bin/env python3
"""
MCP server that bridges AI agents to the UnrealAgentBridge C++ TCP plugin.

Five tools: exec_python, describe_object, generate_catalog, get_log, reflect.
Large responses (describe_object, get_log, reflect describe) are dumped to files
to avoid filling the AI context window. The agent can then use Read/Grep to inspect.
"""

import json
import os
import re
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from mcp.server.fastmcp import FastMCP

HOST = os.environ.get("AGENT_BRIDGE_HOST", "127.0.0.1")
PORT = int(os.environ.get("AGENT_BRIDGE_PORT", "13090"))

# Output directory for dumped responses
# The plugin root is the parent of Skills/ue-python-script/mcp_server/
def _find_plugin_dir() -> str:
    """Find the plugin root directory (where plugin.config.json lives)."""
    env = os.environ.get("AGENT_BRIDGE_PLUGIN_DIR", "").strip()
    if env:
        return env
    # Walk up: mcp_server -> ue-python-script -> Skills -> PluginDir
    return str(Path(__file__).resolve().parents[2])

_PLUGIN_DIR = _find_plugin_dir()
_AGENT_DIR = os.environ.get("AGENT_DIR_NAME", ".claude")
OUTPUT_DIR = os.path.join(_PLUGIN_DIR, _AGENT_DIR, "mcp_output")

mcp = FastMCP("unreal-agent-bridge")


def _ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def _send(command: str, params: dict) -> dict:
    """Send a command to UnrealAgentBridge and return the parsed response."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(120)
    try:
        sock.connect((HOST, PORT))
        payload = json.dumps({"command": command, "params": params}).encode("utf-8") + b"\n"
        sock.sendall(payload)

        # Receive until newline
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
        return {
            "success": False,
            "error": (
                f"Cannot connect to UnrealAgentBridge on {HOST}:{PORT}. "
                "Ensure the Unreal Editor is running with the UnrealAgentBridge plugin enabled."
            ),
        }
    except socket.timeout:
        return {"success": False, "error": "Request timed out (120s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        sock.close()


def _dump_json(filename: str, data: dict) -> str:
    """Write data as pretty JSON to OUTPUT_DIR/{filename}, return the full path."""
    _ensure_output_dir()
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def _dump_text(filename: str, text: str) -> str:
    """Write plain text to OUTPUT_DIR/{filename}, return the full path."""
    _ensure_output_dir()
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


# ---------------------------------------------------------------------------
# Script History (ScriptMemory)
# ---------------------------------------------------------------------------

SCRIPT_HISTORY_DIR = os.path.join(OUTPUT_DIR, "script_history")
SCRIPT_HISTORY_INDEX = os.path.join(SCRIPT_HISTORY_DIR, "index.json")
# Keep at most this many entries in the index (oldest are pruned on write).
SCRIPT_HISTORY_MAX_ENTRIES = 200


def _slugify(text: str, max_len: int = 50) -> str:
    """Turn a summary string into a safe filename slug."""
    slug = re.sub(r"[^a-zA-Z0-9_\- ]+", "", text).strip().replace(" ", "_")
    return slug[:max_len] if slug else "script"


def _save_script_history(code: str, summary: str, success: bool,
                         result: str = "", output_preview: str = "") -> str | None:
    """Save a successful exec_python call to script_history/. Returns the file path."""
    os.makedirs(SCRIPT_HISTORY_DIR, exist_ok=True)

    now = datetime.now(timezone.utc)
    ts_file = now.strftime("%Y%m%d_%H%M%S")
    ts_iso = now.isoformat()
    slug = _slugify(summary)
    filename = f"{ts_file}_{slug}.py"
    filepath = os.path.join(SCRIPT_HISTORY_DIR, filename)

    # Write the script file with metadata header
    header_lines = [
        f"# Summary: {summary}",
        f"# Timestamp: {ts_iso}",
        f"# Result: {'success' if success else 'failed'}",
    ]
    if result:
        # Truncate long result to one line
        result_oneline = result.replace("\n", " ")[:200]
        header_lines.append(f"# Return: {result_oneline}")
    if output_preview:
        preview_oneline = output_preview.replace("\n", " | ")[:200]
        header_lines.append(f"# Output: {preview_oneline}")
    header_lines.append("# ---")

    file_content = "\n".join(header_lines) + "\n" + code + "\n"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(file_content)

    # Update index.json
    index = []
    if os.path.exists(SCRIPT_HISTORY_INDEX):
        try:
            with open(SCRIPT_HISTORY_INDEX, "r", encoding="utf-8") as f:
                index = json.load(f)
        except (json.JSONDecodeError, OSError):
            index = []

    index.append({
        "summary": summary,
        "timestamp": ts_iso,
        "file": filename,
        "success": success,
    })

    # Prune oldest if over limit
    if len(index) > SCRIPT_HISTORY_MAX_ENTRIES:
        index = index[-SCRIPT_HISTORY_MAX_ENTRIES:]

    with open(SCRIPT_HISTORY_INDEX, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return filepath


# Threshold for auto-dumping exec_python output to file (in characters).
# Below this, log_output is returned inline. Above, it's dumped and a summary + file_path is returned.
EXEC_OUTPUT_DUMP_THRESHOLD = 2000
# Max lines to include in the inline summary when output is dumped to file.
EXEC_OUTPUT_SUMMARY_LINES = 15


@mcp.tool()
def exec_python(code: str, summary: str = "") -> dict:
    """Execute Python code in the running Unreal Editor's Python environment.

    Single expressions are auto-detected and evaluated for a return value.
    Multi-line scripts, imports, and control flow use file-execution mode.

    For short output, the full log_output is returned inline.
    For long output (>2000 chars), log_output is dumped to a file and
    a summary (first/last lines) + file_path is returned to save context tokens.
    Use Read/Grep on the file_path to inspect the full output.

    Successful executions are saved to script_history/ for future reference.
    Read script_history/index.json to browse past scripts.

    Args:
        code: Python code to execute. Can be a single expression or multi-line script.
        summary: Optional one-line description of what this script does
                 (e.g. "Spawn 10 chairs in a 2x5 grid"). Saved to script history
                 for future discovery. If omitted, the first 80 chars of code are used.

    Returns:
        dict with 'success', 'result' (expression value), and 'log_output' (print/warnings).
        When output is large: 'log_output' is replaced by 'log_summary', 'log_file_path', and 'log_total_lines'.
    """
    resp = _send("exec_python", {"code": code})

    # --- Script History: save successful executions ---
    if resp.get("success"):
        effective_summary = summary.strip() if summary else ""
        if not effective_summary:
            # Fallback: first meaningful line of code, truncated
            for line in code.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and not stripped.startswith("import "):
                    effective_summary = stripped[:80]
                    break
            if not effective_summary:
                effective_summary = code.strip()[:80]

        # Collect output preview for the history header
        log_entries = resp.get("log_output", [])
        output_lines = []
        for entry in log_entries:
            if isinstance(entry, dict):
                output_lines.append(entry.get("output", ""))
            else:
                output_lines.append(str(entry))
        output_preview = "\n".join(output_lines[:5])

        _save_script_history(
            code=code,
            summary=effective_summary,
            success=True,
            result=resp.get("result", ""),
            output_preview=output_preview,
        )

    # --- Output size handling (unchanged logic) ---
    if not resp.get("success"):
        return resp

    # Measure total output size
    log_entries = resp.get("log_output", [])
    total_text = ""
    for entry in log_entries:
        if isinstance(entry, dict):
            total_text += entry.get("output", "") + "\n"
        else:
            total_text += str(entry) + "\n"

    if len(total_text) <= EXEC_OUTPUT_DUMP_THRESHOLD:
        return resp  # Short output — return as-is

    # Long output — dump to file, return summary
    timestamp = int(time.time())
    filename = f"exec_python_{timestamp}.txt"
    file_path = _dump_text(filename, total_text)

    # Build summary: first N lines + last N lines
    all_lines = total_text.splitlines()
    half = EXEC_OUTPUT_SUMMARY_LINES // 2
    if len(all_lines) <= EXEC_OUTPUT_SUMMARY_LINES:
        summary_lines = all_lines
    else:
        summary_lines = (
            all_lines[:half]
            + [f"... ({len(all_lines) - EXEC_OUTPUT_SUMMARY_LINES} lines omitted) ..."]
            + all_lines[-half:]
        )

    return {
        "success": resp.get("success"),
        "result": resp.get("result"),
        "log_summary": "\n".join(summary_lines),
        "log_total_lines": len(all_lines),
        "log_total_chars": len(total_text),
        "log_file_path": file_path,
        "hint": f"Full output ({len(all_lines)} lines) at: {file_path}",
    }


@mcp.tool()
def describe_object(class_name: str) -> dict:
    """Get live UHT reflection data for a UClass: all BlueprintCallable functions and properties.

    Accepts a class name (e.g. "Actor", "EditorAssetLibrary") or a full object path.
    Automatically tries U- and A- prefixes if the exact name is not found.

    The full response is dumped to a JSON file to save context tokens.
    Use Read/Grep on the returned file_path to find specific functions.

    Args:
        class_name: The UClass name or object path to introspect.

    Returns:
        dict with summary (class_name, parent_class, function_count, property_count, file_path).
        Full data is at file_path — use Grep to search for specific functions.
    """
    resp = _send("describe_object", {"object_path": class_name})
    if not resp.get("success"):
        return resp

    # Dump full response to file
    safe_name = class_name.replace("/", "_").replace(".", "_").replace(":", "_")
    filename = f"describe_object_{safe_name}.json"
    file_path = _dump_json(filename, resp)

    # Build compact summary with first few function names as preview
    functions = resp.get("functions", [])
    properties = resp.get("properties", [])
    func_names = [f.get("python_name", f.get("name", "?")) for f in functions[:10]]
    preview_suffix = "..." if len(functions) > 10 else ""

    return {
        "success": True,
        "class_name": resp.get("class_name"),
        "python_class": resp.get("python_class"),
        "parent_class": resp.get("parent_class"),
        "function_count": resp.get("function_count", len(functions)),
        "property_count": resp.get("property_count", len(properties)),
        "function_preview": func_names,
        "preview_note": f"Showing first 10 of {len(functions)} functions{preview_suffix}",
        "file_path": file_path,
        "hint": f"Use Grep to search: Grep(pattern='your_keyword', path='{file_path}')",
    }


@mcp.tool()
def generate_catalog(output_dir: str = "") -> dict:
    """Generate or refresh the callable function catalog JSON files.

    Scans all loaded UClasses via UHT reflection, filters to BlueprintCallable functions,
    and writes:
      - catalog_index.json  (category index + class index)
      - classes/*.json      (per-class function signatures)

    Args:
        output_dir: Optional output directory. Defaults to .{agent}/callable_catalog/

    Returns:
        dict with success, output_dir, total_classes, total_functions.
    """
    return _send("generate_catalog", {"output_dir": output_dir})


@mcp.tool()
def get_log(count: int = 100, category: str = "", verbosity: str = "", filter: str = "") -> dict:
    """Retrieve recent Unreal Editor log lines.

    Reads from a ring buffer of the last 500 log entries captured since plugin startup.
    Useful for checking material compile errors, asset import warnings, Python script output, etc.

    The full log is dumped to a text file. A summary with error/warning counts and
    the most recent errors is returned inline to save context tokens.

    Args:
        count: Number of log entries to retrieve (default 100, max 500).
        category: Filter by log category substring (e.g. "Material", "Python", "LogTemp").
        verbosity: Filter by verbosity level: "info", "warning", or "error".
        filter: Filter by message text substring (case-sensitive).

    Returns:
        dict with summary (total, error_count, warning_count, recent_errors, file_path).
        Full log at file_path — use Read/Grep to inspect.
    """
    params = {"count": count}
    if category:
        params["category"] = category
    if verbosity:
        params["verbosity"] = verbosity
    if filter:
        params["filter"] = filter

    resp = _send("get_log", params)
    if not resp.get("success"):
        return resp

    entries = resp.get("entries", [])

    # Format as human-readable text for the dump file
    lines = []
    errors = []
    warnings = []
    for e in entries:
        verb = e.get("verbosity", "info")
        cat = e.get("category", "")
        msg = e.get("message", "")
        prefix = {"error": "ERR", "warning": "WRN"}.get(verb, "   ")
        line = f"[{prefix}] [{cat}] {msg}"
        lines.append(line)
        if verb == "error":
            errors.append(f"[{cat}] {msg}")
        elif verb == "warning":
            warnings.append(f"[{cat}] {msg}")

    # Dump to file
    timestamp = int(time.time())
    filter_tag = f"_{category}" if category else ""
    filter_tag += f"_{verbosity}" if verbosity else ""
    filename = f"log{filter_tag}_{timestamp}.txt"
    file_path = _dump_text(filename, "\n".join(lines))

    # Return compact summary
    recent_errors = errors[-5:]  # last 5 errors inline
    recent_warnings = warnings[-3:]  # last 3 warnings inline

    return {
        "success": True,
        "total_entries": len(entries),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "info_count": len(entries) - len(errors) - len(warnings),
        "recent_errors": recent_errors if recent_errors else ["(none)"],
        "recent_warnings": recent_warnings if recent_warnings else ["(none)"],
        "file_path": file_path,
        "hint": f"Full log at: {file_path}",
    }


@mcp.tool()
def reflect(action: str, object: str = "", property: str = "",
            value: str = "", class_name: str = "") -> dict:
    """Raw property access bypassing UE permission gates via ImportText/ExportTextItem.

    Three actions:
      - get: Read any property value (including non-BlueprintVisible).
      - set: Write any property value (bypasses BlueprintReadOnly, EditConst, etc.).
      - describe: List ALL properties and functions of a class (no BlueprintVisible filter).

    For get/set, provide 'object' (UObject path) and 'property' (dot-separated path).
    For describe, provide 'class_name'.

    Value format follows Unreal Text Serialization:
      - Primitives: "42", "3.14", "true", "Hello World"
      - Object refs: full object path string
      - Structs: "(X=1.0,Y=2.0,Z=3.0)"
      - Enums: "EnumValue"

    Args:
        action: "get", "set", or "describe".
        object: UObject path for get/set (e.g. "/Game/UI/WBP.WBP:WidgetTree").
        property: Dot-separated property path for get/set (e.g. "RootWidget" or "Nested.Prop").
        value: New value string for set action (Unreal text serialization format).
        class_name: UClass name for describe action (e.g. "WidgetTree").

    Returns:
        get: {success, value, type}
        set: {success, previous_value, new_value, warning}
        describe: {success, class_name, total_properties, reflect_only_property_names, file_path}
    """
    params: dict = {"action": action}
    if action in ("get", "set"):
        if object:
            params["object"] = object
        if property:
            params["property"] = property
        if action == "set" and value:
            params["value"] = value
    elif action == "describe":
        if class_name:
            params["class_name"] = class_name

    resp = _send("reflect", params)
    if not resp.get("success"):
        return resp

    if action == "describe":
        # File was already dumped by C++ side; return summary with file_path
        return {
            "success": True,
            "class_name": resp.get("class_name"),
            "parent_class": resp.get("parent_class"),
            "total_properties": resp.get("total_properties"),
            "python_accessible_properties": resp.get("python_accessible_properties"),
            "reflect_only_properties": resp.get("reflect_only_properties"),
            "total_functions": resp.get("total_functions"),
            "python_callable_functions": resp.get("python_callable_functions"),
            "call_method_only_functions": resp.get("call_method_only_functions"),
            "reflect_only_property_names": resp.get("reflect_only_property_names", []),
            "file_path": resp.get("file_path"),
            "hint": f"Use Grep to search: Grep(pattern='your_keyword', path='{resp.get('file_path')}')",
        }

    # get/set: return response as-is
    return resp


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
