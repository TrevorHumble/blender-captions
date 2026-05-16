# Captions

A quick-and-dirty dialogue captions add-on for Blender animatics. One Text
object displays every line. Timing is keyframed and draggable in the
dopesheet. Scriptable via `bpy.ops` for headless, MCP, and AI-driven
authoring.

![Caption rendered in viewport](docs/florence.png)

## Why

Most animatic workflows route dialogue through the VSE or per-shot text
objects. Both pile up management overhead. This add-on collapses all dialogue
into one keyframed object: click it, see every line's start and end on the
timeline, drag to retime.

## Install

1. Grab [`dist/captions_tool-0.1.9.zip`](dist/captions_tool-0.1.9.zip) from this
   repo (also attached to the corresponding GitHub Release).
2. Blender → Edit → Preferences → Add-ons → Install... → pick the zip.
3. Enable "Animation: Captions".

If install fails with "already registered as a subclass" or similar, the
add-on is half-loaded from a previous attempt. Run
[`scripts/cleanup.py`](scripts/cleanup.py) from the Text Editor first, then
try installing again.

To rebuild the zip after editing the source:

```powershell
Compress-Archive -Force -Path .\captions_tool -DestinationPath .\dist\captions_tool-0.1.9.zip
```

## Use

Open the N-panel in the 3D viewport and find the **Captions** tab.

- **Create Master Object** appears until a captions text object exists. Click
  it to spawn the single Text object, white emissive, parented to the active
  camera at the bottom of frame.
- **Select Captions Object** selects + activates the master Text object so you
  can grab, rotate, or scale it directly.
- The **filter** input above the list does a case-insensitive substring match
  on line text. Always visible (no hidden dropdown).
- The dialogue list is **always displayed sorted by start frame**, regardless
  of the order you added the lines in.
- **+** adds a line at the current frame (end = start + `default_duration`,
  48 frames by default).
- **−** removes the active line.
- **▲ / ▼** swap the active line's start/end with its chronological neighbor.
  Pressing ▲ shifts that line earlier in playback, ▼ shifts it later.
- The active-line box has inline editing for text, start, and end. The
  keyframe-icon buttons snap start or end to the current playhead frame.
- **Drag keyframes in the dopesheet** to retime. The panel auto-syncs.

### Advanced (collapsed by default)

- **Gap frames** (default 12): when one line ends at exactly the same frame
  the next begins, a blank gap of this many frames is inserted automatically
  so the screen briefly clears between adjacent lines. Set to 0 to disable.
- **Refresh API Reference**: regenerates the `CAPTIONS_README` Text
  datablock (see "API reference" below).
- **Clear All Lines**: wipes the dialogue list and the F-curve.

## Script it

```python
import bpy, json

dialogue = [
    {"text": "SEBASTIAN: Paris?",      "start": 1,   "end": 36},
    {"text": "FLORENCE: No. San Antonio. Have you not been? The Riverwalk is gorgeous.",
                                       "start": 50,  "end": 146},
    {"text": "SEBASTIAN: What's wrong?","start": 160, "end": 195},
]
bpy.ops.captions.bulk_import(json_data=json.dumps(dialogue))
```

One call creates the master object, loads all lines, and writes the timing
F-curve. Scrub the timeline.

### API reference

After enabling the add-on a `CAPTIONS_README` Text datablock contains the full
API. Or call `bpy.ops.captions.print_api()` to regenerate it.

Operators (all under `bpy.ops.captions.*`):

| Operator | Purpose |
|---|---|
| `create_master_object` | Idempotent. Creates the single text object. |
| `select_master` | Selects + activates the master Text object in the viewport. |
| `add_line(text, start, end)` | Add one line. `start=-1` uses current frame. |
| `bulk_import(json_data, append=False)` | JSON array of `{text, start, end}`. |
| `remove_line` | Remove the active line. |
| `move_line(direction='UP'\|'DOWN')` | Swap active line's timing with chronological neighbor. |
| `set_active_frame(which='START'\|'END')` | Set active line's frame to current. |
| `clear_all` | Wipe all lines. |
| `print_api` | Write API docs to `bpy.data.texts["CAPTIONS_README"]`. |

## How it works (architecture)

- **One Text object** named `Captions`, parented to the active camera with
  text-box wrapping sized from the camera frustum.
- **One F-curve** on a custom `caption_idx` integer property, CONSTANT
  interpolation. Each line contributes one keyframe at its start with
  `value=line_id`; a `-1` sentinel marks each end where no other line takes
  over. Lines are addressed by stable id, not collection position, so reorder
  and delete don't disturb the F-curve.
- **`frame_change_pre` handler** reads the F-curve value at the current frame
  and writes `text.body = lines[id].text`.
- **`depsgraph_update_post` handler** back-syncs dopesheet drags into the
  PropertyGroup so the panel always matches what plays.

The `timeline.py` module is the only place that knows the encoding. Every
other module talks to it through `write`, `read`, `active_line_id`.

## Compatibility

- Blender 4.2+ (tested on 5.1).
- Render engines: EEVEE, EEVEE Next, Cycles (text is emissive, ignores
  shadows).

## License

MIT
