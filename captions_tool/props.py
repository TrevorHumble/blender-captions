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


def _on_flip_orientation_changed(self, context):
    """Re-orient the existing master when the user flips the toggle."""
    scene = context.scene
    obj = scene.captions.master_object
    if obj is None:
        return
    sx = abs(obj.scale.x)
    obj.scale.x = -sx if scene.captions.flip_orientation else sx


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
    flip_orientation: BoolProperty(
        default=False,
        description="If captions look mirrored from the camera, toggle this on",
        update=_on_flip_orientation_changed,
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
