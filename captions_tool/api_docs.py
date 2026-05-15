"""API reference, written to a Text datablock on register and on demand.

Lives in a string constant so it can be regenerated, copied, and inspected
from any context (including headless MCP sessions via `bpy.data.texts`).
"""

CAPTIONS_README = """# Captions Add-on API

One Text object displays all dialogue lines. Each line has text, start, end.
Timing lives in keyframes on the object's custom property; the PropertyGroup
mirrors them. You can drag the keyframes in the dopesheet to retime.

## Quickstart for scripting / AI

```python
import bpy, json

dialogue = [
    {"text": "Hello there.",    "start": 1,  "end": 48},
    {"text": "General Kenobi.", "start": 60, "end": 96},
]
bpy.ops.captions.bulk_import(json_data=json.dumps(dialogue))
```

That single call creates the master Text object, loads all lines, and writes
the timing F-curve. Scrub the timeline to see the body change.

## Operators

### Setup
```python
bpy.ops.captions.create_master_object()
```
Idempotent. Auto-called by add_line and bulk_import.

### Add one line
```python
bpy.ops.captions.add_line(text="Hello", start=1, end=48)
```
If start or end is -1 (default), uses current frame and default_duration.

### Bulk import
```python
bpy.ops.captions.bulk_import(json_data='[{"text":"Hi","start":1,"end":48}]',
                             append=False)
```
Default replaces all existing lines. Set append=True to keep them.

### Edit
```python
bpy.ops.captions.remove_line()                   # removes scene.captions.active_index
bpy.ops.captions.set_active_frame(which='START') # or 'END'
bpy.ops.captions.clear_all()
```

### Introspection
```python
bpy.ops.captions.print_api()
# Then read bpy.data.texts["CAPTIONS_README"].as_string()
```

## Data model

```python
scene.captions.lines              # CollectionProperty
scene.captions.lines[0].id        # stable, auto-assigned -- DO NOT SET
scene.captions.lines[0].text
scene.captions.lines[0].start
scene.captions.lines[0].end
scene.captions.active_index
scene.captions.master_object      # PointerProperty -> the Text object
scene.captions.default_duration   # frames added past start when end is omitted
scene.captions.emission_strength  # white emission strength on the material
```

## Notes

- Overlapping lines: the later-starting line takes over when its start frame
  is reached. The dopesheet shows this directly.
- Edit start/end fields in the panel OR drag keyframes in the dopesheet --
  both stay in sync.
- The Text object is white emissive, parented to the active camera at the
  time of creation. You can re-parent or move it freely afterward.
"""
