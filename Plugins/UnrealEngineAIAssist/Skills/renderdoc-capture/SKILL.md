---
name: renderdoc-capture
description: |
  Analyze RenderDoc GPU frame captures using rdc-cli commands.
  TRIGGER when:
  - User asks to analyze a RenderDoc capture (.rdc file)
  - User asks about draw calls, shaders, pipeline state, GPU timings
  - User says "open capture", "frame analysis", "shader performance"
  - User asks "what's drawing X", "why is this slow", "check pipeline state"
  - User asks about pixel debugging, shader editing, render target comparison
  - Frame-level GPU investigation is needed for rendering bug diagnosis
  DO NOT TRIGGER when:
  - User is diagnosing a rendering bug without a capture file (general debugging)
  - User asks about material node graphs (use ArtTechnician agent)
  - User wants to capture frames from a running app without rdc-cli
---

# RenderDoc Capture Analysis — rdc-cli

## Activation Checklist

When this skill activates, **immediately** run the session snapshot:

```bash
python <skill_dir>/scripts/rdc_snapshot.py
```

This single command returns JSON with: `session_active`, `rdc_version`, `status`, `info`, `stats`, `passes`.

**Then follow these rules:**
- If `session_active: true` and capture file matches user's target → proceed directly, do NOT re-open
- If `session_active: true` but different file → `rdc close` then `rdc open <new_file>`
- If `session_active: false` → `rdc open <file>`, then re-run snapshot to cache context
- **Never** call `rdc open` without checking session status first
- **Cache the snapshot in memory** — don't re-run until user switches capture file

If rdc-cli is not installed (`rdc_version` missing), read `references/setup-guide.md`.

---

## ⚠️ Parameter Order Quick Reference

These commands have **different argument orders** — check before calling:

| Command | Order | Example |
|---------|-------|---------|
| `rdc pixel` | **X Y [EID]** | `rdc pixel 841 542 5942` |
| `rdc debug pixel` | **EID X Y** | `rdc debug pixel 5942 841 542` |
| `rdc pick-pixel` | **X Y** | `rdc pick-pixel 841 542` |
| `rdc rt` | **EID -o file** | `rdc rt 5942 -o out.png` |
| `rdc script` | **FILE** or **--code "..."** | `rdc script -c "print('hi')"` |

---

## Architecture

```
AI Agent ──Bash──> rdc <cmd> [--json] ──> daemon (holds capture open) ──> renderdoc Python module
```

- rdc-cli is a CLI tool with 72 commands, **managed by uv** (Python package manager)
- **Install**: `cd <plugin>/ThirdParty/RdcCli && uv tool install .` (one command, no build tools needed)
- **Update**: `cd <plugin>/ThirdParty/RdcCli && uv tool install . --force` (after pulling source changes)
- **Uninstall**: `uv tool uninstall rdc-cli`
- **Bundled renderdoc**: ships with precompiled `renderdoc.pyd` for v1.21 and v1.43 (Python 3.12) — no `rdc setup-renderdoc` needed
- Daemon architecture: `rdc open` loads capture once, subsequent commands query it instantly
- Default output is TSV (pipe-friendly); `--json` for structured parsing
- No MCP server, no RenderDoc GUI, no VS Build Tools needed

---

## Quick Start

```bash
rdc open scene.rdc              # Load capture (daemon auto-starts)
rdc info                        # Capture metadata
rdc draws                       # List all draw calls (TSV)
rdc draws --json                # Same, structured JSON
rdc pipeline 142 --json         # Pipeline state at event 142
rdc shader 142 ps               # Pixel shader source at event 142
rdc close                       # Release capture
```

---

## Command Reference

### Session Management

| Command | Description |
|---------|-------------|
| `rdc open <file.rdc>` | Open capture file (daemon auto-starts, previous capture auto-closes) |
| `rdc close` | Close current capture and stop daemon |
| `rdc status` | Show current capture info (file, API, event count) |
| `rdc goto <eid>` | Navigate to specific event ID |
| `rdc doctor` | Health check: renderdoc module, Python version, system info |

### Frame Overview

