"""Blender-only neutral plastic studio scene, invoked by render_product.

The still is rendered in neutral grey and recolored per filament in the browser
(assets/product-visuals.js), so lighting stays achromatic and the view transform
is Standard: pixel values remain linear-decodable for that recolor. ALBEDO and the
exposure below are the calibration that recolor depends on; change them together.
"""
import bpy,bmesh,json,sys,math,_cycles
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
from pathlib import Path
ALBEDO=.55  # linear grey of the neutral plastic; mirrored as RENDER_ALBEDO in product-visuals.js
payload=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text());out=Path(payload['output'])
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
vertices=[v for t in payload['triangles'] for v in t];faces=[(i,i+1,i+2) for i in range(0,len(vertices),3)]
mesh=bpy.data.meshes.new('CAD millimeters');mesh.from_pydata(vertices,[],faces)
# STL triangle soup: weld it so curved walls shade smoothly while CAD edges stay crisp.
bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.remove_doubles(bm,verts=bm.verts,dist=1e-4);bm.to_mesh(mesh);bm.free()
mesh.shade_smooth();mesh.set_sharp_from_angle(angle=math.radians(35));mesh.update()
obj=bpy.data.objects.new('Product',mesh);bpy.context.collection.objects.link(obj);bpy.context.view_layer.objects.active=obj;obj.select_set(True)
low=Vector(tuple(min(v[i] for v in vertices) for i in range(3)));high=Vector(tuple(max(v[i] for v in vertices) for i in range(3)))
center=(low+high)/2
for v in mesh.vertices:v.co-=Vector((center.x,center.y,low.z))
size=high-low;span=max(size);target=Vector((0,0,size.z/2))

# Engineering FDM plastic: matte-satin dielectric, softened edges, faint 0.2 mm layer lines and
# local ambient occlusion that keeps holes and recesses legible without darkening open faces.
material=bpy.data.materials.new('Neutral FDM plastic');material.use_nodes=True
nodes=material.node_tree.nodes;links=material.node_tree.links;bs=next(n for n in nodes if n.type=='BSDF_PRINCIPLED')
bs.inputs['Roughness'].default_value=.6;bs.inputs['IOR'].default_value=1.5;bs.inputs['Specular IOR Level'].default_value=.4
occlusion=nodes.new('ShaderNodeAmbientOcclusion');occlusion.samples=8;occlusion.only_local=True;occlusion.inputs['Distance'].default_value=max(2,size.z*.25)
shade=nodes.new('ShaderNodeMapRange');shade.inputs['To Min'].default_value=ALBEDO*.5;shade.inputs['To Max'].default_value=ALBEDO
links.new(occlusion.outputs['AO'],shade.inputs['Value']);links.new(shade.outputs['Result'],bs.inputs['Base Color'])
coords=nodes.new('ShaderNodeTexCoord');axes=nodes.new('ShaderNodeSeparateXYZ');links.new(coords.outputs['Object'],axes.inputs[0])
layers=nodes.new('ShaderNodeMath');layers.operation='SINE';scale=nodes.new('ShaderNodeMath');scale.operation='MULTIPLY';scale.inputs[1].default_value=2*math.pi/.2
links.new(axes.outputs['Z'],scale.inputs[0]);links.new(scale.outputs[0],layers.inputs[0])
noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=.6;noise.inputs['Detail'].default_value=8;links.new(coords.outputs['Object'],noise.inputs['Vector'])
grain=nodes.new('ShaderNodeMath');grain.operation='MULTIPLY_ADD';grain.inputs[1].default_value=.35;links.new(noise.outputs['Fac'],grain.inputs[0]);links.new(layers.outputs[0],grain.inputs[2])
bevel=nodes.new('ShaderNodeBevel');bevel.samples=4;bevel.inputs['Radius'].default_value=.35
bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.04;bump.inputs['Distance'].default_value=.015
links.new(grain.outputs[0],bump.inputs['Height']);links.new(bevel.outputs['Normal'],bump.inputs['Normal']);links.new(bump.outputs['Normal'],bs.inputs['Normal']);obj.data.materials.append(material)
# Export just the centered product; glTF converts Blender Z-up to viewer Y-up.
bpy.ops.export_scene.gltf(filepath=str(out/'model.glb'),export_format='GLB',use_selection=True)

