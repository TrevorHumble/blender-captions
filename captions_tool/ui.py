"""N-panel UI for editing captions."""
import bpy
from bpy.types import Panel, UIList

from . import master


class CAPTIONS_UL_lines(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.prop(item, "text", text="", emboss=False)
        row.label(text=f"{item.start}-{item.end}")


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
            layout.separator()
            layout.operator("captions.print_api", text="API Reference", icon='HELP')
            return

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

        if 0 <= caps.active_index < len(caps.lines):
            line = caps.lines[caps.active_index]
            box = layout.box()
            box.prop(line, "text")
            r = box.row(align=True)
            r.prop(line, "start")
            op = r.operator("captions.set_active_frame", text="", icon='KEYFRAME')
            op.which = 'START'
            r = box.row(align=True)
            r.prop(line, "end")
            op = r.operator("captions.set_active_frame", text="", icon='KEYFRAME')
            op.which = 'END'

        layout.separator()
        row = layout.row()
        row.operator("captions.clear_all", icon='X')
        row.operator("captions.print_api", text="API", icon='HELP')


_CLASSES = (CAPTIONS_UL_lines, CAPTIONS_PT_main)


def register():
    for c in _CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(_CLASSES):
        bpy.utils.unregister_class(c)
