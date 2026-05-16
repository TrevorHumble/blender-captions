"""N-panel UI for editing captions."""
import bpy
from bpy.types import Panel, UIList

from . import master


class CAPTIONS_UL_lines(UIList):
    """Always-sorted-by-start-frame list with text-content filter."""

    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, "text", text="", emboss=False)
        row.label(text=f"{item.start}-{item.end}")

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        n = len(items)
        caps = context.scene.captions

        # Default: show everything
        flt_flags = [self.bitflag_filter_item] * n

        # Text filter (case-insensitive substring match on the line text)
        needle = caps.filter_text.strip().lower()
        if needle:
            for i, item in enumerate(items):
                if needle not in item.text.lower():
                    flt_flags[i] &= ~self.bitflag_filter_item

        # Sort: by start frame ascending. flt_neworder[i] = display position
        # of item i.
        sorted_indices = sorted(range(n), key=lambda idx: items[idx].start)
        flt_neworder = [0] * n
        for new_pos, orig_idx in enumerate(sorted_indices):
            flt_neworder[orig_idx] = new_pos

        return flt_flags, flt_neworder


class CAPTIONS_PT_main(Panel):
    bl_label = "Captions"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Captions"

    def draw(self, context):
        scene = context.scene
        caps = scene.captions
        layout = self.layout

        if master.get(scene) is None:
            layout.operator("captions.create_master_object", icon='ADD')
            return

        layout.operator(
            "captions.select_master",
            text="Select Captions Object",
            icon='RESTRICT_SELECT_OFF',
        )

        # Always-visible filter input (no triangle dropdown needed)
        layout.prop(caps, "filter_text", text="", icon='VIEWZOOM')

        row = layout.row()
        row.template_list(
            "CAPTIONS_UL_lines", "",
            caps, "lines",
            caps, "active_index",
            rows=4,
        )
        col = row.column(align=True)
        col.operator("captions.add_line", icon='ADD', text="")
        col.operator("captions.remove_line", icon='REMOVE', text="")
        col.separator()
        col.operator("captions.move_line", icon='TRIA_UP', text="").direction = 'UP'
        col.operator("captions.move_line", icon='TRIA_DOWN', text="").direction = 'DOWN'

        if 0 <= caps.active_index < len(caps.lines):
            line = caps.lines[caps.active_index]
            box = layout.box()
            box.prop(line, "text")
            r = box.row(align=True)
            r.prop(line, "start")
            r.operator("captions.set_active_frame", text="", icon='KEYFRAME').which = 'START'
            r = box.row(align=True)
            r.prop(line, "end")
            r.operator("captions.set_active_frame", text="", icon='KEYFRAME').which = 'END'


class CAPTIONS_PT_advanced(Panel):
    bl_label = "Advanced"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Captions"
    bl_parent_id = "CAPTIONS_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        caps = context.scene.captions
        layout = self.layout
        layout.prop(caps, "gap_frames", text="Gap frames")

        layout.separator()
        row = layout.row(align=True)
        row.prop(caps, "slip_amount", text="Slip frames")
        op = row.operator("captions.slip", text="Apply")
        op.frames = caps.slip_amount

        layout.separator()
        layout.operator("captions.print_api", text="Refresh API Reference", icon='HELP')
        layout.operator("captions.clear_all", text="Clear All Lines", icon='X')


_CLASSES = (CAPTIONS_UL_lines, CAPTIONS_PT_main, CAPTIONS_PT_advanced)


def register():
    for c in _CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(_CLASSES):
        bpy.utils.unregister_class(c)
