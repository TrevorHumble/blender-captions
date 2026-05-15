---
name: headless-captions
description: >
  Seed dialogue captions across a folder of Blender animatic .blend files
  from a dialogue script. Operates interactively in propose-then-act mode:
  the agent proposes a script-to-shot mapping and timing, the user approves,
  then the agent backs everything up and writes the captions. Halts on any
  error and waits for instructions instead of silently skipping or guessing.
  Trigger when the user says "caption these shots from this script,"
  "batch caption blender," "seed captions in my animatic," "automate
  dialogue placement," or hands the agent a dialogue script + a folder of
  .blend files.
---

# Headless Captions for Blender

This skill drives the `blender-captions` add-on
(https://github.com/TrevorHumble/blender-captions) to seed initial dialogue
captions across a folder of animatic shots. The user finishes the timing by
hand during animation; the goal here is to get every line of dialogue into
the right shot so the animator isn't starting from a blank file.

The operating mode is **propose then act**:

1. Collect inputs from the user.
2. Propose a script-to-shot mapping.
3. Wait for approval.
4. Back up every .blend that will be touched.
5. Write captions, one shot at a time.
6. Halt on any error and wait for the user's decision.
7. Report a plain-text summary at the end.

Never silently guess, skip, or replace. When in doubt, ask.

## 1. Inputs to collect before doing anything

Ask the user for these before reading or writing a single file. Do not fall
back to defaults from your training data, your operating system, or this
skill — every path is user-specific.

- **Blender executable path** (`<BLENDER_EXE>`). Example placeholder:
  `<BLENDER_EXE>` could be `C:\Program Files\Blender Foundation\Blender 5.1\blender.exe`
  on Windows, `/Applications/Blender.app/Contents/MacOS/Blender` on macOS,
  `/usr/bin/blender` on Linux. The user must confirm the actual path.
- **captions_tool zip path** (`<ADDON_ZIP>`). The user provides this.
- **.blend folder** (`<BLEND_DIR>`). The directory containing the shot
  files to caption.
- **Dialogue script**. Plain-text content or a path to a `.txt`, `.md`,
  or `.srt` file. Whatever the user has.
- **Project frame rate** (`<FPS>`). Default to 24 only if the user
  explicitly declines to specify.

Echo each value back before proceeding so the user can correct a typo.

## 2. Propose a script-to-shot mapping

List the .blend filenames in `<BLEND_DIR>`. Read the dialogue script.
Build a proposal that maps script lines (or groups of lines) to specific
.blend files. Present in plain text:

```
Proposed mapping:

  shot_010.blend
    SEBASTIAN: "Paris?"
    FLORENCE: "No. San Antonio. Have you not been? The Riverwalk is gorgeous."

  shot_020.blend
    SEBASTIAN: "What's wrong?"

  shot_030.blend
    (no dialogue mapped)

Approve? (yes / changes / ask me a question)
```

Wait for the user's response. If they ask for changes, apply them and
re-present. If a line truly doesn't fit any shot, ask a specific question
("Line N reads: '...'. Which shot does this belong to?") rather than
guessing.

## 3. Pre-flight backup

After mapping is approved and before any write:

1. Look in `<BLEND_DIR>` for an existing `_backup_*` directory.
2. If none exists, create `<BLEND_DIR>/_backup_<ISO timestamp>/`.
3. Copy every .blend that will be touched into the backup folder.
4. Verify each backup file exists and matches the source size.
5. If verification fails, halt and report which file failed; do not proceed.

The user handles revert manually if files later appear corrupted. Don't
auto-revert.

## 4. Frame math

24 fps is the default. Use `<FPS>` if the user provided one. Inside Blender,
the runtime fps is `scene.render.fps / scene.render.fps_base`.

For each shot, estimate a start frame for each line based on natural pacing
and any cues in the script (e.g., explicit timestamps if the script is
SRT-formatted). End frame is left to the addon's `default_duration` setting
(48 frames at 24 fps = 2 seconds) — pass `end=-1` to `add_line` and the
addon fills it in.

Do NOT try to clamp captions to `scene.frame_end`. The shot files may have
default frame ranges that don't reflect actual content yet. Trevor's
pipeline retimes by hand during animation.

This is a rough seed, not finished timing.

## 5. Write captions

For each shot in the approved mapping:

```python
import bpy, json, sys

# Open the .blend
bpy.ops.wm.open_mainfile(filepath=blend_path)

# REFUSE if the file already has captions -- the agent has no business
# overwriting them. Halt and report.
if len(bpy.context.scene.captions.lines) > 0:
    raise RuntimeError(
        f"{blend_path}: already has {len(bpy.context.scene.captions.lines)} "
        "caption lines. Refusing to overwrite. Awaiting user decision."
    )

# Import the lines for this shot. Each entry uses the agent's best
# estimation for `start`; `end=-1` lets the addon use default_duration.
lines = [
    {"text": "SEBASTIAN: Paris?", "start": 12, "end": -1},
    # ...
]
result = bpy.ops.captions.bulk_import(json_data=json.dumps(lines))
if result != {'FINISHED'}:
    raise RuntimeError(f"{blend_path}: bulk_import returned {result}")

# Save -- not optional.
bpy.ops.wm.save_mainfile()
```

## 6. Halt-on-error policy

Any of the following stop the batch and return control to the user:

- A .blend in `<BLEND_DIR>` was not mapped to any dialogue.
- A .blend already has caption lines in it.
- `bulk_import` returns `{'CANCELLED'}` or any operator raises.
- A backup write fails its size check.
- A save fails.

Report the file, the operation, and the error message. Wait for the user
to say one of: **continue** (skip this file, proceed with the rest),
**retry** (run the same step again — useful after a manual fix in
Blender), or **stop** (abort the batch entirely).

Do not invent a fourth option. Do not "try once more" without instruction.

## 7. Final report

When the run completes (or aborts), print a plain-text summary:

```
Backup folder: <BLEND_DIR>/_backup_2026-05-15T11-30-00/

Approved mapping:
  shot_010.blend ← 2 lines
  shot_020.blend ← 1 line
  shot_030.blend ← (none mapped, would have errored)

Results:
  shot_010.blend: OK (2 lines written, saved)
  shot_020.blend: OK (1 line written, saved)
  shot_030.blend: HALTED -- not in approved mapping
  shot_040.blend: HALTED -- already had 5 caption lines

Totals: 2 captioned, 0 skipped silently, 2 halted, 0 errored.
```

## Operator reference

All under `bpy.ops.captions.*`. Return `{'FINISHED'}` on success,
`{'CANCELLED'}` on rejected input.

| Operator | Args | Notes |
|---|---|---|
| `create_master_object` | — | Idempotent. Auto-called by `add_line` and `bulk_import`. |
| `add_line` | `text: str, start: int=-1, end: int=-1` | `start=-1` uses `scene.frame_current`; `end=-1` uses `scene.captions.default_duration` past start. |
| `bulk_import` | `json_data: str, append: bool=False` | JSON array of `{text, start, end}`. Default replaces existing lines. This skill never passes `append=True`; refuse the operation if the file already has captions. |
| `remove_line` | — | Removes `scene.captions.lines[scene.captions.active_index]`. |
| `move_line` | `direction: 'UP'\|'DOWN'` | Swaps timing with chronological neighbor. Not used by this skill. |
| `set_active_frame` | `which: 'START'\|'END'` | Sets the active line's frame to current. Not used by this skill. |
| `clear_all` | — | Wipes the dialogue list and the F-curve. Not used by this skill. |
| `select_master` | — | UI-only, no-op headless. Not used. |
| `print_api` | — | Writes the API reference to `bpy.data.texts["CAPTIONS_README"]`. |

## Data model (read-only inspection)

```python
caps = bpy.context.scene.captions

caps.lines               # CollectionProperty
for line in caps.lines:
    print(line.id, line.text, line.start, line.end)

caps.master_object       # PointerProperty -> the Text object (or None)
caps.default_duration    # int, frames added past start when end is omitted
caps.gap_frames          # int, blank frames between adjacent abutting lines
caps.emission_strength   # float, white emission strength on the material
```

## Setup requirements

1. Blender 4.2+.
2. The captions_tool add-on must be installed and enabled in the Blender
   instance running headless. To bootstrap into a clean Blender:

```python
import bpy
bpy.ops.preferences.addon_install(filepath="<ADDON_ZIP>")
bpy.ops.preferences.addon_enable(module="captions_tool")
bpy.ops.wm.save_userpref()
```

Replace `<ADDON_ZIP>` with the user-provided path (current build is
`captions_tool-0.1.8.zip`).

## Verifying captions landed correctly

```python
from captions_tool.timeline import _iter_fcurves

m = bpy.context.scene.captions.master_object
for _container, fc in _iter_fcurves(m.animation_data.action):
    if fc.data_path == '["caption_idx"]':
        for kp in fc.keyframe_points:
            print(f"frame={kp.co.x:.0f} value={kp.co.y:.0f} type={kp.type}")
```

Expect one positive-valued keyframe per line plus `-1` sentinels at each
line's end, all with `interpolation='CONSTANT'` and `type='BREAKDOWN'`.

Read the rendered body at a given frame:

```python
bpy.context.scene.frame_set(50)
print(bpy.context.scene.captions.master_object.data.body)
```

## Invocation

The user runs this from a shell:

```
<BLENDER_EXE> --background --python <YOUR_SCRIPT>.py
```

Where `<YOUR_SCRIPT>.py` is the file the agent writes to drive the batch.

## Out of scope

- SRT parsing beyond extracting timestamps if present (a richer SRT
  importer is a planned addon feature, not this skill's job).
- Audio-based retiming.
- Rendering the animatic.
- Clamping captions to `scene.frame_end`.
- Silent fallbacks of any kind.

If the user asks for any of the above, say so and stop.
