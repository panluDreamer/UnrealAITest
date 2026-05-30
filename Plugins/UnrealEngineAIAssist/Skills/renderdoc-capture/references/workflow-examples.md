# rdc-cli Workflow Examples

Concrete examples for common RenderDoc frame analysis tasks.

---

## 1. Find the Most Expensive Draw Calls

```bash
# Open capture
rdc open D:\captures\game_frame.rdc

# Check if GPU counters are available
rdc counters --json 2>/dev/null || echo "No GPU counters in this capture"

# List all draws sorted by duration (if counters available)
rdc draws --sort duration --limit 10

# Alternative: look at draw complexity indicators
rdc draws --json | python -c "
import json, sys
draws = json.load(sys.stdin)
for d in sorted(draws, key=lambda x: x.get('num_indices', 0), reverse=True)[:10]:
    print(f\"EID {d['eid']:>6}  indices={d.get('num_indices',0):>8}  {d['name']}\")
"

# Deep dive on the worst offender
rdc pipeline 4521 --json   # Check: how many render targets? MSAA? Blend enabled?
rdc shader 4521 ps         # How complex is the pixel shader?
rdc bindings 4521          # How many textures/buffers bound?
```

---

## 2. Debug Why a Render Target is Black

```bash
rdc open D:\captures\black_screen.rdc

# Step 1: Find the final present / backbuffer write
rdc passes                              # See render pass structure
rdc draws | tail -20                    # Last 20 draws (near present)

# Step 2: Check the last draw that writes to the backbuffer
rdc pipeline <last_eid> --json          # Are render targets bound?
rdc rt <last_eid> -o final_output.png   # Export to see what's there

# Step 3: Walk backwards through passes to find where it goes black
rdc rt <eid_pass_N> -o pass_n.png       # Check each pass output
rdc rt <eid_pass_N-1> -o pass_n1.png    # Previous pass

# Step 4: Once you find the problematic pass, check its draws
rdc pass "PostProcess"                  # Draws in that pass
rdc pipeline <problem_eid> --json       # Viewport correct? Scissor? Blend?
rdc shader <problem_eid> ps             # Shader returning (0,0,0,0)?

# Step 5: Check input resources
rdc bindings <problem_eid> --json       # What textures are bound?
rdc tex-stats <input_texture_id>        # Is the input texture empty/zero?
```

---

## 3. Compare Two Captures (Before/After Optimization)

```bash
# Quick stats comparison
rdc diff before.rdc after.rdc --stats

# Draw call differences (added/removed/changed)
rdc diff before.rdc after.rdc --draws

# Show only changed draws (marked with ~)
rdc diff before.rdc after.rdc --draws | grep '~'

# Compare pipeline state at a specific draw
rdc diff before.rdc after.rdc --pipeline 142

# Compare render target output visually
rdc open before.rdc
rdc rt 142 -o before_rt.png
rdc close

rdc open after.rdc
rdc rt 142 -o after_rt.png
rdc close
```

---

## 4. Extract All Shaders in a Render Pass

```bash
rdc open scene.rdc

# List passes to find the one we want
rdc passes

# Get all draws in the target pass
rdc pass "GBuffer" -q                   # Get draw EIDs only

# Extract pixel shaders from each draw
for eid in $(rdc pass "GBuffer" -q); do
    echo "=== Event $eid ==="
    rdc shader $eid ps 2>/dev/null || echo "(no pixel shader)"
done

# Or get the unique shader mapping
rdc shader-map | grep "GBuffer"

# List all unique shaders in the frame
rdc shaders
```

---

## 5. Check Pixel Value at Specific Coordinates

```bash
rdc open capture.rdc

# Read pixel value at (400, 300) at draw 500
rdc pixel 500 400 300

# Read from current output (after all draws)
rdc pick-pixel 400 300

# Assert pixel matches expected value (CI use)
rdc assert-pixel 500 400 300 1.0 0.0 0.0 1.0   # Expect red
echo "Exit code: $?"                              # 0=match, 1=mismatch

# Debug: trace shader execution for that pixel
rdc debug pixel 500 400 300 --trace
```

---

## 6. Investigate Overdraw in a Mobile Game

