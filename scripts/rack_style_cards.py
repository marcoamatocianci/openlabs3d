"""Remake the two pictures on the configurator's design cards from the real CAD: python scripts/rack_style_cards.py WORK_DIR

They are the same rack (6 x 50 mL) in each design family, built by the engine and rendered by the site's own Blender path, so
they change when the geometry does. Needs requirements-cad.txt and Blender. Run it after a change to the design families.
"""
import json, os, subprocess, sys
from pathlib import Path
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.rack.planner import plan
from app.rack.schema import RackConfiguration

WIDTH, HEIGHT = 640, 480

def main(work):
    environment = {**os.environ, 'PYTHONPATH': str(ROOT / 'backend'), 'CAD_RENDER_THREADS': '10'}
    for style in ('lightweight', 'premium'):
        folder = Path(work) / style; folder.mkdir(parents=True, exist_ok=True)
        config = RackConfiguration(tubes=[{'profile_id': 'conical-50-generic', 'quantity': 6}], style=style)
        (folder / 'spec.json').write_text(json.dumps(plan(config, [(350, 350, 350)])['spec']))
        subprocess.run([sys.executable, '-m', 'app.rack.build', str(folder / 'spec.json'), str(folder)], check=True, env=environment, cwd=ROOT / 'backend', stdout=subprocess.DEVNULL)
        subprocess.run([sys.executable, '-m', 'app.render_product', str(folder / 'rack.stl'), '--output', str(folder / 'render')], check=True, env=environment, cwd=ROOT / 'backend', stdout=subprocess.DEVNULL)
        image = Image.open(folder / 'render' / 'render.png').convert('RGBA')
        image = image.crop(image.getchannel('A').getbbox())
        scale = min(WIDTH * .94 / image.width, HEIGHT * .94 / image.height)
        image = image.resize((int(image.width * scale), int(image.height * scale)), Image.LANCZOS)
        card = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
        card.paste(image, ((WIDTH - image.width) // 2, (HEIGHT - image.height) // 2))
        card.save(ROOT / 'assets' / 'products' / f'rack-style-{style}.webp', quality=86, method=6)

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'rack-style-cards')
