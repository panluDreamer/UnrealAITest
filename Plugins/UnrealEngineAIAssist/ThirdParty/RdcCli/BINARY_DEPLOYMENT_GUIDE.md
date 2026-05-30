# Binary Deployment Guide

## Current Status

The bundled RenderDoc discovery mechanism is fully implemented and ready to receive precompiled binaries. All infrastructure (directories, configuration, discovery logic) is in place.

## Directory Structure

```
src/rdc/_renderdoc_bins/
├── __init__.py
├── v1_21/
│   └── py312/
│       ├── renderdoc.pyd
│       └── renderdoc.dll
└── v1_43/
    └── py312/
        ├── renderdoc.pyd
        └── renderdoc.dll
```

## Binary Requirements - Phase 1 (Windows, Python 3.12)

### RenderDoc 1.21

**Location:** `src/rdc/_renderdoc_bins/v1_21/py312/`

**Files Required:**
- `renderdoc.pyd` - Python extension module for CPython 3.12 (32-bit or 64-bit matching your Python build)
- `renderdoc.dll` - RenderDoc core library (MUST match the version in renderdoc.pyd)

**Source:** Official RenderDoc 1.21 release
- Download from: https://github.com/baldurk/renderdoc/releases/tag/v1.21
- Or from RenderDoc website official downloads

**Verification:**
```bash
# After placing files, verify they exist:
dir src\rdc\_renderdoc_bins\v1_21\py312\
# Should show:
#   renderdoc.pyd
#   renderdoc.dll
```

### RenderDoc 1.43

**Location:** `src/rdc/_renderdoc_bins/v1_43/py312/`

**Files Required:**
- `renderdoc.pyd` - Python extension module for CPython 3.12
- `renderdoc.dll` - RenderDoc core library (MUST match the version in renderdoc.pyd)

**Source:** Official RenderDoc 1.43 release
- Download from: https://github.com/baldurk/renderdoc/releases/tag/v1.43
- Or from RenderDoc website official downloads

**Verification:**
```bash
# After placing files, verify they exist:
dir src\rdc\_renderdoc_bins\v1_43\py312\
# Should show:
#   renderdoc.pyd
#   renderdoc.dll
```

## Deployment Steps

1. **Download binaries** from official RenderDoc releases (1.21 and 1.43)

2. **Extract/Locate** the precompiled Python modules:
   - For Windows: Look for `.pyd` files in the RenderDoc distribution
   - Usually found in: `renderdoc/bin/` or similar

3. **Verify architecture compatibility:**
   ```bash
   # Check your Python architecture:
   python -c "import struct; print(f'{struct.calcsize(\"P\")*8}-bit')"
   # Output: either "32-bit" or "64-bit"
   
   # Get Python version:
   python --version
   # Output should be Python 3.12.x
   ```

4. **Copy binaries to directories:**
   ```bash
   # For RenderDoc 1.21
   copy renderdoc.pyd src\rdc\_renderdoc_bins\v1_21\py312\
   copy renderdoc.dll src\rdc\_renderdoc_bins\v1_21\py312\
   
   # For RenderDoc 1.43
   copy renderdoc.pyd src\rdc\_renderdoc_bins\v1_43\py312\
   copy renderdoc.dll src\rdc\_renderdoc_bins\v1_43\py312\
   ```

5. **Verify placement:**
   ```bash
   dir src\rdc\_renderdoc_bins\v1_21\py312\
   dir src\rdc\_renderdoc_bins\v1_43\py312\
   # Both should show both .pyd and .dll files
   ```

## Validation After Deployment

### 1. Syntax Check
```bash
python -m py_compile src/rdc/discover.py
# Should produce no output (success)
```

### 2. Import Test
```bash
python -c "from rdc import discover; mod = discover.find_renderdoc(); print(f'Found: {mod}')"
# Should print: Found: <module 'renderdoc' from 'src/rdc/_renderdoc_bins/v1_21/py312/renderdoc.pyd'>
# (or v1_43 depending on what's available)
```

### 3. Version Discovery
```bash
python -c "from rdc._bundled_renderdoc import get_bundled_versions; print(get_bundled_versions())"
# Should print: ['1.43', '1.21'] (descending order)
```

