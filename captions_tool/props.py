"""Captions data model.

A CaptionLine is the user-visible unit: text plus a start/end frame range.
Each line has a stable `id` (auto-assigned, never reused). The id is what the
timeline F-curve encodes, so the collection can be reordered or items deleted
without disturbing playback timing of unrelated lines.
"""
import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import PropertyGroup


def _on_gap_changed(self, context):
    """Rebuild the F-curve so the gap takes effect on existing lines."""
    # Late import: props.py is imported before operators.py at register time.
    from . import operators
    operators._rewrite(context.scene)


class CaptionLine(PropertyGroup):
    id: IntProperty()
    text: StringProperty(default="...")
    start: IntProperty(default=1, min=0)
    end: IntProperty(default=48, min=0)


class CaptionSettings(PropertyGroup):
    lines: CollectionProperty(type=CaptionLine)
    active_index: IntProperty()
    master_object: PointerProperty(type=bpy.types.Object)
    default_duration: IntProperty(default=48, min=1)
    next_id: IntProperty(default=1, min=1)
    auto_parent_to_camera: BoolProperty(default=True)
    emission_strength: bpy.props.FloatProperty(default=2.0, min=0.0)
    gap_frames: IntProperty(
        default=12,
        min=0,
        description=(
            "Blank frames inserted between adjacent dialogue lines (when one line "
            "ends exactly where the next begins). 0 = no automatic gap"
        ),
        update=_on_gap_changed,
    )
    filter_text: StringProperty(
        name="Filter",
        description="Show only lines containing this text (case-insensitive)",
    )


_CLASSES = (CaptionLine, CaptionSettings)


def register():
    for c in _CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.captions = PointerProperty(type=CaptionSettings)


def unregister():
    del bpy.types.Scene.captions
    for c in reversed(_CLASSES):
        bpy.utils.unregister_class(c)
