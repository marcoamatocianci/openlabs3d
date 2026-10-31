"""python -m app.render_product MODEL.stl --output DIRECTORY
CAD coordinates are millimeters. Original files are never changed.
"""
import argparse,json,os,subprocess,tempfile,threading
from pathlib import Path
from PIL import Image,ImageFilter
from .mesh import inspect_mesh
_lock=threading.Lock()
# Sources are content-addressed, so a render already queued or running for the same file produces the
# same output: further requests (repeated "regenerate" clicks, re-uploads) are dropped, not re-run.
_pending=set();_pending_lock=threading.Lock()
def thumbnail(im,size=640):
    """Same image as render.png, downscaled cleanly: Lanczos (alpha-premultiplied by Pillow) and a light
    unsharp mask on colour only, so edges stay crisp without haloing the transparent outline."""
    small=im.resize((size,round(im.height*size/im.width)),Image.LANCZOS)
    colour=small.convert('RGB').filter(ImageFilter.UnsharpMask(radius=.8,percent=40,threshold=1))
    colour.putalpha(small.getchannel('A'));return colour
def render_asset(source, output=None):
    source=Path(source);output=Path(output) if output else source.parent.parent/'renders'/source.stem
    output.mkdir(parents=True,exist_ok=True)
    key=str(output.resolve())
    with _pending_lock:
        if key in _pending:return True
        _pending.add(key)
    try:return _render(source,output)
    finally:
        with _pending_lock:_pending.discard(key)
def _render(source,output):
    with _lock:
        try:
            dimensions,triangles=inspect_mesh(source.read_bytes(),source.suffix.lower(),True)
            (output/'status.json').write_text(json.dumps({'status':'processing'}))
            with tempfile.TemporaryDirectory(prefix='ol-render-') as temporary:
                data=Path(temporary)/'mesh.json';data.write_text(json.dumps({'triangles':triangles,'output':temporary}))
                subprocess.run([os.getenv('BLENDER_BIN','blender'),'--background','--factory-startup','--threads','2','--python-exit-code','1','--python',str(Path(__file__).with_name('studio_scene.py')),'--',str(data)],check=True,timeout=180,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
                with Image.open(Path(temporary)/'render.png') as im:
                    im=im.convert('RGBA');im.save(output/'render.png',optimize=True)
                    thumbnail(im).save(output/'thumb.webp',quality=92,alpha_quality=100,method=6)
                (output/'model.glb').write_bytes((Path(temporary)/'model.glb').read_bytes())
            (output/'status.json').write_text(json.dumps({'status':'ready','dimensions_mm':dimensions}))
        except Exception as exc:
            (output/'status.json').write_text(json.dumps({'status':'failed'}))
            import logging
            logging.getLogger(__name__).exception('CAD rendering failed: %s %s',source.name,getattr(exc,'stderr',b'').decode(errors='replace')[-2000:])
            return False
    return True
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source');parser.add_argument('--output');args=parser.parse_args()
    raise SystemExit(0 if render_asset(args.source,args.output) else 1)
