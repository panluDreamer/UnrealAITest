# Bundled RenderDoc Implementation Status

**Last Updated:** 2026-04-14  
**Status:** Phase 1 Implementation Complete - Ready for Binary Deployment

## Overview

The bundled RenderDoc discovery mechanism has been fully integrated into rdc-cli. This eliminates the need for users to run `rdc setup-renderdoc` by including precompiled RenderDoc binaries within the package distribution.

## Implementation Summary

### Components

1. **src/rdc/discover.py** - PATCHED
   - Import added: `from rdc import _bundled_renderdoc`
   - Docstring updated for 4-item search order
   - Bundled discovery logic integrated at priority 2

2. **src/rdc/_bundled_renderdoc.py** - COMPLETE
   - get_bundled_versions(): Scans and returns available versions
   - get_bundled_renderdoc_path(): Maps version to Python-specific directory

3. **src/rdc/_renderdoc_bins/** - STRUCTURE READY
   - v1_21/py312/ (awaiting binaries)
   - v1_43/py312/ (awaiting binaries)

4. **pyproject.toml** - CONFIGURED
   - Package-data includes *.pyd, *.dll, *.so

5. **.gitignore** - CONFIGURED
   - Force-include patterns for binary files

## Validation Results

- [PASS] Module imports and initialization
- [PASS] Version detection (1.21, 1.43)
- [PASS] Python version directory structure
- [PASS] Search order prioritization
- [PASS] Configuration files

## Phase 1: Windows - Python 3.12

**Status:** READY FOR BINARY DEPLOYMENT

**Required Actions:**

1. Obtain renderdoc.pyd + renderdoc.dll for RenderDoc 1.21 (CPython 3.12)
   - Deploy to: src/rdc/_renderdoc_bins/v1_21/py312/

2. Obtain renderdoc.pyd + renderdoc.dll for RenderDoc 1.43 (CPython 3.12)
   - Deploy to: src/rdc/_renderdoc_bins/v1_43/py312/

3. Verification Checklist:
   - [ ] Binaries placed in correct directories
   - [ ] python -m py_compile src/rdc/discover.py (syntax check)
   - [ ] Test discovery with: python -c "from rdc import discover; print(discover.find_renderdoc())"
   - [ ] Build wheel: python -m build --wheel
   - [ ] Verify wheel contents: unzip -l dist/rdc_cli-*.whl | grep _renderdoc_bins
   - [ ] Test rdc commands work with bundled module

## Phase 2: Multi-Python (After Phase 1)
- Expand to Python 3.10, 3.11, 3.13, 3.14

## Phase 3: Linux/macOS (After Phase 1)
- Obtain renderdoc.so and librenderdoc.so

## Phase 4: Wheel & Release (After All Phases)
- Build multi-platform wheel
- Update documentation

## Backward Compatibility

- RENDERDOC_PYTHON_PATH env var still works (priority 1)
- System RenderDoc installations still discovered
- rdc setup-renderdoc workflow unchanged

## Next Steps

1. Obtain Windows binaries for RenderDoc 1.21 and 1.43, Python 3.12
2. Deploy to src/rdc/_renderdoc_bins/v{version}/py312/
3. Run validation tests
4. Build and test wheel distribution
5. Proceed to Phase 2 after Phase 1 success