```bash
rdc open mobile_frame.rdc

# Frame overview
rdc stats                               # Total draw count
rdc passes                              # Pass structure

# Count draws per pass
for pass_name in $(rdc passes -q); do
    count=$(rdc pass "$pass_name" -q | wc -l)
    echo "$pass_name: $count draws"
done

# Check depth test/write state for opaque pass
rdc pass "ForwardOpaque" -q | while read eid; do
    # Check if depth test is enabled
    rdc cat /draws/$eid/pipeline/depth 2>/dev/null
done

# Check blend state for transparent pass (should be sorted back-to-front)
rdc pass "Translucent" -q | while read eid; do
    rdc cat /draws/$eid/pipeline/blend 2>/dev/null
done

# Export render target at key points to visualize
rdc rt <after_opaque_eid> -o opaque_result.png
rdc rt <after_translucent_eid> -o translucent_result.png
```

---

## 7. Shader Edit and Test

```bash
rdc open buggy_frame.rdc

# Get current shader
rdc shader 200 ps > original_shader.hlsl

# Edit the shader (fix the bug)
# ... modify original_shader.hlsl ...

# Check available encodings
rdc shader-encodings 200 ps

# Build the modified shader
rdc shader-build 200 ps fixed_shader.hlsl

# Replace and see the result
rdc shader-replace 200 ps fixed_shader.hlsl
rdc rt 200 -o after_fix.png

# Compare with original
rdc shader-restore 200 ps
rdc rt 200 -o before_fix.png

# Restore everything when done
rdc shader-restore-all
```

---

## 8. Android Remote Capture

```bash
# Setup injection for an Android app
rdc android setup com.example.mygame

# Launch the app on device, then trigger capture
rdc android capture com.example.mygame

# Wait for capture, then list and download
rdc capture-list
rdc capture-copy 0 -o android_frame.rdc

# Analyze locally
rdc open android_frame.rdc
rdc info
rdc stats
rdc draws | head -20

# Clean up
rdc android stop com.example.mygame
```

---

## 9. VFS Navigation for Quick Exploration

```bash
rdc open scene.rdc

# Explore the capture structure
rdc ls /
rdc tree /draws/142

# Quick access to specific data
rdc cat /draws/142/shader/ps         # Pixel shader source
rdc cat /draws/142/pipeline/blend    # Blend state
rdc cat /draws/142/pipeline/depth    # Depth-stencil state
rdc cat /info                        # Capture info
rdc cat /stats                       # Frame stats

# Check all targets at a draw
rdc ls /draws/142/targets/
rdc cat /draws/142/targets/0         # First color target info
```

---

## 10. CI Pipeline Assertions

```bash
#!/bin/bash
# ci_gpu_check.sh — Run after capturing a reference frame

rdc open test_frame.rdc

# Assert no API errors
rdc assert-clean || exit 1

# Assert draw count is reasonable
rdc assert-count draws "<=" 500 || exit 1

# Assert specific pixel color (UI element should be visible)
rdc assert-pixel 1000 128 64 1.0 1.0 1.0 1.0 || exit 1

# Assert render target matches reference
rdc assert-image 1000 reference_output.png || exit 1

# Assert depth test is enabled for opaque draws
rdc assert-state 200 /draws/200/pipeline/depth "enabled=true" || exit 1

echo "All GPU checks passed"
rdc close
```

---

## 11. Inline Code for Batch Analysis

Use `rdc script --code` (or `-c`) to run Python directly inside the daemon,
avoiding multiple CLI round-trips.

```bash
rdc open capture.rdc

# Count all draw calls with more than 1000 triangles
rdc script -c "
actions = adapter.flat_draws()
heavy = [a for a in actions if a.numIndices > 1000]
print(f'{len(heavy)} draws with >1000 triangles')
for a in heavy[:10]:
    print(f'  EID {a.eventId}: {a.numIndices} indices  {a.customName}')
"

# Scan pixels along a vertical line to find color transitions
rdc script -c "
import renderdoc as rd, struct
controller.SetFrameEvent(1210, True)
textures = controller.GetTextures()
resources = controller.GetResources()
name_map = {r.resourceId: r.name for r in resources}
for t in textures:
    if t.width >= 1000 and t.height >= 500:
        print(f'{t.resourceId}  {t.width}x{t.height}  {t.format.Name()}  {name_map.get(t.resourceId, \"\")}')
"

# Read texture data at specific pixels (batch, one CLI call)
rdc script -c "
import renderdoc as rd
for eid in [500, 600, 700, 800]:
    controller.SetFrameEvent(eid, True)
    state = controller.GetPipelineState()
    targets = state.GetOutputTargets()
    if targets:
        print(f'EID {eid}: {len(targets)} render targets')
"
```
