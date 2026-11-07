"""Label fitting from the fonts' own metrics, without any CAD. Fonts are bundled so metrics and geometry match."""
from functools import lru_cache
from pathlib import Path
from PIL import ImageFont
from .rules import RULES

FONT_DIR = Path(__file__).with_name('fonts')
# stroke: thin strokes as a share of the font size (5th percentile of stroke widths), checked by
# tests/test_rack_engine.py::test_font_strokes_match_their_constants. Bold faces only: regular weights do not print.
FONTS = {'sans': {'file': 'LiberationSans-Bold.ttf', 'label': 'Sans', 'stroke': .085},
         'serif': {'file': 'DejaVuSerif-Bold.ttf', 'label': 'Serif', 'stroke': .057},
         'mono': {'file': 'DejaVuSansMono-Bold.ttf', 'label': 'Mono', 'stroke': .105}}
DEFAULT_SIZE_MM = 10.0
_REFERENCE = 200

def font_path(font): return str(FONT_DIR / FONTS[font]['file'])

@lru_cache(maxsize=8)
def _font(font): return ImageFont.truetype(font_path(font), _REFERENCE)

def text_size(text, font, size):
    """(width, cap height) in mm of a line of text at this font size."""
    f = _font(font)
    box = f.getbbox(text or 'H')
    cap = f.getbbox('H')
    return (box[2] - box[0]) * size / _REFERENCE, (cap[3] - cap[1]) * size / _REFERENCE

def min_size(font):
    """The smallest size whose thinnest stroke still prints, and never below the general minimum."""
    return max(RULES.min_text_size_mm, RULES.min_text_stroke_mm / FONTS[font]['stroke'])

def fit(text, font, requested, box_w, box_h):
    """(size, status) for a line of text in a box: the requested size (or the default), or the largest smaller size
    that fits. status: 'ok', 'reduced' (smaller than the buyer asked), or 'too_long' / 'too_short' when even the
    smallest printable size does not fit that way."""
    lower = min_size(font)
    wanted = max(min(requested or DEFAULT_SIZE_MM, RULES.max_text_size_mm), lower)
    width, cap = text_size(text, font, 1)
    by_width, by_height = box_w / width if width else wanted, box_h / cap if cap else wanted
    largest = min(by_width, by_height)
    if largest < lower: return round(lower, 2), 'too_long' if by_width < by_height else 'too_short'
    size = round(min(wanted, largest - .005), 2)
    reduced = requested is not None and size < requested - .01
    return size, 'reduced' if reduced else 'ok'

def characters_that_fit(text, font, size, box_w):
    """How many characters of this text fit at a size, to suggest a shorter label."""
    for n in range(len(text), 0, -1):
        if text_size(text[:n], font, size)[0] <= box_w: return n
    return 0
