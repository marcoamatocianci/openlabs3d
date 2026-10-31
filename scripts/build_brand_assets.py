"""Web brand assets from the supplied logo artwork ("OpenLabs3D Laboratory Printer Logo.png").

    uv run --no-project --python 3.12 --with Pillow --with numpy python scripts/build_brand_assets.py

The artwork is not redrawn. Its flat background is removed by un-mixing every pixel against the
nearest ink (so anti-aliased edges keep their exact ink colour instead of a pale fringe), the
lockup is trimmed, and small WebP/PNG sizes are written to assets/brand/:

  openlabs3d-logo.png         transparent full-resolution master (not loaded by the site)
  openlabs3d-logo.webp        topbar/footer lockup for the Bright theme
  openlabs3d-logo-dark.webp   the same lockup reversed for the Dark theme: only the navy ink
                              becomes the Dark theme's ink colour; blue and red are unchanged
  favicon-32.png, favicon-192.png, apple-touch-icon.png
                              the printer mark alone, on the artwork's own light background tile
"""
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'OpenLabs3D Laboratory Printer Logo.png'
OUT = ROOT / 'assets/brand'
DARK_INK = np.array([0xe1, 0xed, 0xff], float)  # --ink in style.css for [data-theme=dark]
LOCKUP_HEIGHT = 96                                 # 2x the largest display height (48 px, footer)

def unmix(rgb):
    """Return (straight colour, alpha, ink index) assuming pixel = a*ink + (1-a)*background."""
    border = np.concatenate([rgb[:16].reshape(-1, 3), rgb[-16:].reshape(-1, 3), rgb[:, :16].reshape(-1, 3), rgb[:, -16:].reshape(-1, 3)])
    bg = np.median(border, 0)
    distance = np.sqrt(((rgb - bg) ** 2).sum(2))
    # Inks: the most common colours among clearly non-background pixels (navy, blue, red).
    solid = rgb[distance > 120].reshape(-1, 3)
    inks = []
    for _ in range(3):
        if not len(solid): break
        bins = (solid // 24).astype(int); keys, counts = np.unique(bins, axis=0, return_counts=True)
        key = keys[counts.argmax()]; members = (bins == key).all(1)
        inks.append(solid[members].mean(0)); solid = solid[np.sqrt(((solid - inks[-1]) ** 2).sum(1)) > 70]
    inks = np.array(inks)
    best = np.full(rgb.shape[:2], np.inf); alpha = np.zeros(rgb.shape[:2]); index = np.zeros(rgb.shape[:2], int)
    offset = rgb - bg
    for k, ink in enumerate(inks):
        direction = ink - bg
        a = np.clip((offset @ direction) / (direction @ direction), 0, 1)
        residual = ((offset - a[..., None] * direction) ** 2).sum(2)
        better = residual < best
        best[better], alpha[better], index[better] = residual[better], a[better], k
    alpha[distance < 8] = 0                       # background grain
    safe = np.maximum(alpha, 1e-3)[..., None]
    colour = np.clip(bg + offset / safe, 0, 255)
    return colour, alpha, index, inks, bg

def rgba(colour, alpha):
    return Image.fromarray(np.dstack([colour, alpha * 255]).round().astype(np.uint8), 'RGBA')

def main():
    rgb = np.asarray(Image.open(SOURCE).convert('RGB')).astype(float)
    colour, alpha, index, inks, bg = unmix(rgb)
    navy = int(np.argmin(inks.sum(1)))
    light = rgba(colour, alpha)
    box = light.getchannel('A').point(lambda v: 255 if v > 8 else 0).getbbox()
    pad = 6
    box = (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad)
    reversed_colour = colour.copy()
    # Reverse only the navy strokes; keep their alpha so edges stay smooth.
    reversed_colour[index == navy] = DARK_INK
    dark = rgba(reversed_colour, alpha)
    OUT.mkdir(parents=True, exist_ok=True)
    lockup = light.crop(box); lockup.save(OUT / 'openlabs3d-logo.png', optimize=True)
    size = (round(lockup.width * LOCKUP_HEIGHT / lockup.height), LOCKUP_HEIGHT)
    lockup.resize(size, Image.LANCZOS).save(OUT / 'openlabs3d-logo.webp', quality=90, alpha_quality=90, method=6)
    dark.crop(box).resize(size, Image.LANCZOS).save(OUT / 'openlabs3d-logo-dark.webp', quality=90, alpha_quality=90, method=6)
    # The printer mark is everything left of the widest empty column run (the mark/wordmark gap).
    columns = (alpha > .05).any(0); filled = np.flatnonzero(columns)
    runs, start = [], None
    for x in range(filled[0], filled[-1] + 1):
        if not columns[x] and start is None: start = x
        elif columns[x] and start is not None: runs.append((x - start, start)); start = None
    width, x = max(runs)
    mark = light.crop((box[0] + pad, box[1] + pad, x, box[3] - pad))
    side = round(max(mark.size) * 1.22)
    tile = Image.new('RGBA', (side, side), tuple(int(v) for v in bg) + (255,))
    tile.alpha_composite(mark, ((side - mark.width) // 2, (side - mark.height) // 2))
    for name, px in (('favicon-32.png', 32), ('favicon-192.png', 192), ('apple-touch-icon.png', 180)):
        tile.resize((px, px), Image.LANCZOS).convert('RGB').save(OUT / name, optimize=True)
    print('inks', inks.round(), 'background', bg, 'lockup', lockup.size, 'web', size, 'mark', mark.size, 'gap', (x, x + width))
    for p in sorted(OUT.iterdir()): print(f'{p.name:28} {p.stat().st_size:>8} B')

if __name__ == '__main__':
    main()
