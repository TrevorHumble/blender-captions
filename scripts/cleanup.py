"""Cleanup script for the Captions add-on.

Run this from Blender's Text Editor (Text Editor -> Open -> pick this file ->
Run Script) when the add-on is stuck in a partially-registered state -- for
example after a failed Install... that left "CaptionLine already registered"
errors behind.

Safe to run even when nothing is registered.
"""
import sys
import bpy

CAPTION_CLASSES = [
    # Order doesn't matter for unregister_class.
    # Keep this list in sync with _CLASSES tuples across props.py, operators.py,
    # and ui.py. tests/lint/check.py verifies this automatically.
    "CaptionLine", "CaptionSettings",
    "CAPTIONS_UL_lines", "CAPTIONS_PT_main", "CAPTIONS_PT_advanced",
    "CAPTIONS_OT_create_master_object", "CAPTIONS_OT_select_master",
    "CAPTIONS_OT_add_line", "CAPTIONS_OT_remove_line",
    "CAPTIONS_OT_move_line", "CAPTIONS_OT_set_active_frame",
    "CAPTIONS_OT_bulk_import", "CAPTIONS_OT_clear_all",
    "CAPTIONS_OT_print_api",
]

# Remove app handlers that mention captions
for hl in (bpy.app.handlers.frame_change_pre,
           bpy.app.handlers.depsgraph_update_post,
           bpy.app.handlers.load_post):
    for h in list(hl):
        if "captions" in (getattr(h, "__module__", "") or "").lower():
            hl.remove(h)
            print(f"removed handler: {h.__module__}.{h.__name__}")

# Drop Scene.captions
if hasattr(bpy.types.Scene, "captions"):
    try:
        del bpy.types.Scene.captions
        print("removed Scene.captions")
    except Exception as e:
        print(f"could not delete Scene.captions: {e}")

# Unregister all caption classes
for name in CAPTION_CLASSES:
    cls = getattr(bpy.types, name, None)
    if cls is not None:
        try:
            bpy.utils.unregister_class(cls)
            print(f"unregistered: {name}")
        except Exception as e:
            print(f"could not unregister {name}: {e}")

# Drop from sys.modules
for mod_name in list(sys.modules.keys()):
    if mod_name == "captions_tool" or mod_name.startswith("captions_tool."):
        del sys.modules[mod_name]
        print(f"removed from sys.modules: {mod_name}")

print()
print(f"Scene has 'captions' attr: {hasattr(bpy.context.scene, 'captions')}")
print(f"bpy.types.CaptionLine exists: {hasattr(bpy.types, 'CaptionLine')}")
print(f"'captions_tool' in sys.modules: {'captions_tool' in sys.modules}")
print("\nCleanup done. You can now Install... the addon zip via Preferences.")