| Command | Description |
|---------|-------------|
| `rdc info` | Capture metadata: API, driver, GPU, resolution, timestamps |
| `rdc stats` | Frame statistics: draw/dispatch counts, resource counts, timings |
| `rdc events` | Full event list (all API calls, not just draws) |
| `rdc draws` | Draw call list with names, event IDs, instance counts |
| `rdc passes` | Render pass structure (hierarchical markers) |
| `rdc pass <name>` | Details of a specific render pass |
| `rdc log` | API debug messages and warnings |
| `rdc counters` | GPU performance counters (if available in capture) |

### Draw Call Inspection

| Command | Description |
|---------|-------------|
| `rdc event <eid>` | Event details (API call, parameters) |
| `rdc draw <eid>` | Draw call details (topology, vertex/index count, instances) |
| `rdc pipeline <eid>` | **Full pipeline state**: blend, depth-stencil, rasterizer, render targets, bound shaders, viewports, scissors |
| `rdc bindings <eid>` | Resource bindings: textures, buffers, samplers per shader stage |

### Shader Analysis

| Command | Description |
|---------|-------------|
| `rdc shader <eid> <stage>` | Shader disassembly/source. Stages: `vs`, `ps`, `cs`, `gs`, `hs`, `ds` |
| `rdc shader <eid> <stage> --constants` | Shader + constant buffer values |
| `rdc shaders` | All unique shaders in the frame |
| `rdc shader-map` | Shader → draw call mapping (which draws use which shaders) |

### Resource Inspection

| Command | Description |
|---------|-------------|
| `rdc resources` | All resources in capture (textures, buffers, shaders) |
| `rdc resource <id>` | Resource details (format, dimensions, usage) |
| `rdc usage <id>` | Where this resource is used across the frame |
| `rdc search <keyword>` | Search resources by name (partial match) |
| `rdc unused-targets` | Render targets that are written but never read |

### Pixel & Debug

| Command | Description |
|---------|-------------|
| `rdc pixel <eid> <x> <y>` | Pixel RGBA value at coordinates for event |
| `rdc pick-pixel <x> <y>` | Pick pixel from current output target |
| `rdc debug pixel <eid> <x> <y>` | Debug pixel shader execution |
| `rdc debug pixel <eid> <x> <y> --trace` | Full shader execution trace |
| `rdc debug vertex <eid> <vtx_id>` | Debug vertex shader for specific vertex |
| `rdc debug thread <eid> <gx> <gy> <gz>` | Debug compute shader thread |
| `rdc tex-stats <texture_id>` | Texture statistics (min/max/average values) |

### Export

| Command | Description |
|---------|-------------|
| `rdc texture <id> -o file.png` | Export texture as PNG |
| `rdc rt <eid> -o file.png` | Export render target at event as PNG |
| `rdc buffer <id> -o file.bin` | Export buffer data (binary) |
| `rdc mesh <eid> -o file.obj` | Export mesh at event (OBJ/glTF format) |
| `rdc snapshot <eid> -o dir/` | Full state snapshot (all targets, shaders, buffers) |

### Shader Edit-Replay

| Command | Description |
|---------|-------------|
| `rdc shader-encodings <eid> <stage>` | Available shader encodings for the API |
| `rdc shader-build <eid> <stage> <file>` | Compile modified shader source |
| `rdc shader-replace <eid> <stage> <file>` | Replace shader and re-render |
| `rdc shader-restore <eid> <stage>` | Restore original shader |
| `rdc shader-restore-all` | Restore all replaced shaders |

### CI Assertions

Exit codes: 0 = pass, 1 = fail, 2 = error

| Command | Description |
|---------|-------------|
| `rdc assert-pixel <eid> <x> <y> <r> <g> <b> <a>` | Assert pixel color matches expected |
| `rdc assert-image <eid> <reference.png>` | Assert render target matches reference image |
| `rdc assert-clean` | Assert no API errors/warnings in frame |
| `rdc assert-count <type> <op> <n>` | Assert resource/draw count (e.g., `draws <= 500`) |
| `rdc assert-state <eid> <vfs_path> <expected>` | Assert pipeline state value |

### Frame Comparison (Diff)

