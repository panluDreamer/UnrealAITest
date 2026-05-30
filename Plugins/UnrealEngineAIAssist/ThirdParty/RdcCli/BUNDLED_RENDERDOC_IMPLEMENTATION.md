# Bundled RenderDoc Implementation

## Overview
This document describes the complete implementation of bundled RenderDoc binaries in rdc-cli, eliminating the need for users to run `rdc setup-renderdoc`.

## Architecture

### Directory Structure
```
src/rdc/
├── _bundled_renderdoc.py          # Runtime discovery helper module
├── _renderdoc_bins/               # Bundled binaries package directory
│   ├── __init__.py                # Makes _renderdoc_bins a Python package
│   ├── v1_21/                     # RenderDoc 1.21 binaries
│   │   └── py312/                 # Python 3.12 binaries
│   │       ├── renderdoc.pyd      # Windows (when present)
│   │       ├── renderdoc.dll      # Windows (when present)
│   │       ├── renderdoc.so       # Linux (when present)
│   │       └── librenderdoc.so    # Linux (when present)
│   └── v1_43/                     # RenderDoc 1.43 binaries
│       ├── py310/                 # Python 3.10 binaries (future)
│       ├── py311/                 # Python 3.11 binaries (future)
│       ├── py312/                 # Python 3.12 binaries
│       ├── py313/                 # Python 3.13 binaries (future)
│       └── py314/                 # Python 3.14 binaries (future)
├── discover.py                    # PATCHED: Integrated bundled discovery
└── ...other modules
```

## Implementation Details

### 1. Helper Module: `src/rdc/_bundled_renderdoc.py`

**Functions:**

#### `get_bundled_versions() -> list[str]`
- Scans the `_renderdoc_bins/` directory structure
- Converts directory names: `v1_21` → `1.21`
- Returns versions sorted in descending order (newest first)
- Returns empty list if directory doesn't exist

#### `get_bundled_renderdoc_path(version: str) -> Optional[Path]`
- Accepts version string like `"1.21"` or `"1.43"`
- Detects current Python version: `3.12` → `"py312"`
- Constructs path: `_renderdoc_bins/v1_21/py312/`
- Returns `Path` if directory exists, `None` otherwise
- Logs debug information for troubleshooting

### 2. Module Discovery: `src/rdc/discover.py`

**Changes Made:**
1. Added import: `from rdc import _bundled_renderdoc`
2. Updated `find_renderdoc()` function docstring with new search order
3. Inserted bundled version discovery logic after RENDERDOC_PYTHON_PATH check

**New Search Order:**
```
1. RENDERDOC_PYTHON_PATH environment variable
2. Bundled RenderDoc versions (highest version first)
3. System paths (/usr/lib/renderdoc, /usr/local/lib/renderdoc, etc.)
4. Sibling directory of renderdoccmd on PATH
```

**Implementation Logic:**
```python
# Add bundled RenderDoc versions (highest version first)
bundled_versions = _bundled_renderdoc.get_bundled_versions()
for version in bundled_versions:
    bundled_path = _bundled_renderdoc.get_bundled_renderdoc_path(version)
    if bundled_path:
        candidates.append(str(bundled_path))
```

### 3. Package Configuration: `pyproject.toml`

**Changes Made:**
```toml
[tool.setuptools.package-data]
"rdc._skills" = ["**/*.md"]
"rdc._renderdoc_bins" = ["**/*.pyd", "**/*.dll", "**/*.so"]
```

This ensures that when building wheel distributions, all binary files (`.pyd`, `.dll`, `.so`) in the `_renderdoc_bins/` directory are included in the package.

### 4. Version Control: `.gitignore`

**Changes Made:**
Added force-include patterns to override global `*.pyd` exclusion:
```
# Force-include bundled RenderDoc binaries
!src/rdc/_renderdoc_bins/
!src/rdc/_renderdoc_bins/**/*.pyd
!src/rdc/_renderdoc_bins/**/*.dll
!src/rdc/_renderdoc_bins/**/*.so
```

