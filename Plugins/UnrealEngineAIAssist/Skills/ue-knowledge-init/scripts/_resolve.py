"""Shared path resolution for UE knowledge-graph scripts.

Auto-detects the agent config directory name (e.g. '.claude', '.windsurf',
'.cursor') from the script's location, with an env-var override.

Supports two layouts:
  1. Plugin layout:  Engine/Plugins/UnrealEngineAIAssist/Skills/<skill>/scripts/
  2. Legacy layout:  Engine/.{agent}/skills/<skill>/scripts/

Exports:
    agent_dir_name()  -> str   e.g. '.claude'
    find_engine_root() -> Path  engine repo root containing Engine/Source/
    find_plugin_dir()  -> Path  plugin root containing Skills/
    knowledge_dir()   -> Path  <plugin_dir>/Knowledge
    skills_dir()      -> Path  Engine/<agent>/skills
"""

import os
from pathlib import Path

_cached_agent_dir: str | None = None


def agent_dir_name() -> str:
    """Return the agent config directory name (e.g. '.claude').

    Priority:
        1. AGENT_DIR_NAME env var
        2. Auto-detect: plugin layout (Skills/ under a Plugins/ dir)
           -> scan Engine/.* for a directory with knowledge/ subfolder
        3. Auto-detect: legacy layout (skills/ under a dot-prefixed dir)
        4. Fallback to '.claude'
    """
    global _cached_agent_dir
    if _cached_agent_dir is not None:
        return _cached_agent_dir

    env = os.environ.get("AGENT_DIR_NAME", "").strip()
    if env:
        _cached_agent_dir = env
        return _cached_agent_dir

    p = Path(__file__).resolve()

    # Check plugin layout: .../<Engine>/Plugins/<PluginName>/Skills/<skill>/scripts/_resolve.py
    for parent in p.parents:
        if parent.name == "Skills":
            plugin_dir = parent.parent  # e.g. UnrealEngineAIAssist
            if plugin_dir.parent.name == "Plugins":
                engine_dir = plugin_dir.parent.parent  # Engine/
                if (engine_dir / "Source").is_dir():
                    # Scan Engine/.* for agent dirs with knowledge/
                    for item in engine_dir.iterdir():
                        if item.name.startswith(".") and item.is_dir():
                            if (item / "knowledge").is_dir():
                                _cached_agent_dir = item.name
                                return _cached_agent_dir
                    # No existing agent dir found; fallback to .claude
                    _cached_agent_dir = ".claude"
                    return _cached_agent_dir

    # Legacy layout: walk up from __file__ to find 'skills' parent,
    # then its parent should be Engine/<agent_dir>.
    for parent in p.parents:
        if parent.name == "skills":
            candidate = parent.parent  # Engine/<agent_dir>
            engine_dir = candidate.parent  # Engine/
            if (engine_dir / "Source").is_dir() and candidate.name.startswith("."):
                _cached_agent_dir = candidate.name
                return _cached_agent_dir
            break

    _cached_agent_dir = ".claude"
    return _cached_agent_dir


def find_engine_root(reference_file: str | None = None) -> Path:
    """Return the engine repository root (the directory containing
    ``Engine/Source/``).

    Detection order:
        1. Walk up from *reference_file* (default: this module) — works when
           the plugin lives under ``Engine/Plugins/``.
        2. Read ``plugin.config.json`` in the plugin directory — handles the
           common case where project and engine are on different drives.
        3. Fallback to cwd.
    """
    start = Path(reference_file).resolve() if reference_file else Path(__file__).resolve()
    for parent in [start] + list(start.parents):
        if (parent / "Engine" / "Source").is_dir():
            return parent

    # plugin.config.json is written by the C++ plugin on editor startup.
    try:
        import json
        config_path = find_plugin_dir() / "plugin.config.json"
        if config_path.is_file():
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            engine_dir = cfg.get("engine_dir", "")
            if engine_dir:
                p = Path(engine_dir)
                # engine_dir typically points to the Engine/ subdirectory
                if p.name == "Engine" and (p / "Source").is_dir():
                    return p.parent
                if (p / "Engine" / "Source").is_dir():
                    return p
    except Exception:
        pass

    return Path.cwd()


_cached_plugin_dir: Path | None = None


def find_plugin_dir() -> Path:
    """Find the plugin root directory (the one containing Skills/ and Agents/).

    Detection order:
        1. AGENT_BRIDGE_PLUGIN_DIR env var
        2. Walk up from __file__ to find a parent whose child ``Skills/`` exists
           (plugin layout: .../Plugins/UnrealEngineAIAssist/Skills/<skill>/scripts/)
        3. Walk up from __file__ looking for ``skills/`` under a dot-prefixed dir,
           then go to the plugin that owns the symlinked Skills/
        4. Fallback to cwd
    """
    global _cached_plugin_dir
    if _cached_plugin_dir is not None:
        return _cached_plugin_dir

    env = os.environ.get("AGENT_BRIDGE_PLUGIN_DIR", "").strip()
    if env:
        _cached_plugin_dir = Path(env)
        return _cached_plugin_dir

    p = Path(__file__).resolve()

    # Plugin layout: walk up until we find a dir that has a Skills/ child
    for parent in p.parents:
        if parent.name in ("Skills", "skills"):
            candidate = parent.parent
            # Verify it looks like our plugin dir
            if (candidate / "Skills").is_dir():
                _cached_plugin_dir = candidate
                return _cached_plugin_dir
            # Legacy: .claude/skills/ -> plugin is one more level up
            if candidate.name.startswith(".") and (candidate.parent / "Skills").is_dir():
                _cached_plugin_dir = candidate.parent
                return _cached_plugin_dir

    _cached_plugin_dir = Path.cwd()
    return _cached_plugin_dir


def knowledge_dir(engine_root: Path | None = None) -> Path:
    """Return ``<plugin_dir>/Knowledge``.

    The *engine_root* parameter is accepted for backward compatibility but
    is no longer used — knowledge data now lives under the plugin directory.
    """
    return find_plugin_dir() / "Knowledge"


def skills_dir(engine_root: Path | None = None) -> Path:
    """Return ``<engine_root>/Engine/<agent_dir>/skills``.

    In plugin layout, the actual skill files live inside the plugin,
    but this returns the symlinked path under the agent directory.
    """
    if engine_root is None:
        engine_root = find_engine_root()
    return engine_root / "Engine" / agent_dir_name() / "skills"