| Command | Description |
|---------|-------------|
| `rdc diff a.rdc b.rdc --draws` | Compare draw call lists (`+` added, `-` removed, `~` changed) |
| `rdc diff a.rdc b.rdc --stats` | Compare frame statistics |
| `rdc diff a.rdc b.rdc --pipeline <eid>` | Compare pipeline state at specific event |
| `rdc diff a.rdc b.rdc --framebuffer <eid>` | Compare framebuffer output |

### VFS (Virtual Filesystem)

Stable, scriptable paths to all capture data:

| Command | Description |
|---------|-------------|
| `rdc ls /` | List root: `draws/`, `resources/`, `textures/`, `shaders/`, `passes/`, ... |
| `rdc ls /draws/142/` | List draw 142's children: `pipeline/`, `shader/`, `targets/`, ... |
| `rdc cat /draws/142/shader/ps` | Read pixel shader at draw 142 |
| `rdc cat /draws/142/pipeline/blend` | Read blend state at draw 142 |
| `rdc tree /draws/142` | Full tree view of draw 142's state |

**Path patterns:**
- `/draws/<eid>/shader/<stage>` — Shader source
- `/draws/<eid>/pipeline/<component>` — Pipeline state component
- `/draws/<eid>/targets/` — Render targets
- `/resources/<id>/` — Resource metadata
- `/textures/<id>/` — Texture data
- `/passes/<name>/draws` — Draws in a render pass

### Android Remote Capture

| Command | Description |
|---------|-------------|
| `rdc android setup <package>` | Inject RenderDoc into Android app |
| `rdc android capture <package>` | Trigger frame capture |
| `rdc android stop <package>` | Remove RenderDoc injection |

### Target Control (Live Capture)

| Command | Description |
|---------|-------------|
| `rdc attach <pid>` | Attach to running process |
| `rdc capture-trigger` | Trigger capture on attached process |
| `rdc capture-list` | List captures from attached session |
| `rdc capture-copy <idx> -o file.rdc` | Download capture from target |

### Utilities

| Command | Description |
|---------|-------------|
| `rdc count <type>` | Quick count (draws, events, resources, etc.) |
| `rdc script <file.py>` | Execute Python script inside daemon (has `controller`, `rd`, `adapter`, `state` vars; requires `rdc open` first) |
| `rdc completion <shell>` | Install shell completions (bash/zsh/fish) |
| `rdc thumbnail -o thumb.png` | Extract capture thumbnail |
| `rdc gpus` | GPU info from capture |
| `rdc sections` | List capture file sections |
| `rdc callstacks` | API call stack traces (if available) |

---

## Output Format Tips

| Flag | Effect |
|------|--------|
| (default) | TSV — pipe to `grep`, `awk`, `sort`, `head`, `cut` |
| `--json` | Structured JSON object |
| `--jsonl` | Streaming JSON lines (one object per line) |
| `--no-header` | Omit TSV header row (cleaner piping) |
| `-q` / `--quiet` | ID-only output |
| `--sort <field>` | Sort results by field |
| `--limit <n>` | Limit result count |
| `--filter <expr>` | Filter results by expression |

**Recommendation**: Use `--json` when you need to parse specific fields. Use default TSV + `grep` for quick searches.

---

## Standard Analysis Workflows

### Phase 1: Frame Overview

```bash
rdc open capture.rdc
rdc info                                    # API, GPU, driver
rdc stats                                   # Draw count, dispatch count, resource count
rdc passes                                  # Render pass structure
```

Present to user:
> "Loaded capture ({API}): {draw_count} draws, {dispatch_count} dispatches.
> Render passes: {pass_list}. Which pass should I investigate?"

### Phase 2: Targeted Investigation

**"What's rendering X?"** (find draws by name/shader/texture):
```bash
rdc draws | grep -i "shadow"                # Search draws by name
rdc search "character_skin"                 # Search resources
rdc shader-map | grep -i "toon"             # Find draws using a shader
```

**"Why is this slow?"** (performance analysis):
```bash
rdc counters --json                         # GPU counters if available
rdc draws --sort duration --limit 10        # Top 10 longest draws (if timing available)
rdc stats                                   # Overall frame metrics
```

Then for each hotspot:
```bash
rdc pipeline <eid> --json                   # What state? How many targets?
rdc shader <eid> ps                         # How complex is the shader?
rdc bindings <eid>                          # How many resources bound?
```