## Current Status

### Completed ✓
- [x] Directory structure created with v1.21 and v1.43 support for Python 3.12
- [x] `_bundled_renderdoc.py` helper module implemented
- [x] `discover.py` patched with bundled discovery integration
- [x] `pyproject.toml` configured for binary inclusion
- [x] `.gitignore` updated to allow binary commits
- [x] Python syntax validation passed for all modules
- [x] Module import chain verified (discover.py → _bundled_renderdoc)

### Pending Tasks ⏳

#### Phase 1: Windows Binary Support
1. Obtain RenderDoc 1.21 & 1.43 for Python 3.12 (Windows):
   - `renderdoc.pyd` (Python 3.12)
   - `renderdoc.dll` (matching version)
   - Place in: `src/rdc/_renderdoc_bins/v1_21/py312/` and `v1_43/py312/`

2. Test on Windows:
   - Verify `find_renderdoc()` discovers bundled versions
   - Verify `os.add_dll_directory()` handles DLL loading
   - Test `rdc` command functionality with bundled binaries
   - Test wheel distribution includes binaries

#### Phase 2: Multi-Python Version Support
1. Expand to Python 3.10, 3.11, 3.13, 3.14:
   - Create directories: `v1_21/py310/`, `v1_21/py311/`, etc.
   - Obtain precompiled binaries for each version
   - Test discovery mechanism selects correct Python version

#### Phase 3: Linux Support
1. Obtain RenderDoc binaries for Linux (Python 3.12):
   - `renderdoc.so`
   - `librenderdoc.so`
   - Test ARM Performance Studio patched module support

2. Test on Linux:
   - Verify preload mechanism for librenderdoc.so
   - Test multiversion discovery on Linux

#### Phase 4: Build & Distribution Testing
1. Build wheel distribution:
   ```bash
   python -m build --wheel
   ```

2. Verify wheel contents:
   ```bash
   unzip -l dist/rdc_cli-*.whl | grep _renderdoc_bins
   ```

3. Test installation and runtime:
   - Install from wheel
   - Verify `import renderdoc` works without setup
   - Check diagnostic information

## Binary Files Needed

### Windows (Python 3.12)
- **RenderDoc 1.21:**
  - `renderdoc.pyd` (ABI matches CPython 3.12)
  - `renderdoc.dll`
  - Location: `renderdoc/lib/` or similar in official releases

- **RenderDoc 1.43:**
  - `renderdoc.pyd` (ABI matches CPython 3.12)
  - `renderdoc.dll`

### Linux (Python 3.12)
- **RenderDoc 1.21:**
  - `renderdoc.so`
  - `librenderdoc.so.1` or similar
  - Location: `/usr/lib/renderdoc/` or from package manager

- **RenderDoc 1.43:**
  - `renderdoc.so`
  - `librenderdoc.so.1` or similar

## Testing Checklist

- [ ] `import rdc._bundled_renderdoc` works
- [ ] `import rdc.discover` works
- [ ] `get_bundled_versions()` returns `["1.43", "1.21"]` (after binaries added)
- [ ] `get_bundled_renderdoc_path("1.43")` returns correct path
- [ ] `find_renderdoc()` finds bundled versions
- [ ] `rdc` commands work with bundled binaries
- [ ] Wheel includes binary files
- [ ] Installation from wheel has no `renderdoc` import failures

## Notes

- The implementation prioritizes bundled versions after RENDERDOC_PYTHON_PATH but before system paths
- This allows users to override bundled versions with environment variables if needed
- The subprocess-based probing mechanism prevents crashes from incompatible binaries
- ARM Performance Studio support is preserved through conditional preloading
- Future expansion to Python 3.10, 3.11, 3.13, 3.14 is straightforward (just add directories and binaries)
