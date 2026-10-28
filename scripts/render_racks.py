"""Run: blender -b -t 6 --python scripts/render_racks.py
Concept geometry only: tube fit and manufacture have not been validated.
"""
import bpy, math, sys
from mathutils import Vector
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'assets/products'
COLORS={'aqua-blue':(0.055,0.39,0.52,1),'signal-red':(0.65,0.035,0.055,1),'cream':(0.8,0.73,0.54,1)}
def box(name, size, loc, bevel=1):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc); o=bpy.context.object; o.name=name; o.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    if bevel:
        m=o.modifiers.new('Rounded manufactured edges','BEVEL');m.width=bevel;m.segments=4
        bpy.context.view_layer.objects.active=o;bpy.ops.object.modifier_apply(modifier=m.name)
    return o
for key,nx,ny,pitch,radius,height in [('microtube-rack',6,4,18,5.5,28),('15ml-rack',4,3,25,8.5,48),('50ml-rack',3,2,38,15,58)]:
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    w,d=nx*pitch+10,ny*pitch+10
    parts=[box('Stable rounded base',(w,d,5),(0,0,2.5),2)]
    top=box('Perforated upper deck',(w,d,7),(0,0,height),2)
    for x in range(nx):
        for y in range(ny):
            cx=(x-(nx-1)/2)*pitch;cy=(y-(ny-1)/2)*pitch
            bpy.ops.mesh.primitive_cylinder_add(vertices=64,radius=radius,depth=15,location=(cx,cy,height))
            cutter=bpy.context.object;m=top.modifiers.new('Tube opening','BOOLEAN');m.operation='DIFFERENCE';m.object=cutter
            bpy.context.view_layer.objects.active=top;bpy.ops.object.modifier_apply(modifier=m.name);bpy.data.objects.remove(cutter,do_unlink=True)
    m=top.modifiers.new('Opening chamfers','BEVEL');m.width=.6;m.segments=3
    parts.append(top)
    for x in [-1,1]:
        parts.append(box('Structural end wall',(5,d-8,height-4),(x*(w/2-4),0,height/2),1.5))
    mat=bpy.data.materials.new('Matte FDM polymer');mat.use_nodes=True
    bs=mat.node_tree.nodes.get('Principled BSDF');bs.inputs['Roughness'].default_value=.34
    for o in parts:o.data.materials.append(mat)
    bpy.ops.object.select_all(action='DESELECT')
    for o in parts: o.select_set(True)
    model_dir=ROOT.parent/'models';model_dir.mkdir(exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(model_dir/(key+'.glb')),use_selection=True,export_apply=True)
    if '--models-only' in sys.argv: continue
    scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=48;scene.cycles.use_denoising=True
    scene.render.resolution_x=scene.render.resolution_y=1024;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA';scene.render.film_transparent=True
    scene.world.color=(.35,.35,.35)
    bpy.ops.object.camera_add(location=(190,-235,205));cam=bpy.context.object;cam.rotation_euler=(Vector((0,0,22))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO';cam.data.ortho_scale=210;scene.camera=cam
    for loc,power,size in [((40,-100,220),650000,160),((-170,-30,120),380000,140),((60,160,160),700000,100)]:
        bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.data.energy=power;o.data.shape='DISK';o.data.size=size;o.rotation_euler=(-o.location).to_track_quat('-Z','Y').to_euler()
    scene.view_settings.view_transform='AgX'
    dest=ROOT/key;dest.mkdir(parents=True,exist_ok=True)
    for color,rgba in COLORS.items():
        bs.inputs['Base Color'].default_value=rgba;scene.render.filepath=str(dest/(color+'.png'));bpy.ops.render.render(write_still=True)
