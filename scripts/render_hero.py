"""Homepage hero: the three official racks as one art-directed product family.

Render (Blender, from the repository root):
    blender -b --factory-startup -t 0 --python scripts/render_hero.py [-- --preview FILE.png]
Encode the web assets from the render (any Python with Pillow):
    uv run --no-project --python 3.12 --with Pillow python scripts/render_hero.py

Meshes are the official STL files, imported unmodified (millimetres); only whole-object placement
and rotation change. The material and softbox recipe follows backend/app/studio_scene.py, with real
filament colours instead of the neutral grey that is recoloured in the browser: lights, room, exposure
and the filament albedo formula match the product previews, so the hero reads like the catalogue.
No floor, no shadow catcher: the group floats on a transparent background.
"""
import math, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'assets/hero'
RAW=Path(tempfile.gettempdir())/'openlabs3d-hero-raw.png'  # 16-bit master; only the encoded assets are published

def encode():
    """Trim to the products plus a slim margin, then write the high-resolution PNG and two WebP sizes."""
    from PIL import Image,ImageFilter
    with Image.open(RAW) as im:
        im=im.convert('RGBA');x0,y0,x1,y1=im.getchannel('A').point(lambda a:255 if a>2 else 0).getbbox()
        pad=round(.025*max(x1-x0,y1-y0));im=im.crop((max(0,x0-pad),max(0,y0-pad),min(im.width,x1+pad),min(im.height,y1+pad)))
        im.save(OUT/'racks-family.png',optimize=True)
        for width in (1600,900):
            small=im.resize((width,round(im.height*width/im.width)),Image.LANCZOS)
            colour=small.convert('RGB').filter(ImageFilter.UnsharpMask(radius=.8,percent=35,threshold=1));colour.putalpha(small.getchannel('A'))
            colour.save(OUT/f'racks-family-{width}.webp',quality=88,alpha_quality=90,method=6)
        print('hero',im.size,[(p.name,p.stat().st_size) for p in sorted(OUT.glob('racks-family*'))])

try:
    import bpy
except ImportError:
    encode();raise SystemExit

from mathutils import Vector,Matrix
from bpy_extras.object_utils import world_to_camera_view
PREVIEW='--preview' in sys.argv
PRODUCTS=ROOT/'official_products'

def linear(hex_colour):
    c=[int(hex_colour[i:i+2],16)/255 for i in (1,3,5)]
    return [v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in c]
# The hero is a touch livelier than the previews: filamentAlbedo() keeps 80 % of the chroma at -1.3 EV.
HERO_CHROMA=1.0;HERO_EXPOSURE=-1.15
def filament(hex_colour):
    # filamentAlbedo() in assets/product-visuals.js (real filament reads darker and less saturated), with HERO_CHROMA.
    a=linear(hex_colour);y=.2126*a[0]+.7152*a[1]+.0722*a[2]
    return tuple(min(.8,max(.012,(y+(c-y)*HERO_CHROMA)*.85)) for c in a)+(1,)

# (file, sRGB filament colour, position in mm on the shared plane, yaw in degrees)
# Yellow 15 mL rack forward and centred; the low orange microtube rack behind-left, the tall teal
# 50 mL rack behind-right, so the heights step up from front to back and none hides another.
RACKS=[
    ('microtube_rack_24','#B9532E',(-70,64,0),-6),
    ('centrifuge_rack_50ml_6','#2B7572',(72,98,0),26),
    ('centrifuge_rack_15ml_12','#EDC662',(-12,-34,0),12),
]

bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene

