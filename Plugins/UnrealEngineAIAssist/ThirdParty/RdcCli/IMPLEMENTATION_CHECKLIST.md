# Bundled RenderDoc Implementation Checklist

## Overview

This document tracks the 4-phase implementation of bundled RenderDoc binary support for rdc-cli. Each phase builds upon the previous one, with specific success criteria and resource requirements.

---

## Phase 0: Infrastructure Setup [COMPLETE]

Infrastructure and configuration to support bundled binary discovery.

### Infrastructure Checklist

- [x] Create src/rdc/_bundled_renderdoc.py module
- [x] Update src/rdc/discover.py module  
- [x] Create directory structure for binary storage
- [x] Configure package distribution
- [x] Create test suite
- [x] Create documentation

### Phase 0 Success Criteria

- [x] All tests pass
- [x] Directory structure created
- [x] Configuration correct
- [x] Documentation complete

---

## Phase 1: Windows Python 3.12 Binaries

Windows support for Python 3.12 with RenderDoc versions 1.21 and 1.43.

### Binary Acquisition

- [ ] Download RenderDoc 1.21 Windows binaries
- [ ] Download RenderDoc 1.43 Windows binaries

### Binary Deployment

- [ ] Deploy RenderDoc 1.21 for Python 3.12
- [ ] Deploy RenderDoc 1.43 for Python 3.12

### Binary Validation

- [ ] Test binary discovery
- [ ] Test binary loading
- [ ] Test end-to-end discovery

### Wheel Building

- [ ] Build wheel distribution
- [ ] Verify wheel contents
- [ ] Test wheel installation

### Phase 1 Success Criteria

- [ ] Both versions available for Python 3.12 on Windows
- [ ] Discovery finds bundled binaries
- [ ] All tests pass
- [ ] Wheel includes binaries

---

## Phase 2: Multi-Python Versions

Expand Phase 1 coverage to Python 3.10, 3.11, 3.13, 3.14.

- [ ] Create directories for Python 3.10, 3.11, 3.13, 3.14
- [ ] Deploy binaries for each version
- [ ] Test all versions

---

## Phase 3: Linux and macOS Support

Cross-platform support with native binaries.

- [ ] Linux directory structure and binaries
- [ ] macOS directory structure and binaries
- [ ] Platform testing matrix

---

## Phase 4: Release and Documentation

Final release preparation and PyPI publication.

- [ ] Update documentation
- [ ] PyPI publication
- [ ] Release validation

---

## Implementation Status

- Phase 0: **COMPLETE**
- Phase 1: **AWAITING BINARY DEPLOYMENT**
- Phase 2: **PENDING Phase 1**
- Phase 3: **PENDING Phase 2**
- Phase 4: **PENDING Phase 3**

**Last Updated**: 2026-04-14