# Three-quarter view: long lens for near-isometric proportions, 30 degrees above, front-left.
scene=bpy.context.scene;scene.render.resolution_x=scene.render.resolution_y=1200;scene.render.resolution_percentage=100
bpy.ops.object.camera_add();cam=bpy.context.object;cam.data.lens=100;cam.data.sensor_width=36;scene.camera=cam
direction=Vector((-math.sin(math.radians(35)),-math.cos(math.radians(35)),0))*math.cos(math.radians(30))+Vector((0,0,math.sin(math.radians(30))))
corners=[Vector((x,y,z)) for x in (-size.x/2,size.x/2) for y in (-size.y/2,size.y/2) for z in (0,size.z)]
def place(distance):
    cam.location=target+direction*distance;cam.rotation_euler=(-direction).to_track_quat('-Z','Y').to_euler();cam.data.shift_x=cam.data.shift_y=0;bpy.context.view_layer.update()
    def box():
        p=[world_to_camera_view(scene,cam,v) for v in corners];return min(q.x for q in p),max(q.x for q in p),min(q.y for q in p),max(q.y for q in p)
    b=box();cam.data.shift_x=(b[0]+b[1])/2-.5;cam.data.shift_y=(b[2]+b[3])/2-.5;bpy.context.view_layer.update()
    b=box();return max(b[1]-b[0],b[3]-b[2])  # widest projected extent, as a fraction of the frame
# Fit the bounding box to 72% of the frame: generous transparent margins on every side.
low_d,high_d=span*.5,span*40
for _ in range(40):
    middle=(low_d+high_d)/2
    if place(middle)>.72:low_d=middle
    else:high_d=middle
place(high_d);cam.data.clip_start=span/1000;cam.data.clip_end=span*100

# Broad softboxes and a grey room; no floor, the product floats on a transparent background.
def softbox(name,offset,power,width,depth,shadows=True):
    bpy.ops.object.light_add(type='AREA',location=target+Vector(offset)*span);light=bpy.context.object;light.name=name
    light.data.shape='RECTANGLE';light.data.size=width*span;light.data.size_y=depth*span;light.data.energy=power*span**2;light.data.spread=math.radians(90);light.data.use_shadow=shadows
    light.rotation_euler=(target-light.location).to_track_quat('-Z','Y').to_euler();return light
softbox('Key softbox',(-1.6,-.2,1.8),44,2.8,2.0)
softbox('Fill softbox',(1.4,-2.2,.7),14,3.0,2.0,False)
softbox('Rim strip',(.5,2.4,1.5),20,2.8,.5,False)
world=scene.world or bpy.data.worlds.new('Studio');scene.world=world;world.use_nodes=True
background=next(n for n in world.node_tree.nodes if n.type=='BACKGROUND');background.inputs['Color'].default_value=(.5,.5,.5,1);background.inputs['Strength'].default_value=.55

# Distribution Blender builds (the Debian package in the image) ship without OpenImageDenoise: sample more instead.
denoise=bool(getattr(_cycles,"with_openimagedenoise",False))
scene.render.engine='CYCLES';scene.cycles.samples=48 if denoise else 96;scene.cycles.use_adaptive_sampling=True;scene.cycles.adaptive_threshold=.02 if denoise else .012;scene.cycles.caustics_reflective=scene.cycles.caustics_refractive=False
scene.cycles.use_denoising=denoise;scene.cycles.max_bounces=4;scene.render.film_transparent=True;scene.cycles.film_transparent_glass=False
scene.render.filter_size=1.2;scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA';scene.render.image_settings.color_depth='8';scene.render.filepath=str(out/'render.png')
scene.view_settings.view_transform='Standard';scene.view_settings.look='None';scene.view_settings.exposure=-1.3
bpy.ops.render.render(write_still=True)