**"Check state at draw X":**
```bash
rdc pipeline <eid> --json                   # Full state dump
rdc bindings <eid> --json                   # All bindings
rdc rt <eid> -o rt_check.png               # Visual check of output
```

### Phase 3: Deep Shader Analysis

```bash
rdc shader <eid> ps                         # Get shader source
rdc shader <eid> ps --constants             # + constant buffer values
rdc debug pixel <eid> <x> <y> --trace       # Step-by-step execution trace
```

For shader optimization:
```bash
rdc shader-build <eid> ps modified.hlsl     # Compile modified version
rdc shader-replace <eid> ps modified.hlsl   # Replace and see effect
rdc rt <eid> -o after.png                   # Check result
rdc shader-restore <eid> ps                 # Revert
```

### Phase 4: Comparison

```bash
rdc diff before.rdc after.rdc --draws       # What changed?
rdc diff before.rdc after.rdc --stats       # Performance delta?
rdc diff before.rdc after.rdc --pipeline 142 # State difference at specific draw?
```

### Phase 5: Reporting

Summarize findings:
> "## Frame Analysis Results
> **Capture**: {filename} ({API}, {GPU})
> **Focus**: {what was investigated}
>
> ### Findings
> 1. {finding with event ID}
> 2. {finding}
>
> ### Recommendations
> - {actionable recommendation}
>
> ### Data Exported
> - {exported files if any}"

---

## Integration with Rendering Bug Investigation

When diagnosing a rendering bug that requires frame-level investigation:

1. Ask user to provide a .rdc capture of the problematic frame
2. Open and analyze with focus on the hypothesis:
   - For "FBF/subpass issue" → check `rdc pipeline <eid> --json` for load/store actions, RT formats
   - For "shader fallback" → check `rdc shader <eid> ps` for unexpected variant
   - For "overdraw" → check `rdc draws` count per pass, depth test state
   - For "bandwidth" → check RT sizes, texture formats, unnecessary clears

---

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| `rdc: command not found` | Not installed | `cd <plugin>/ThirdParty/RdcCli && uv tool install .` |
| `renderdoc module not found` | Bundled binaries missing or Python version mismatch | Reinstall: `uv tool install . --force` (requires Python 3.12) |
| `No capture open` | No file loaded | `rdc open <file.rdc>` |
| `Event ID not found` | Invalid eid | Check valid IDs with `rdc events -q` |
| `Daemon connection failed` | Stale daemon | `rdc close` then `rdc open` again |
| `OpenCapture failed: ... E_INVALIDARG` | D3D12 GPU compatibility | rdc-cli auto-retries without forced GPU; if still fails, replay on the same machine that captured |
| `GPU counters unavailable` | Not captured with counters | Recapture with GPU counters enabled |
| `Binary content` on `rdc cat` | Tried to cat binary data | Use `-o file` to save instead |
| `active session exists` | Already have a capture open | Use `rdc close` first, or just proceed with current session |
| Chinese filename garbled | Windows bash encoding | Copy/rename .rdc to ASCII path, or use `cmd /c chcp 65001 && rdc open "..."` |

---

## Tips

- **Run `rdc_snapshot.py` first** — one call gives you session_active + info + stats + passes
- **Never blind-open** — always check session status before `rdc open`
- **Use `rdc script --code`** for batch operations (e.g., scanning 10 pixels in one call instead of 10 bash calls)
- **Use `rdc passes`** to see the high-level render pass structure — much more manageable than raw draw lists
- **Export PNGs for visual checks**: `rdc rt <eid> -o check.png` — then Read the PNG
- **VFS paths are stable**: `/draws/142/shader/ps` always works for the same capture

---

## Inline Code Execution

Use `rdc script --code` (or `-c`) to run Python inside the daemon without writing a temp file.
The code has access to `controller`, `rd`, `adapter`, `state` — same as `rdc script <file.py>`.

