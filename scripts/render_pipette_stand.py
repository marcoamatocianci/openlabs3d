"""Run: blender -b -t 6 --python scripts/render_pipette_stand.py
Fallback colour images and viewer GLB for the DNA pipette stand, from the real assembled CAD export
(official_products/dna_pipette_stand_6). Same camera direction, lights and colours as render_racks.py,
framed for the taller stand. Pipette fit is UNVERIFIED; see the product README.
"""
import bpy, math
from mathutils import Vector
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
KEY = 'dna-pipette-stand'
SOURCE = REPO / 'official_products/dna_pipette_stand_6/assembly/dna_pipette_stand_6_assembled.stl'
COLORS = {'aqua-blue': (0.055, 0.39, 0.52, 1), 'signal-red': (0.65, 0.035, 0.055, 1), 'cream': (0.8, 0.73, 0.54, 1)}

bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
bpy.ops.wm.stl_import(filepath=str(SOURCE))
stand = bpy.context.selected_objects[0]; stand.name = 'DNA pipette stand'
bpy.context.view_layer.objects.active = stand
bpy.ops.object.shade_auto_smooth(angle=math.radians(35))
# The viewer GLB only needs the silhouette and relief; keep it near the size of the rack GLBs.
decimate = stand.modifiers.new('Viewer weight', 'DECIMATE'); decimate.ratio = .25
mat = bpy.data.materials.new('Matte FDM polymer'); mat.use_nodes = True
bs = mat.node_tree.nodes.get('Principled BSDF'); bs.inputs['Roughness'].default_value = .34
stand.data.materials.append(mat)
model_dir = REPO / 'assets/models'; model_dir.mkdir(exist_ok=True)
bpy.ops.object.select_all(action='DESELECT'); stand.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(model_dir / (KEY + '.glb')), use_selection=True, export_apply=True)
stand.modifiers.remove(decimate)

scene = bpy.context.scene; scene.render.engine = 'CYCLES'; scene.cycles.samples = 48; scene.cycles.use_denoising = True
scene.render.resolution_x = scene.render.resolution_y = 1024; scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'; scene.render.image_settings.color_mode = 'RGBA'; scene.render.film_transparent = True
scene.world.color = (.35, .35, .35)
target = Vector((0, 0, 140)); scale = 1.55   # the stand is ~2.4× taller than the racks
bpy.ops.object.camera_add(location=Vector((190, -235, 205)) * scale + Vector((0, 0, 90)))
cam = bpy.context.object; cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
cam.data.type = 'ORTHO'; cam.data.ortho_scale = 390; scene.camera = cam
for loc, power, size in [((40, -100, 220), 650000, 160), ((-170, -30, 120), 380000, 140), ((60, 160, 160), 700000, 100)]:
    bpy.ops.object.light_add(type='AREA', location=Vector(loc) * scale); o = bpy.context.object
    o.data.energy = power * scale ** 1.5; o.data.shape = 'DISK'; o.data.size = size * scale
    o.rotation_euler = (target - o.location).to_track_quat('-Z', 'Y').to_euler()
scene.view_settings.view_transform = 'AgX'
dest = REPO / 'assets/products' / KEY; dest.mkdir(parents=True, exist_ok=True)
for color, rgba in COLORS.items():
    bs.inputs['Base Color'].default_value = rgba; scene.render.filepath = str(dest / (color + '.png')); bpy.ops.render.render(write_still=True)