def plastic(name,colour):
    """The product-preview plastic (backend/app/studio_scene.py): matte-satin dielectric, faint 0.2 mm
    layer lines, softened edges and local occlusion that keeps tube openings legible."""
    m=bpy.data.materials.new(name);m.use_nodes=True;nodes=m.node_tree.nodes;links=m.node_tree.links
    bs=next(n for n in nodes if n.type=='BSDF_PRINCIPLED')
    bs.inputs['Roughness'].default_value=.6;bs.inputs['IOR'].default_value=1.5;bs.inputs['Specular IOR Level'].default_value=.4
    occlusion=nodes.new('ShaderNodeAmbientOcclusion');occlusion.samples=8;occlusion.only_local=True;occlusion.inputs['Distance'].default_value=12
    # Colour x mix(1, AO, 0.5): a fully occluded crevice keeps half its colour, as in the previews.
    invert=nodes.new('ShaderNodeMix');invert.data_type='RGBA';invert.inputs['Factor'].default_value=.5
    invert.inputs['A'].default_value=(1,1,1,1);links.new(occlusion.outputs['AO'],invert.inputs['B'])
    tint=nodes.new('ShaderNodeMix');tint.data_type='RGBA';tint.blend_type='MULTIPLY';tint.inputs['Factor'].default_value=1
    tint.inputs['A'].default_value=colour;links.new(invert.outputs['Result'],tint.inputs['B']);links.new(tint.outputs['Result'],bs.inputs['Base Color'])
    coords=nodes.new('ShaderNodeTexCoord');axes=nodes.new('ShaderNodeSeparateXYZ');links.new(coords.outputs['Object'],axes.inputs[0])
    scale=nodes.new('ShaderNodeMath');scale.operation='MULTIPLY';scale.inputs[1].default_value=2*math.pi/.2
    layers=nodes.new('ShaderNodeMath');layers.operation='SINE';links.new(axes.outputs['Z'],scale.inputs[0]);links.new(scale.outputs[0],layers.inputs[0])
    noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=.6;noise.inputs['Detail'].default_value=8;links.new(coords.outputs['Object'],noise.inputs['Vector'])
    grain=nodes.new('ShaderNodeMath');grain.operation='MULTIPLY_ADD';grain.inputs[1].default_value=.35;links.new(noise.outputs['Fac'],grain.inputs[0]);links.new(layers.outputs[0],grain.inputs[2])
    bevel=nodes.new('ShaderNodeBevel');bevel.samples=4;bevel.inputs['Radius'].default_value=.35
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.04;bump.inputs['Distance'].default_value=.015
    links.new(grain.outputs[0],bump.inputs['Height']);links.new(bevel.outputs['Normal'],bump.inputs['Normal']);links.new(bump.outputs['Normal'],bs.inputs['Normal'])
    return m

objects=[]
for key,hex_colour,position,yaw in RACKS:
    bpy.ops.wm.stl_import(filepath=str(PRODUCTS/key/(key+'.stl')));obj=bpy.context.selected_objects[0];obj.name=key
    mesh=obj.data
    # Same welding and smoothing as the product pipeline: curved walls shade smoothly, CAD edges stay crisp.
    import bmesh
    bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.remove_doubles(bm,verts=bm.verts,dist=1e-4);bm.to_mesh(mesh);bm.free()
    mesh.shade_smooth();mesh.set_sharp_from_angle(angle=math.radians(35));mesh.update()
    corners=[Vector(c) for c in obj.bound_box];centre=sum(corners,Vector())/8
    # Centre the footprint on the object origin (a whole-object offset, geometry untouched).
    obj.matrix_world=Matrix.Translation(Vector(position))@Matrix.Rotation(math.radians(yaw),4,'Z')@Matrix.Translation(Vector((-centre.x,-centre.y,-min(c.z for c in corners))))
    mesh.materials.append(plastic(key+' filament',filament(hex_colour)));objects.append(obj)
bpy.context.view_layer.update()
points=[o.matrix_world@Vector(c) for o in objects for c in o.bound_box]
low=Vector(tuple(min(p[i] for p in points) for i in range(3)));high=Vector(tuple(max(p[i] for p in points) for i in range(3)))
target=(low+high)/2;span=max(high-low)

