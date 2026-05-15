"""User-facing operators.

Every operator works without a 3D viewport context, so the add-on is callable
headless via bpy.ops from MCP / script-driven sessions.
"""
import json

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty
from bpy.types import Operator

from . import api_docs, handlers, master, timeline


def _allocate_id(scene):
    nid = scene.captions.next_id
    scene.captions.next_id = nid + 1
    return nid


def _rewrite(scene):
    m = master.get(scene)
    if m is None:
        return
    handlers.begin_write()
    try:
        timeline.write(m, scene.captions.lines, scene.captions.gap_frames)
    finally:
        handlers.end_write()


class CAPTIONS_OT_create_master_object(Operator):
    """Create the single Text object that displays all captions."""
    bl_idname = "captions.create_master_object"
    bl_label = "Create Master Object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        master.create(context.scene)
        return {'FINISHED'}


class CAPTIONS_OT_add_line(Operator):
    """Add a dialogue line. Auto-creates the master object."""
    bl_idname = "captions.add_line"
    bl_label = "Add Line"
    bl_options = {'REGISTER', 'UNDO'}

    text: StringProperty(default="New line")
    start: IntProperty(default=-1, description="-1 means use current frame")
    end: IntProperty(default=-1, description="-1 means start + default duration")

    def execute(self, context):
        scene = context.scene
        master.create(scene)
        s = self.start if self.start >= 0 else scene.frame_current
        e = self.end if self.end >= 0 else s + scene.captions.default_duration

        line = scene.captions.lines.add()
        line.id = _allocate_id(scene)
        line.text = self.text
        line.start = s
        line.end = e
        scene.captions.active_index = len(scene.captions.lines) - 1
        _rewrite(scene)
        return {'FINISHED'}


class CAPTIONS_OT_remove_line(Operator):
    """Remove the active dialogue line."""
    bl_idname = "captions.remove_line"
    bl_label = "Remove Line"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        i = scene.captions.active_index
        if i < 0 or i >= len(scene.captions.lines):
            return {'CANCELLED'}
        scene.captions.lines.remove(i)
        scene.captions.active_index = max(0, min(i, len(scene.captions.lines) - 1))
        _rewrite(scene)
        return {'FINISHED'}


class CAPTIONS_OT_set_active_frame(Operator):
    """Set the active line's start or end to the current frame."""
    bl_idname = "captions.set_active_frame"
    bl_label = "Set Frame"
    bl_options = {'REGISTER', 'UNDO'}

    which: EnumProperty(
        items=[('START', "Start", ""), ('END', "End", "")],
        default='START',
    )

    def execute(self, context):
        scene = context.scene
        i = scene.captions.active_index
        if i < 0 or i >= len(scene.captions.lines):
            return {'CANCELLED'}
        line = scene.captions.lines[i]
        if self.which == 'START':
            line.start = scene.frame_current
        else:
            line.end = scene.frame_current
        _rewrite(scene)
        return {'FINISHED'}


class CAPTIONS_OT_move_line(Operator):
    """Swap the active line's timing with its chronological neighbor.

    The list is always displayed sorted by start frame, so 'Up' swaps timing
    with the line that plays just before this one and 'Down' swaps with the
    line that plays just after. Collection order is left alone -- the
    UIList's filter_items re-sorts the display automatically.
    """
    bl_idname = "captions.move_line"
    bl_label = "Move Line"
    bl_options = {'REGISTER', 'UNDO'}

    direction: EnumProperty(
        items=[('UP', "Up", ""), ('DOWN', "Down", "")],
        default='UP',
    )

    def execute(self, context):
        caps = context.scene.captions
        i = caps.active_index
        n = len(caps.lines)
        if i < 0 or i >= n:
            return {'CANCELLED'}

        # Walk the list in start-frame order to find the chronological neighbor
        sorted_indices = sorted(range(n), key=lambda idx: caps.lines[idx].start)
        display_pos = sorted_indices.index(i)
        target_display = display_pos - 1 if self.direction == 'UP' else display_pos + 1
        if target_display < 0 or target_display >= n:
            return {'CANCELLED'}
        target = sorted_indices[target_display]

        # Swap timings (text and id stay put)
        a_start, a_end = caps.lines[i].start, caps.lines[i].end
        b_start, b_end = caps.lines[target].start, caps.lines[target].end
        caps.lines[i].start, caps.lines[i].end = b_start, b_end
        caps.lines[target].start, caps.lines[target].end = a_start, a_end

        _rewrite(context.scene)
        return {'FINISHED'}