```bash
# Quick query
rdc script -c "print(len(controller.GetRootActions()))"

# Batch pixel scan (1 bash call instead of 10)
rdc script -c "
controller.SetFrameEvent(5942, True)
textures = controller.GetTextures()
for t in textures:
    if t.width >= 1000:
        print(f'{t.resourceId}  {t.width}x{t.height}  {t.format.Name()}')
"

# Scan pixels along a line
rdc script -c "
import renderdoc as rd
for y in range(318, 329):
    controller.SetFrameEvent(1210, True)
    # ... read texture data at each pixel
"
```

---

## Analysis Recipes

### Recipe: "为什么像素 (X,Y) 没有描边/颜色不对"

**Quick method** — use the pixel_compare.py script:
```bash
python <skill_dir>/scripts/pixel_compare.py <EID> <X_good> <Y_good> <X_bad> <Y_bad>
```

**Manual method:**

1. Find the target draw call:
   ```bash
   rdc draws | grep -i "PostProcess\|Outline"
   ```

2. Compare pixel values:
   ```bash
   rdc pixel <X> <Y_good> <EID> --json
   rdc pixel <X> <Y_bad> <EID> --json
   ```

3. Debug trace both pixels, diff to find divergence:
   ```bash
   rdc debug pixel <EID> <X> <Y_good> --trace > /tmp/good.tsv
   rdc debug pixel <EID> <X> <Y_bad> --trace > /tmp/bad.tsv
   diff /tmp/good.tsv /tmp/bad.tsv | head -40
   ```

4. Read shader disassembly + constants at the divergent instruction:
   ```bash
   rdc cat /draws/<EID>/shader/ps/disasm
   rdc cat /draws/<EID>/shader/ps/constants
   ```

### Recipe: "找到某个 pass 的所有 draw calls"

```bash
rdc passes                    # List all passes
rdc pass "<PASS_NAME>"        # Draws in that pass
```

### Recipe: "扫描一条线找颜色突变"

```bash
python <skill_dir>/scripts/edge_scan.py <EID> x=611 318 328
```

### Recipe: "导出 RT 看中间结果"

```bash
rdc rt <EID> -o /tmp/check.png
# Then use Read tool to view the PNG
```

### Recipe: "搜索特定 draw call"

```bash
python <skill_dir>/scripts/draw_search.py PostProcess Outline Shadow
```

---

## renderdoc Python API Quick Reference (v1.41+)

When using `rdc script <file.py>`, the script has access to `controller` (ReplayController), `rd` (renderdoc module), `adapter`, and `state`. This reference avoids common attribute name mistakes.

### CaptureFile (no replay needed)

```python
cap = rd.OpenCaptureFile()
cap.OpenFile(path, "", None)            # → ResultCode
cap.DriverName()                        # → str ("D3D12", "Vulkan", "OpenGL ES")
cap.GetSectionCount()                   # → int  (NOT SectionCount!)
cap.GetSectionProperties(i)             # → .name, .type, .uncompressedSize
cap.GetThumbnail(rd.FileType.PNG, 320)  # → .data (bytes), .width, .height
cap.OpenCapture(rd.ReplayOptions(), None) # → (ResultCode, ReplayController)
cap.Shutdown()
```

### ReplayController

```python
ctrl.GetRootActions()    # → list[ActionDescription]  (NOT GetDrawcalls!)
ctrl.GetResources()      # → list[ResourceDescription]
ctrl.GetTextures()       # → list[TextureDescription]
ctrl.GetBuffers()        # → list[BufferDescription]
ctrl.Shutdown()
```

### ActionDescription

```python
action.eventId           # int — unique event ID
action.actionId          # int — action sequence number
action.customName        # str — pass/draw name  (NOT .name!)
action.children          # list[ActionDescription]
action.flags             # ActionFlags  (NOT DrawFlags!)
action.numIndices        # int — vertex/index count
action.numInstances      # int
action.dispatchDimension # tuple (x, y, z) for compute
action.outputs           # tuple of ResourceId (render targets)
```

### ActionFlags

```python
rd.ActionFlags.Drawcall      # regular draw call
rd.ActionFlags.Dispatch      # compute dispatch
rd.ActionFlags.Clear         # clear operation
rd.ActionFlags.PushMarker    # begin marker/pass
rd.ActionFlags.SetMarker     # standalone marker
rd.ActionFlags.PassBoundary  # render pass boundary
```
