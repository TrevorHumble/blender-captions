"""The master Text object: the single object that renders all captions.

Created once per scene. Looked up via the scene's pointer property; name is
used only as a fallback so users can freely rename the object.

Positioning: when a camera exists, the master is parented to the camera and
positioned at the bottom-center of the camera frame at 1m depth. Position
and scale are computed from the camera's actual view frustum so the text
sits inside the visible area regardless of lens or aspect ratio.
"""
import bpy
import mathutils

MASTER_NAME = "Captions"
MATERIAL_NAME = "Captions_Material"
_DEPTH = 1.0          # how far in front of the camera the text lives
_BOTTOM_MARGIN = 0.05 # fraction of frame height above bottom edge
_TEXT_HEIGHT = 0.06   # text height as fraction of frame height


def get(scene):
    """Return the scene's master object, or None if missing."""
    obj = scene.captions.master_object
    if obj is not None and obj.name in bpy.data.objects:
        return obj
    obj = bpy.data.objects.get(MASTER_NAME)
    if obj is not None:
        scene.captions.master_object = obj
    return obj


def create(scene):
    """Create the master Text object. Idempotent: returns the existing one if any."""
    existing = get(scene)
    if existing is not None:
        return existing

    curve = bpy.data.curves.new(MASTER_NAME, 'FONT')
    curve.body = ""
    curve.align_x = 'CENTER'
    curve.align_y = 'BOTTOM'

    obj = bpy.data.objects.new(MASTER_NAME, curve)
    scene.collection.objects.link(obj)
    obj.data.materials.append(_ensure_material(scene.captions.emission_strength))
    obj.visible_shadow = False

    if scene.camera and scene.captions.auto_parent_to_camera:
        _attach_to_camera(obj, scene)

    scene.captions.master_object = obj
    return obj


def _attach_to_camera(obj, scene):
    """Parent `obj` to the active camera and place it at bottom-center of the frame.

    matrix_parent_inverse is left as identity so the object's local coords are
    interpreted directly in camera space. Without that, parenting visually
    cancels itself out.
    """
    cam = scene.camera
    obj.parent = cam
    obj.matrix_parent_inverse = mathutils.Matrix.Identity(4)

    corners = cam.data.view_frame(scene=scene)
    near_z = abs(corners[0].z)
    factor = _DEPTH / near_z
    xs = [c.x * factor for c in corners]
    ys = [c.y * factor for c in corners]
    left_x, right_x = min(xs), max(xs)
    bottom_y, top_y = min(ys), max(ys)
    frame_height = top_y - bottom_y
    frame_width = right_x - left_x

    obj.location = (0.0, bottom_y + frame_height * _BOTTOM_MARGIN, -_DEPTH)
    s = frame_height * _TEXT_HEIGHT
    obj.scale = (s, s, s)

    # Word-wrap inside the camera frame (with a small horizontal margin).
    # text_box width is in the text's local units; convert by dividing by scale.
    usable_width = frame_width * 0.9
    obj.data.text_boxes[0].width = usable_width / s
    obj.data.text_boxes[0].x = -(usable_width / s) / 2  # center the box on origin


def _ensure_material(strength):
    mat = bpy.data.materials.get(MATERIAL_NAME)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(MATERIAL_NAME)
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    emission = tree.nodes.new('ShaderNodeEmission')
    emission.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)
    emission.inputs['Strength'].default_value = strength
    output = tree.nodes.new('ShaderNodeOutputMaterial')
    tree.links.new(emission.outputs['Emission'], output.inputs['Surface'])
    return mat