### 4. Path Resolution
```bash
python -c "from rdc._bundled_renderdoc import get_bundled_renderdoc_path; print(get_bundled_renderdoc_path('1.21'))"
# Should print path to v1_21/py312 directory
```

### 5. Run Test Suite
```bash
# If pytest available:
python -m pytest tests/test_bundled_discovery.py -v

# Or simple import test:
python tests/test_bundled_discovery.py
```

## Building Wheel Distribution

After binaries are placed:

```bash
# Install build tools if needed:
pip install build

# Build wheel:
python -m build --wheel

# Verify wheel contents:
# Windows:
tar -tzf dist/rdc_cli-*.whl | findstr "_renderdoc_bins"

# Or using unzip if available:
unzip -l dist/rdc_cli-*.whl | grep _renderdoc_bins
```

**Expected output should show:**
```
rdc_cli-X.Y.Z-py3-none-any.whl:
  rdc/_renderdoc_bins/__init__.py
  rdc/_renderdoc_bins/v1_21/py312/renderdoc.pyd
  rdc/_renderdoc_bins/v1_21/py312/renderdoc.dll
  rdc/_renderdoc_bins/v1_43/py312/renderdoc.pyd
  rdc/_renderdoc_bins/v1_43/py312/renderdoc.dll
```

## ABI Compatibility Checklist

When obtaining binaries, ensure:

- [ ] renderdoc.pyd is compiled for CPython 3.12 (check filename: cp312-win_amd64.pyd)
- [ ] renderdoc.dll version matches the .pyd module version
- [ ] Architecture matches your Python (32-bit or 64-bit)
- [ ] Windows version compatibility (depends on RenderDoc's build requirements)
- [ ] Both .pyd and .dll are present for each version

## Troubleshooting

### Issue: "No module named 'renderdoc'"

**Solution:** Verify binaries are in correct directories:
```bash
python -c "from pathlib import Path; print(Path('src/rdc/_renderdoc_bins').absolute())"
# Then manually verify the files exist
```

### Issue: "DLL load failed while importing renderdoc"

**Cause:** renderdoc.dll not found in py312 directory  
**Solution:** Ensure both renderdoc.pyd AND renderdoc.dll are in the same directory

### Issue: "DLL load failed: %1 is not a valid Win32 application"

**Cause:** Architecture mismatch (32-bit/64-bit)  
**Solution:** Verify Python architecture and get matching binary:
```bash
python -c "import sys; print(sys.maxsize > 2**32 and '64-bit' or '32-bit')"
```

### Issue: "This module is not ABI compatible with this Python version"

**Cause:** Binary compiled for different Python version  
**Solution:** Ensure .pyd filename indicates Python 3.12:
- Look for: `cp312-win_amd64.pyd` (or `cp312-win32.pyd`)
- Get correct version from RenderDoc release for your Python version

## Phase 1 Completion Checklist

After deploying Phase 1 binaries:

- [ ] renderdoc.pyd and renderdoc.dll placed in v1_21/py312
- [ ] renderdoc.pyd and renderdoc.dll placed in v1_43/py312
- [ ] Syntax check passes: python -m py_compile src/rdc/discover.py
- [ ] Import test passes: python -c "from rdc import discover; discover.find_renderdoc()"
- [ ] Version discovery passes: get_bundled_versions() returns ['1.43', '1.21']
- [ ] Path resolution passes: get_bundled_renderdoc_path('1.21') returns valid path
- [ ] Test suite passes: python tests/test_bundled_discovery.py
- [ ] Wheel builds successfully: python -m build --wheel
- [ ] Wheel contains binaries: unzip -l dist/rdc_cli-*.whl includes all .pyd/.dll files
- [ ] rdc commands work: test rdc open, rdc query, etc.

## Next Phases

### Phase 2: Multi-Python (Python 3.10, 3.11, 3.13, 3.14)
- Create additional py310/, py311/, py313/, py314/ directories
- Deploy binaries for each Python version
- Test with each Python version

### Phase 3: Linux/macOS Support
- Obtain renderdoc.so and librenderdoc.so
- Deploy to Linux/macOS specific directories
- Test platform-specific features (ARM Performance Studio)

### Phase 4: Release
- Build multi-platform wheel
- Publish to PyPI
- Update documentation

