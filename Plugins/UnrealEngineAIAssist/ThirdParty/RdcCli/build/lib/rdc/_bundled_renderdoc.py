"""Helper module for discovering bundled RenderDoc binaries.

Provides runtime discovery of precompiled RenderDoc modules included in the
rdc-cli package distribution.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def get_bundled_renderdoc_path(version: str) -> Optional[Path]:
    """Return path to bundled renderdoc directory for the given version.
    
    Args:
        version: Version string like "1.21" or "1.43"
        
    Returns:
        Path to the renderdoc binaries directory (e.g., _renderdoc_bins/v1_21/py312/)
        or None if not available for this Python version.
    """
    # Convert version "1.21" -> "v1_21"
    version_dir = f"v{version.replace('.', '_')}"
    
    # Get current Python version: 3.10 -> "py310", 3.12 -> "py312", etc.
    py_version = f"py{sys.version_info.major}{sys.version_info.minor}"
    
    # Build path to bundled binaries
    # This module is at: src/rdc/_bundled_renderdoc.py
    # Bundled binaries are at: src/rdc/_renderdoc_bins/v1_21/py312/
    module_dir = Path(__file__).parent
    bundled_dir = module_dir / "_renderdoc_bins" / version_dir / py_version
    
    if bundled_dir.is_dir():
        log.debug("Found bundled RenderDoc %s at %s", version, bundled_dir)
        return bundled_dir
    
    log.debug("Bundled RenderDoc %s not available for Python %s", version, py_version)
    return None


def get_bundled_versions() -> list[str]:
    """Return list of available bundled RenderDoc versions.
    
    Returns:
        List of version strings like ["1.43", "1.21"] in descending order
        (newest first).
    """
    module_dir = Path(__file__).parent
    bundled_root = module_dir / "_renderdoc_bins"
    
    if not bundled_root.is_dir():
        return []
    
    versions = []
    for version_dir in bundled_root.iterdir():
        if not version_dir.is_dir():
            continue
        # Convert "v1_21" -> "1.21"
        version_str = version_dir.name.replace("v", "").replace("_", ".")
        versions.append(version_str)
    
    # Sort in descending order (newest first)
    versions.sort(reverse=True, key=lambda v: tuple(map(int, v.split("."))))
    
    log.debug("Available bundled RenderDoc versions: %s", versions)
    return versions
