#!/usr/bin/env python3
"""
UnrealEngineAIAssist — Cross-platform installation script.

All AI client directories (.claude, .codebuddy, etc.) are created inside the
plugin's own root directory, fully decoupled from the Engine path.  The C++
plugin writes plugin.config.json on editor startup; this script reads it to
locate the engine directory when needed.

Usage:
    python setup.py                          # Auto-detect client, install
    python setup.py --client claude          # Explicit client
    python setup.py --client codebuddy       # For Codebuddy
    python setup.py --check                  # Verify installation
    python setup.py --uninstall              # Remove symlinks + generated configs
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLUGIN_DIR = Path(__file__).resolve().parent

def discover_skills() -> list[str]:
    """Auto-discover skills by scanning Skills/ directory for subdirs with SKILL.md."""
    skills_dir = PLUGIN_DIR / "Skills"
    skills = []
    if skills_dir.is_dir():
        for child in sorted(skills_dir.iterdir()):
            if child.is_dir() and (child / "SKILL.md").exists():
                skills.append(child.name)
    return skills


def discover_agents() -> list[str]:
    """Auto-discover agents by scanning Agents/ directory for subdirs with SKILL.md."""
    agents_dir = PLUGIN_DIR / "Agents"
    agents = []
    if agents_dir.is_dir():
        for child in sorted(agents_dir.iterdir()):
            if child.is_dir() and (child / "SKILL.md").exists():
                agents.append(child.name)
    return agents


SKILLS = discover_skills()
AGENTS = discover_agents()

CLIENT_MAP = {
    "claude": ".claude",
}

MCP_SERVER_DIR = PLUGIN_DIR / "Skills" / "ue-python-script" / "mcp_server"
MCP_SCRIPT = "unreal_agent_bridge_mcp.py"

# Permissions to merge into settings.local.json
REQUIRED_PERMISSIONS = [
    "mcp__unreal-agent-bridge__exec_python",
    "mcp__unreal-agent-bridge__describe_object",
    "mcp__unreal-agent-bridge__reflect",
    "mcp__unreal-agent-bridge__get_log",
    "mcp__unreal-agent-bridge__generate_catalog",
    "Skill(ue-knowledge-reader)",
    "Bash(rdc:*)",      # RenderDoc CLI commands (rdc-cli)
    "Bash(devbridge:*)",   # Device-debugging CLI (devbridge-cli)
]


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def read_plugin_config() -> dict:
    """Read plugin.config.json (written by C++ plugin on editor startup)."""
    config_path = PLUGIN_DIR / "plugin.config.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def get_engine_dir() -> Path | None:
    """Get engine_dir from plugin.config.json, or None if unavailable."""
    config = read_plugin_config()
    engine_dir = config.get("engine_dir", "")
    if engine_dir:
        return Path(engine_dir)
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_windows():
    return platform.system() == "Windows"


def auto_detect_client() -> str | None:
    """Scan PluginDir/ for existing .{client} directories."""
    for name, dotdir in CLIENT_MAP.items():
        if (PLUGIN_DIR / dotdir).is_dir():
            return name
    return None


def create_link(src: Path, dst: Path) -> str:
    """Create a symlink or junction. Returns the method used."""
    if dst.exists() or dst.is_symlink():
        # Check if it already points to the right place
        try:
            if dst.resolve() == src.resolve():
                return "exists"
        except (OSError, ValueError):
            pass
        # Remove stale link
        if dst.is_symlink() or dst.is_junction() if hasattr(dst, 'is_junction') else False:
            dst.unlink()
        elif dst.is_dir():
            shutil.rmtree(dst)
        elif dst.is_file():
            dst.unlink()

    is_dir = src.is_dir()

    if is_windows():
        if is_dir:
            # Try junction first (no admin needed) for directories
            try:
                subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(dst), str(src)],
                    check=True, capture_output=True,
                )
                return "junction"
            except subprocess.CalledProcessError:
                pass
            # Try symlink (may need admin or Developer Mode)
            try:
                dst.symlink_to(src, target_is_directory=True)
                return "symlink"
            except OSError:
                pass
            # Fallback: copy
            shutil.copytree(src, dst)
            return "copy"
        else:
            # File: try symlink, then copy
            try:
                dst.symlink_to(src, target_is_directory=False)
                return "symlink"
            except OSError:
                pass
            shutil.copy2(src, dst)
            return "copy"
    else:
        try:
            dst.symlink_to(src)
            return "symlink"
        except OSError:
            shutil.copytree(src, dst)
            return "copy"


def remove_link(path: Path):
    """Remove a symlink, junction, or directory."""
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink():
        path.unlink()
    elif is_windows():
        # Could be a junction
        try:
            subprocess.run(
                ["cmd", "/c", "rmdir", str(path)],
                check=True, capture_output=True,
            )
        except subprocess.CalledProcessError:
            shutil.rmtree(path, ignore_errors=True)
    elif path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def find_python_in_venv(venv_dir: Path) -> Path | None:
    """Find the python executable in a venv."""
    if is_windows():
        p = venv_dir / "Scripts" / "python.exe"
    else:
        p = venv_dir / "bin" / "python"
    return p if p.exists() else None


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

def install(client: str, port: int = 13090):
    agent_dir = CLIENT_MAP[client]
    agent_path = PLUGIN_DIR / agent_dir          # e.g. PluginDir/.claude
    skills_path = agent_path / "skills"

    print(f"UnrealEngineAIAssist Setup")
    print(f"  Plugin:  {PLUGIN_DIR}")
    print(f"  Client:  {client} ({agent_dir})")
    engine_dir = get_engine_dir()
    if engine_dir:
        print(f"  Engine:  {engine_dir}  (from plugin.config.json)")
    else:
        print(f"  Engine:  (unknown — start the editor to generate plugin.config.json)")
    print()

    # 1. Create skills directory
    skills_path.mkdir(parents=True, exist_ok=True)

    # 2. Create symlinks for each skill
    print("Creating skill links...")
    for skill in SKILLS:
        src = PLUGIN_DIR / "Skills" / skill
        dst = skills_path / skill
        method = create_link(src, dst)
        status = "OK" if method not in ("copy",) else "WARN (copied, not linked)"
        print(f"  {skill}: {status} [{method}]")

    # 2b. Create agent links
    print("\nCreating agent links...")
    agents_path = agent_path / "agents"
    agents_path.mkdir(parents=True, exist_ok=True)

    # Link shared RULE.md
    src = PLUGIN_DIR / "Agents" / "RULE.md"
    dst = agents_path / "RULE.md"
    if src.exists():
        method = create_link(src, dst)
        print(f"  RULE.md: OK [{method}]")

    # Link each agent directory
    for agent_name in AGENTS:
        src = PLUGIN_DIR / "Agents" / agent_name
        dst = agents_path / agent_name
        if src.exists():
            method = create_link(src, dst)
            status = "OK" if method not in ("copy",) else "WARN (copied, not linked)"
            print(f"  {agent_name}: {status} [{method}]")
        else:
            print(f"  {agent_name}: SKIP (source not found)")

    # 3. Install Python venv + dependencies
    print("\nSetting up Python environment...")
    venv_dir = MCP_SERVER_DIR / ".venv"
    if not venv_dir.exists():
        # Try uv first, then fall back to venv
        try:
            subprocess.run(
                ["uv", "venv", str(venv_dir)],
                check=True, capture_output=True,
            )
            print("  Created venv with uv")
        except (subprocess.CalledProcessError, FileNotFoundError):
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                check=True,
            )
            print("  Created venv with python -m venv")

    # Install deps
    python = find_python_in_venv(venv_dir)
    if python:
        try:
            subprocess.run(
                ["uv", "sync", "--directory", str(MCP_SERVER_DIR)],
                check=True, capture_output=True,
            )
            print("  Installed dependencies with uv sync")
        except (subprocess.CalledProcessError, FileNotFoundError):
            subprocess.run(
                [str(python), "-m", "pip", "install", "mcp[cli]>=1.4.1"],
                check=True, capture_output=True,
            )
            print("  Installed dependencies with pip")
    else:
        print("  WARN Could not find Python in venv, skip dependency install")

    # 4. Generate/merge .mcp.json inside the plugin directory
    print("\nConfiguring MCP server...")
    mcp_json_path = PLUGIN_DIR / ".mcp.json"

    # Build the server config using bundled uvx.exe (relative to PLUGIN_DIR)
    uvx_path = MCP_SERVER_DIR / "uvx.exe" if is_windows() else MCP_SERVER_DIR / "uvx"

    def to_rel(p: Path) -> str:
        """Return forward-slash relative path from PLUGIN_DIR; fall back to absolute."""
        try:
            return p.relative_to(PLUGIN_DIR).as_posix()
        except ValueError:
            return p.as_posix()

    server_config = {
        "command": to_rel(uvx_path),
        "args": [
            "--from", to_rel(MCP_SERVER_DIR),
            "unreal-agent-bridge-mcp",
        ],
        "env": {
            "AGENT_BRIDGE_PORT": str(port),
            "AGENT_DIR_NAME": agent_dir,
        },
    }

    if mcp_json_path.exists():
        with open(mcp_json_path, "r", encoding="utf-8") as f:
            mcp_data = json.load(f)
    else:
        mcp_data = {}

    if "mcpServers" not in mcp_data:
        mcp_data["mcpServers"] = {}

    mcp_data["mcpServers"]["unreal-agent-bridge"] = server_config

    with open(mcp_json_path, "w", encoding="utf-8") as f:
        json.dump(mcp_data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"  Written: {mcp_json_path}")

    # 5. Merge settings.local.json
    print("\nMerging settings...")
    settings_path = agent_path / "settings.local.json"
    if settings_path.exists():
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    else:
        settings = {}

    if "permissions" not in settings:
        settings["permissions"] = {}
    if "allow" not in settings["permissions"]:
        settings["permissions"]["allow"] = []

    allow_list = settings["permissions"]["allow"]
    added = []
    for perm in REQUIRED_PERMISSIONS:
        if perm not in allow_list:
            allow_list.append(perm)
            added.append(perm)

    # Enable MCP server
    if "enableAllProjectMcpServers" not in settings:
        settings["enableAllProjectMcpServers"] = True
    if "enabledMcpjsonServers" not in settings:
        settings["enabledMcpjsonServers"] = []
    if "unreal-agent-bridge" not in settings["enabledMcpjsonServers"]:
        settings["enabledMcpjsonServers"].append("unreal-agent-bridge")

    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write("\n")

    if added:
        print(f"  Added {len(added)} permissions to {settings_path}")
    else:
        print(f"  Permissions already up to date")

    # 6. Create knowledge directory & reuse existing catalog
    knowledge_path = PLUGIN_DIR / "Knowledge"
    knowledge_path.mkdir(parents=True, exist_ok=True)

    # callable_catalog stays per-client
    catalog_dst = agent_path / "callable_catalog"
    if not catalog_dst.exists():
        # Try to reuse callable_catalog from another client if available
        for other_dotdir in CLIENT_MAP.values():
            if other_dotdir == agent_dir:
                continue
            other_catalog = PLUGIN_DIR / other_dotdir / "callable_catalog"
            if other_catalog.is_dir() and (other_catalog / "catalog_index.json").exists():
                method = create_link(other_catalog, catalog_dst)
                print(f"\n  Reused callable_catalog from {other_dotdir} [{method}]")
                break
        else:
            # Also check legacy location (inside old knowledge dirs)
            for other_dotdir in CLIENT_MAP.values():
                other_catalog = PLUGIN_DIR / other_dotdir / "knowledge" / "callable_catalog"
                if other_catalog.is_dir() and (other_catalog / "catalog_index.json").exists():
                    method = create_link(other_catalog, catalog_dst)
                    print(f"\n  Reused callable_catalog from {other_dotdir}/knowledge/ [{method}]")
                    break
            else:
                print(f"\n  No existing callable_catalog found — run generate_catalog later")
    else:
        print(f"\n  callable_catalog already exists")

    print(f"\n{'='*60}")
    print("OK Installation complete!")
    print(f"\nNext steps:")
    print(f"  1. Regenerate project files and rebuild the editor")
    print(f"  2. Verify editor log: 'UnrealEngineAIAssist: Listening on 127.0.0.1:{port}'")
    print(f"  3. (Optional) Run /ue-knowledge-init to generate the knowledge graph")
    print(f"\nRun 'python setup.py --check' to verify installation")


# ---------------------------------------------------------------------------
# Check
# ---------------------------------------------------------------------------

def check(client: str):
    agent_dir = CLIENT_MAP[client]
    agent_path = PLUGIN_DIR / agent_dir
    skills_path = agent_path / "skills"
    all_ok = True

    print(f"UnrealEngineAIAssist Installation Check")
    print(f"  Plugin: {PLUGIN_DIR}")
    print(f"  Client: {client} ({agent_dir})")
    engine_dir = get_engine_dir()
    if engine_dir:
        print(f"  Engine: {engine_dir}")
    else:
        print(f"  Engine: (plugin.config.json not found — start the editor first)")
    print()

    # Check plugin.config.json
    print("Plugin config:")
    config_path = PLUGIN_DIR / "plugin.config.json"
    if config_path.exists():
        config = read_plugin_config()
        print(f"  plugin.config.json: OK (engine_dir={config.get('engine_dir', '?')})")
    else:
        print(f"  plugin.config.json: WARN missing (start editor to auto-generate)")

    # Check skills
    print("\nSkills:")
    for skill in SKILLS:
        dst = skills_path / skill
        if dst.exists():
            skill_md = dst / "SKILL.md"
            ok = skill_md.exists()
            status = "OK" if ok else "WARN link exists but SKILL.md missing"
        else:
            ok = False
            status = "FAIL missing"
        if not ok:
            all_ok = False
        print(f"  {skill}: {status}")

    # Check agents
    print("\nAgents:")
    agents_path = agent_path / "agents"
    rule_md = agents_path / "RULE.md"
    if rule_md.exists():
        print(f"  RULE.md: OK")
    else:
        print(f"  RULE.md: FAIL missing")
        all_ok = False

    for agent_name in AGENTS:
        dst = agents_path / agent_name
        if dst.exists():
            skill_md = dst / "SKILL.md"
            ok = skill_md.exists()
            status = "OK" if ok else "WARN link exists but SKILL.md missing"
        else:
            ok = False
            status = "FAIL missing"
        if not ok:
            all_ok = False
        print(f"  {agent_name}: {status}")

    # Check venv
    print("\nPython environment:")
    venv_dir = MCP_SERVER_DIR / ".venv"
    python = find_python_in_venv(venv_dir)
    if python:
        print(f"  venv: OK ({python})")
        # Check mcp is installed
        try:
            result = subprocess.run(
                [str(python), "-c", "from mcp.server.fastmcp import FastMCP; print('ok')"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and "ok" in result.stdout:
                print(f"  mcp: OK (FastMCP available)")
            else:
                print("  mcp: FAIL not installed")
                all_ok = False
        except Exception:
            print("  mcp: WARN could not verify")
    else:
        print("  venv: FAIL missing")
        all_ok = False

    # Check .mcp.json
    print("\nMCP config:")
    mcp_json_path = PLUGIN_DIR / ".mcp.json"
    if mcp_json_path.exists():
        with open(mcp_json_path, "r", encoding="utf-8") as f:
            mcp_data = json.load(f)
        if "unreal-agent-bridge" in mcp_data.get("mcpServers", {}):
            print(f"  .mcp.json: OK (unreal-agent-bridge configured)")
        else:
            print("  .mcp.json: FAIL unreal-agent-bridge entry missing")
            all_ok = False
    else:
        print("  .mcp.json: FAIL missing")
        all_ok = False

    # Check settings
    print("\nSettings:")
    settings_path = agent_path / "settings.local.json"
    if settings_path.exists():
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
        allow_list = settings.get("permissions", {}).get("allow", [])
        missing = [p for p in REQUIRED_PERMISSIONS if p not in allow_list]
        if not missing:
            print(f"  Permissions: OK (all {len(REQUIRED_PERMISSIONS)} present)")
        else:
            print(f"  Permissions: WARN missing {len(missing)}: {missing}")
            all_ok = False
    else:
        print(f"  settings.local.json: FAIL missing")
        all_ok = False

    # Check knowledge dir
    print("\nKnowledge:")
    knowledge_path = PLUGIN_DIR / "Knowledge"
    if knowledge_path.exists():
        mg = knowledge_path / "module_graph.json"
        if mg.exists():
            print(f"  Knowledge graph: OK (module_graph.json exists)")
        else:
            print(f"  Knowledge directory: OK (empty — run /ue-knowledge-init)")
        # Check callable_catalog (per-client)
        catalog_path = agent_path / "callable_catalog"
        if catalog_path.exists() and (catalog_path / "catalog_index.json").exists():
            is_link = catalog_path.is_symlink() or (
                is_windows() and catalog_path.is_junction()
                if hasattr(catalog_path, 'is_junction') else False
            )
            source_info = " (linked)" if is_link else ""
            print(f"  Callable catalog: OK{source_info}")
        else:
            print(f"  Callable catalog: MISSING (run generate_catalog or setup.py to reuse)")
    else:
        print(f"  Knowledge directory: FAIL missing")

    print(f"\n{'='*60}")
    if all_ok:
        print("OK All checks passed!")
    else:
        print("FAIL Some checks failed. Run 'python setup.py' to fix.")

    return all_ok


# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------

def uninstall(client: str):
    agent_dir = CLIENT_MAP[client]
    agent_path = PLUGIN_DIR / agent_dir
    skills_path = agent_path / "skills"

    print(f"UnrealEngineAIAssist Uninstall")
    print(f"  Client: {client} ({agent_dir})")
    print()

    # Remove skill links
    print("Removing skill links...")
    for skill in SKILLS:
        dst = skills_path / skill
        if dst.exists() or dst.is_symlink():
            remove_link(dst)
            print(f"  Removed: {skill}")
        else:
            print(f"  Already gone: {skill}")

    # Remove agent links
    print("\nRemoving agent links...")
    agents_path = agent_path / "agents"
    for agent_name in AGENTS:
        dst = agents_path / agent_name
        if dst.exists() or dst.is_symlink():
            remove_link(dst)
            print(f"  Removed: {agent_name}")
        else:
            print(f"  Already gone: {agent_name}")
    # Remove shared RULE.md link
    rule_link = agents_path / "RULE.md"
    if rule_link.exists() or rule_link.is_symlink():
        remove_link(rule_link)
        print(f"  Removed: RULE.md")
    # Remove agents directory if empty
    if agents_path.exists():
        try:
            agents_path.rmdir()  # Only removes if empty
            print(f"  Removed empty agents/ directory")
        except OSError:
            pass  # Not empty, leave it

    # Remove venv
    venv_dir = MCP_SERVER_DIR / ".venv"
    if venv_dir.exists():
        shutil.rmtree(venv_dir, ignore_errors=True)
        print("\nRemoved Python venv")

    # Remove unreal-agent-bridge from .mcp.json (but keep other servers)
    mcp_json_path = PLUGIN_DIR / ".mcp.json"
    if mcp_json_path.exists():
        with open(mcp_json_path, "r", encoding="utf-8") as f:
            mcp_data = json.load(f)
        if "unreal-agent-bridge" in mcp_data.get("mcpServers", {}):
            del mcp_data["mcpServers"]["unreal-agent-bridge"]
        if not mcp_data["mcpServers"]:
            mcp_json_path.unlink()
            print("Removed .mcp.json (was the only server)")
        else:
            with open(mcp_json_path, "w", encoding="utf-8") as f:
                json.dump(mcp_data, f, indent=2, ensure_ascii=False)
                f.write("\n")
            print("Removed unreal-agent-bridge from .mcp.json")

    # Note: don't remove Knowledge/ (user data) or settings.local.json (may have other settings)
    print(f"\n{'='*60}")
    print("OK Uninstall complete.")
    print(f"  Note: Knowledge/ and {agent_dir}/settings.local.json were preserved.")
    print(f"  Delete them manually if desired.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="UnrealEngineAIAssist setup script",
    )
    parser.add_argument(
        "--client", "-c",
        choices=list(CLIENT_MAP.keys()),
        help="AI client to configure (default: auto-detect)",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Verify installation without making changes",
    )
    parser.add_argument(
        "--uninstall", action="store_true",
        help="Remove symlinks and generated configs",
    )
    parser.add_argument(
        "--port", type=int, default=13090,
        help="TCP port for the UnrealEngineAIAssist plugin (default: 13090)",
    )
    args = parser.parse_args()

    # Resolve client
    client = args.client
    if not client:
        client = auto_detect_client()
        if not client:
            client = "claude"
            print(f"No existing AI client directory found, defaulting to '{client}'")

    if args.check:
        ok = check(client)
        sys.exit(0 if ok else 1)
    elif args.uninstall:
        uninstall(client)
    else:
        install(client, port=args.port)


if __name__ == "__main__":
    main()