class CAPTIONS_OT_select_master(Operator):
    """Select the captions text object in the viewport so you can grab,
    rotate, or scale it. Re-links the object to the active scene if a
    previous outliner delete left it orphaned.
    """
    bl_idname = "captions.select_master"
    bl_label = "Select Captions Object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        m = master.get(scene)
        if m is None:
            self.report({'WARNING'}, "No captions object exists yet.")
            return {'CANCELLED'}

        # If the object got orphaned (deleted from outliner while a
        # PointerProperty held a reference), re-link it before selecting.
        if scene not in m.users_scene:
            scene.collection.objects.link(m)

        for obj in context.view_layer.objects:
            obj.select_set(obj is m)
        context.view_layer.objects.active = m
        return {'FINISHED'}


class CAPTIONS_OT_bulk_import(Operator):
    """Bulk-load dialogue from a JSON array of {text, start, end} objects."""
    bl_idname = "captions.bulk_import"
    bl_label = "Bulk Import"
    bl_options = {'REGISTER', 'UNDO'}

    json_data: StringProperty(description="JSON array of {text, start, end} objects")
    append: BoolProperty(default=False, description="Append instead of replacing")

    def execute(self, context):
        scene = context.scene
        try:
            data = json.loads(self.json_data)
        except json.JSONDecodeError as exc:
            self.report({'ERROR'}, f"JSON parse error: {exc}")
            return {'CANCELLED'}
        if not isinstance(data, list):
            self.report({'ERROR'}, "Expected a JSON array")
            return {'CANCELLED'}

        master.create(scene)
        if not self.append:
            scene.captions.lines.clear()

        count = 0
        for entry in data:
            if not isinstance(entry, dict):
                continue
            text = str(entry.get("text", ""))
            start = int(entry.get("start", scene.frame_current))
            end = int(entry.get("end", start + scene.captions.default_duration))
            line = scene.captions.lines.add()
            line.id = _allocate_id(scene)
            line.text = text
            line.start = start
            line.end = end
            count += 1

        scene.captions.active_index = max(0, len(scene.captions.lines) - 1)
        _rewrite(scene)
        self.report({'INFO'}, f"Imported {count} lines")
        return {'FINISHED'}


class CAPTIONS_OT_clear_all(Operator):
    """Clear all dialogue lines."""
    bl_idname = "captions.clear_all"
    bl_label = "Clear All"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        scene.captions.lines.clear()
        scene.captions.active_index = 0
        _rewrite(scene)
        m = master.get(scene)
        if m is not None:
            m.data.body = ""
        return {'FINISHED'}


class CAPTIONS_OT_print_api(Operator):
    """Write the API reference to a CAPTIONS_README text datablock."""
    bl_idname = "captions.print_api"
    bl_label = "Print API"

    def execute(self, context):
        name = "CAPTIONS_README"
        readme = bpy.data.texts.get(name)
        if readme is None:
            readme = bpy.data.texts.new(name)
        readme.clear()
        readme.write(api_docs.CAPTIONS_README)
        self.report({'INFO'}, f"Wrote {name}. See Text Editor.")
        return {'FINISHED'}


_CLASSES = (
    CAPTIONS_OT_create_master_object,
    CAPTIONS_OT_select_master,
    CAPTIONS_OT_add_line,
    CAPTIONS_OT_remove_line,
    CAPTIONS_OT_move_line,
    CAPTIONS_OT_set_active_frame,
    CAPTIONS_OT_bulk_import,
    CAPTIONS_OT_clear_all,
    CAPTIONS_OT_print_api,
)


def register():
    for c in _CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(_CLASSES):
        bpy.utils.unregister_class(c)