# The previews' three-quarter view: 35 degrees front-left, 30 degrees above, 100 mm lens.
width,height=(1200,960) if PREVIEW else (2400,1920)
scene.render.resolution_x,scene.render.resolution_y,scene.render.resolution_percentage=width,height,100
bpy.ops.object.camera_add();cam=bpy.context.object;cam.data.lens=100;cam.data.sensor_width=36;cam.data.sensor_fit='HORIZONTAL';scene.camera=cam
azimuth,elevation=math.radians(35),math.radians(30)
direction=Vector((-math.sin(azimuth)*math.cos(elevation),-math.cos(azimuth)*math.cos(elevation),math.sin(elevation)))
def place(distance):
    cam.location=target+direction*distance;cam.rotation_euler=(-direction).to_track_quat('-Z','Y').to_euler();cam.data.shift_x=cam.data.shift_y=0;bpy.context.view_layer.update()
    def box():
        p=[world_to_camera_view(scene,cam,v) for v in points];return min(q.x for q in p),max(q.x for q in p),min(q.y for q in p),max(q.y for q in p)
    b=box();aspect=height/width;cam.data.shift_x=(b[0]+b[1])/2-.5;cam.data.shift_y=((b[2]+b[3])/2-.5)*aspect;bpy.context.view_layer.update()
    b=box();return max(b[1]-b[0],b[3]-b[2])
# Bounding boxes overestimate the silhouette; 0.9 still leaves every rack unclipped. The PNG is trimmed later.
near,far=span*.5,span*40
for _ in range(40):
    middle=(near+far)/2
    if place(middle)>.9:near=middle
    else:far=middle
place(far);cam.data.clip_start=span/1000;cam.data.clip_end=span*100

# The product studio's broad softboxes and grey room, scaled to the group.
def softbox(name,offset,power,size_x,size_y,shadows=True):
    bpy.ops.object.light_add(type='AREA',location=target+Vector(offset)*span);light=bpy.context.object;light.name=name
    light.data.shape='RECTANGLE';light.data.size=size_x*span;light.data.size_y=size_y*span;light.data.energy=power*span**2
    light.data.spread=math.radians(90);light.data.use_shadow=shadows
    light.rotation_euler=(target-light.location).to_track_quat('-Z','Y').to_euler();return light
softbox('Key softbox',(-1.6,-.2,1.8),44,2.8,2.0)
softbox('Fill softbox',(1.4,-2.2,.7),14,3.0,2.0,False)
softbox('Rim strip',(.5,2.4,1.5),20,2.8,.5,False)
world=scene.world or bpy.data.worlds.new('Studio');scene.world=world;world.use_nodes=True
background=next(n for n in world.node_tree.nodes if n.type=='BACKGROUND');background.inputs['Color'].default_value=(.5,.5,.5,1);background.inputs['Strength'].default_value=.55

try:scene.render.engine='CYCLES'
except TypeError as e:print(e);raise
import _cycles
scene.cycles.samples=64 if PREVIEW else 256;scene.cycles.use_adaptive_sampling=True;scene.cycles.adaptive_threshold=.02 if PREVIEW else .01
scene.cycles.use_denoising=bool(getattr(_cycles,'with_openimagedenoise',False));scene.cycles.max_bounces=6;scene.cycles.caustics_reflective=scene.cycles.caustics_refractive=False
scene.render.film_transparent=True;scene.render.filter_size=1.2
# Same tone mapping as the product previews, slightly brighter (HERO_EXPOSURE).
scene.view_settings.view_transform='Standard';scene.view_settings.look='None';scene.view_settings.exposure=HERO_EXPOSURE
s=scene.render.image_settings;s.file_format='PNG';s.color_mode='RGBA';s.color_depth='16'
OUT.mkdir(parents=True,exist_ok=True)
scene.render.filepath=sys.argv[sys.argv.index('--preview')+1] if PREVIEW else str(RAW)
bpy.ops.render.render(write_still=True)
