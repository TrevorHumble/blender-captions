---
name: headless-captions
description: >
  Generate dialogue captions in Blender animatic .blend files without opening
  the UI. Use this skill when the user wants to batch-caption a folder of
  shots, drive the captions addon from an AI pipeline, generate subtitles
  from a script, or otherwise script the blender-captions addon. Trigger
  when the user says "headless captions," "batch caption blender,"
  "captions for multiple shots," "automate dialogue," "captions via MCP,"
  or mentions Blender background mode in the same breath as captions.
---

# Headless Captions for Blender

The `blender-captions` add-on (https://github.com/TrevorHumble/blender-captions)
exposes its full feature set through `bpy.ops.captions.*`. None of the
operators require a 3D viewport context. Anything you do in the N-panel can
be done from a Python script run via `blender --background --python`.

## Quickstart

Single file, one call:

```python
import bpy, json

dialogue = [
    {"text": "SEBASTIAN: Paris?",       "start": 1,   "end": 36},
    {"text": "FLORENCE: No. San Antonio. Have you not been? The Riverwalk is gorgeous.",
                                        "start": 50,  "end": 146},
    {"text": "SEBASTIAN: What's wrong?", "start": 160, "end": 195},
]
bpy.ops.captions.bulk_import(json_data=json.dumps(dialogue))
bpy.ops.wm.save_mainfile()
```

`bulk_import` is idempotent and self-bootstrapping. It creates the master
Text object if missing, parents it to the active camera, and writes the
F-curve. By default it replaces existing lines; pass `append=True` to keep
them.

## Batch script (process a folder of .blend files)

```python
"""Run via:
    blender --background --python batch_captions.py
"""
import bpy, json, os, glob

# Map of blend filename stem -> dialogue list
DIALOGUE = {
    "shot_010": [
        {"text": "SEBASTIAN: Paris?", "start": 1, "end": 36},
        # ...
    ],
    "shot_020": [
        # ...
    ],
}

BLEND_DIR = "/path/to/animatic/shots"
OUT_DIR   = "/path/to/renders"

for blend_path in glob.glob(os.path.join(BLEND_DIR, "*.blend")):
    stem = os.path.splitext(os.path.basename(blend_path))[0]
    if stem not in DIALOGUE:
        continue

    bpy.ops.wm.open_mainfile(filepath=blend_path)
    bpy.ops.captions.bulk_import(json_data=json.dumps(DIALOGUE[stem]))
    bpy.ops.wm.save_mainfile()

    # Optional: render the animatic
    bpy.context.scene.render.filepath = os.path.join(OUT_DIR, f"{stem}_")
    bpy.context.scene.render.image_settings.file_format = 'FFMPEG'
    bpy.ops.render.render(animation=True)
```

Launch:
```
blender --background --python batch_captions.py
```

## Operator reference

All under `bpy.ops.captions.*`. Return `{'FINISHED'}` on success,
`{'CANCELLED'}` on rejected input.

| Operator | Args | Notes |
|---|---|---|
| `create_master_object` | — | Idempotent. Spawns the master Text object and parents it to the active camera. Auto-called by `add_line` and `bulk_import`. |
| `add_line` | `text: str, start: int=-1, end: int=-1` | `start=-1` uses `scene.frame_current`; `end=-1` uses `start + scene.captions.default_duration`. |
| `bulk_import` | `json_data: str, append: bool=False` | JSON array of `{text, start, end}`. Default replaces; `append=True` to add to existing lines. |
| `remove_line` | — | Removes `scene.captions.lines[scene.captions.active_index]`. |
| `move_line` | `direction: 'UP'\|'DOWN'` | Swaps timing with the chronological neighbor. |
| `set_active_frame` | `which: 'START'\|'END'` | Sets the active line's start or end to `scene.frame_current`. |
| `clear_all` | — | Wipes the dialogue list and the F-curve. |
| `select_master` | — | UI-only; no-op in headless mode. |
| `print_api` | — | Writes the API reference to `bpy.data.texts["CAPTIONS_README"]`. Useful when an AI agent needs to discover the API. |

## Data model (read-only inspection)

```python
caps = bpy.context.scene.captions

caps.lines               # CollectionProperty -- iterate in any order
for line in caps.lines:
    print(line.id, line.text, line.start, line.end)

caps.master_object       # PointerProperty -> the Text object (or None)
caps.default_duration    # int, frames added past start when end is omitted
caps.gap_frames          # int, blank frames between adjacent abutting lines
caps.emission_strength   # float, white emission strength on the material
```

## Setup requirements

1. **Blender 4.2+** (tested through 5.1).
2. The `captions_tool` add-on must be **installed and enabled** in the
   Blender instance running headless. In a fresh container, this means
   either:
   - Drop the `captions_tool/` folder into Blender's `scripts/addons/`
     directory, then enable it once interactively so the preference is
     persisted, OR
   - Install via a bootstrap script:
     ```python
     import bpy
     bpy.ops.preferences.addon_install(filepath="/path/to/captions_tool-0.1.7.zip")
     bpy.ops.preferences.addon_enable(module="captions_tool")
     bpy.ops.wm.save_userpref()
     ```

## Verifying that captions were written

After `bulk_import`, you can inspect the F-curve directly:

```python
from captions_tool.timeline import _iter_fcurves

m = bpy.context.scene.captions.master_object
for _container, fc in _iter_fcurves(m.animation_data.action):
    if fc.data_path == '["caption_idx"]':
        for kp in fc.keyframe_points:
            print(f"frame={kp.co.x:.0f} value={kp.co.y:.0f} type={kp.type}")
```

You should see one positive-valued keyframe per line (the line's `id`) plus
sentinel `-1` keyframes at each line's end where no other line takes over,
all with `interpolation='CONSTANT'` and `type='BREAKDOWN'`.

To verify the rendered body at a given frame:

```python
bpy.context.scene.frame_set(50)
print(bpy.context.scene.captions.master_object.data.body)
```

## Known limitations in headless mode

- `select_master` has no effect (no viewport).
- The `CAPTIONS_README` text datablock is upserted via a deferred timer. In
  batch scripts that exit fast, it may not appear. Call
  `bpy.ops.captions.print_api()` explicitly if you need it.
- The `depsgraph_update_post` drag-sync handler isn't useful headless
  (there's nothing to drag), but it doesn't hurt either.

## Driving from an MCP / Claude Code session

If you're connecting to a running Blender via MCP (e.g., the `blender` MCP
server's `execute_blender_code` tool), the same operators work. The
difference is that MCP runs inside an interactive Blender process, so the
viewport is live and you can take screenshots to verify your captions
visually.

Pattern: call `bpy.ops.captions.bulk_import(...)`, then `scene.frame_set(N)`,
then read `master_object.data.body` to confirm the right line is showing.
The frame_change_pre handler updates the body synchronously during
`frame_set`.

## When NOT to use headless mode

- Authoring dialogue from scratch by ear (use the N-panel; the modal
  set-start/set-end buttons are faster).
- Retiming by feel (drag keyframes in the dopesheet).

Headless is for batch operations, AI-driven authoring, and CI-style
pipelines where dialogue comes from another source (a script, an SRT file,
an LLM, a database) and just needs to be loaded into Blender.
