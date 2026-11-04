"""python -m app.render_product MODEL.stl --output DIRECTORY
CAD coordinates are millimeters. Original files are never changed.

The CAD worker (app.cad_worker) is the only caller in the deployed site: it renders each unique content once
per RENDER_PRESET into a fresh directory. Blender only ever receives a numpy array of triangles parsed and
bounded by app.mesh, never the uploaded file, and runs at low CPU priority with optional memory and CPU caps.
"""
import argparse,json,os,resource,subprocess,tempfile,threading,time
from pathlib import Path
import numpy as np
from PIL import Image,ImageFilter
from .mesh import load_mesh
_lock=threading.Lock()
# A render already queued or running for the same output directory is not started twice in one process.
_pending=set();_pending_lock=threading.Lock()
THREADS=os.getenv('CAD_RENDER_THREADS','2')
TIMEOUT=int(os.getenv('CAD_RENDER_TIMEOUT_SECONDS','300'))
MEMORY_MB=int(os.getenv('CAD_RENDER_MEMORY_MB','0'))      # address-space cap for Blender; 0 = container limit only
NICE=int(os.getenv('CAD_RENDER_NICE','10'))
def thumbnail(im,size=640):
    """Same image as render.png, downscaled cleanly: Lanczos (alpha-premultiplied by Pillow) and a light
    unsharp mask on colour only, so edges stay crisp without haloing the transparent outline."""
    small=im.resize((size,round(im.height*size/im.width)),Image.LANCZOS)
    colour=small.convert('RGB').filter(ImageFilter.UnsharpMask(radius=.8,percent=40,threshold=1))
    colour.putalpha(small.getchannel('A'));return colour
def _limits():
    """Runs in the Blender child: lower priority than the web app and PostgreSQL, bounded memory and CPU."""
    os.nice(NICE)
    if MEMORY_MB:resource.setrlimit(resource.RLIMIT_AS,(MEMORY_MB<<20,MEMORY_MB<<20))
    resource.setrlimit(resource.RLIMIT_CPU,(TIMEOUT*int(THREADS or 1)+60,)*2)
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
def render_asset(source, output=None, metrics=None, image='render.png'):
    """image: 'render.png', or 'render.webp' (lossless, same pixels, about a third smaller; the worker's choice)."""
    source=Path(source);output=Path(output) if output else source.parent.parent/'renders'/source.stem
    output.mkdir(parents=True,exist_ok=True)
    key=str(output.resolve())
    with _pending_lock:
        if key in _pending:return True
        _pending.add(key)
    try:return _render(source,output,metrics if metrics is not None else {},image)
    finally:
        with _pending_lock:_pending.discard(key)
def _render(source,output,metrics,image='render.png'):
    with _lock:
        try:
            started=time.perf_counter()
            mesh=load_mesh(source.read_bytes(),source.suffix.lower());dimensions=mesh.dimensions
            metrics['parse_seconds']=round(time.perf_counter()-started,3);metrics['triangles']=len(mesh.triangles)
            (output/'status.json').write_text(json.dumps({'status':'processing'}))
            with tempfile.TemporaryDirectory(prefix='ol-render-') as temporary:
                triangles=Path(temporary)/'triangles.npy';np.save(triangles,mesh.triangles.astype(np.float32),allow_pickle=False)
                data=Path(temporary)/'mesh.json';data.write_text(json.dumps({'triangles':str(triangles),'output':temporary}))
                started=time.perf_counter()
                subprocess.run([os.getenv('BLENDER_BIN','blender'),'--background','--factory-startup','--threads',THREADS,'--python-exit-code','1','--python',str(Path(__file__).with_name('studio_scene.py')),'--',str(data)],
                               check=True,timeout=TIMEOUT,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,preexec_fn=_limits)
                metrics['blender_seconds']=round(time.perf_counter()-started,2)
                started=time.perf_counter()
                with Image.open(Path(temporary)/'render.png') as im:
                    im=im.convert('RGBA')
                    if image=='render.webp':im.save(output/image,lossless=True,method=6,exact=True)
                    else:im.save(output/'render.png',optimize=True)
                    thumbnail(im).save(output/'thumb.webp',quality=92,alpha_quality=100,method=6)
                (output/'model.glb').write_bytes((Path(temporary)/'model.glb').read_bytes())
                metrics['encode_seconds']=round(time.perf_counter()-started,2)
            metrics['bytes']={f:(output/f).stat().st_size for f in (image,'thumb.webp','model.glb')};metrics['image']=image
            (output/'status.json').write_text(json.dumps({'status':'ready','dimensions_mm':dimensions}))
        except Exception as exc:
            (output/'status.json').write_text(json.dumps({'status':'failed'}))
            import logging
            detail=getattr(exc,'stderr',b'') or b''
            metrics['error']=(type(exc).__name__+': '+(detail.decode(errors='replace')[-300:] if detail else str(exc)[:300])).strip()
            logging.getLogger(__name__).exception('CAD rendering failed: %s %s',source.name,detail.decode(errors='replace')[-2000:] if detail else '')
            return False
    return True
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source');parser.add_argument('--output');args=parser.parse_args()
    metrics={};ok=render_asset(args.source,args.output,metrics);print(json.dumps(metrics))
    raise SystemExit(0 if ok else 1)
