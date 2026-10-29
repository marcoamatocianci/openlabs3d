import json,re
from pathlib import PurePosixPath
from . import config
def visual_data(p):
    if not re.fullmatch(r'[a-f0-9]{48}\.(stl|3mf)',p.cad_path or ''):return {'status':'none'}
    revision=PurePosixPath(p.cad_path).stem
    folder=config.UPLOAD_DIR.parent/'renders'/revision
    try:status=json.loads((folder/'status.json').read_text())['status']
    except (OSError,ValueError,KeyError):status='pending'
    if status!='ready':return {'status':status}
    base=f'/api/listings/{p.id}/visuals/{revision}/'
    return {'status':'ready','image':base+'render.png','thumbnail':base+'thumb.webp','model':base+'model.glb'}
