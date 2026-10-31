"""One active profile picture; curated designs for writes, legacy artwork for reads only."""
import json
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

VARIANTS = {
    'erlenmeyer': ('angular',), 'test-tube': ('single',), 'pipette': ('classic',),
    'dna': ('helix',), 'molecule': ('triad', 'ring', 'chain'), 'petri-dish': ('agar',),
}
FOREGROUNDS = ('#386641', '#6a994e', '#a7c957', '#f2e8cf', '#bc4749')
BACKGROUNDS = ('#d7e0d9', '#e1eadc', '#edf4dd', '#fcfaf5', '#f2dadb')
MIN_CONTRAST = 3
COLOR = r'^#[0-9A-Fa-f]{6}$'
PHOTO_NAME = r'[a-f0-9]{48}\.webp'
# Historical artwork remains renderable, but cannot be selected or newly saved.
LEGACY_VARIANTS = {
    'erlenmeyer': ('angular', 'rounded', 'liquid', 'abstract'), 'beaker': ('classic', 'filled', 'wide'),
    'test-tube': ('single', 'trio', 'tilted'), 'pipette': ('classic', 'drop', 'minimal'),
    'dna': ('helix', 'ladder', 'beads'), 'molecule': ('triad', 'ring', 'chain'),
    'microscope': ('classic', 'compact'), 'petri-dish': ('colonies', 'agar', 'stacked'),
    'cell': ('nucleus', 'dividing', 'membrane'), 'bacterium': ('rod', 'cocci', 'spiral'),
    'centrifuge-tube': ('conical', 'filled', 'pair'), 'microplate': ('grid', 'filled', 'strip'),
}

def contrast(a, b):
    def luminance(hex_color):
        channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        return sum(w * (c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4)
                   for c, w in zip(channels, (.2126, .7152, .0722)))
    lo, hi = sorted((luminance(a), luminance(b)))
    return (hi + .05) / (lo + .05)

class AvatarStyle(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: str = Field(max_length=40)
    variant: str = Field(max_length=40)
    foreground: str = Field(pattern=COLOR)
    background: str = Field(pattern=COLOR)

    @model_validator(mode='after')
    def curated_design(self):
        if self.variant not in VARIANTS.get(self.type, ()):
            raise ValueError('Unknown avatar design or variation')
        self.foreground, self.background = self.foreground.lower(), self.background.lower()
        if self.foreground not in FOREGROUNDS or self.background not in BACKGROUNDS:
            raise ValueError('Choose colours from the palette')
        return self

class AvatarChoice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['avatar', 'initials']
    style: AvatarStyle | None = None

    @model_validator(mode='after')
    def one_picture(self):
        if (self.kind == 'avatar') != (self.style is not None):
            raise ValueError('An avatar requires a design; initials have no design')
        return self

def readable_style(style):
    """Validate historical keys and hex colours before allowing SVG rendering."""
    if not isinstance(style, dict) or set(style) != {'type', 'variant', 'foreground', 'background'}:
        return None
    if not all(isinstance(v, str) for v in style.values()):
        return None
    if style['variant'] not in LEGACY_VARIANTS.get(style['type'], ()):
        return None
    if not all(re.fullmatch(COLOR, style[k]) for k in ('foreground', 'background')):
        return None
    return {**style, 'foreground': style['foreground'].lower(), 'background': style['background'].lower()}

def picture_data(raw):
    """Return exactly one safe selection; malformed stored data falls back to initials."""
    try:
        picture = json.loads(raw)
        if isinstance(picture, dict):
            if picture.get('kind') == 'photo' and isinstance(picture.get('file'), str) and re.fullmatch(PHOTO_NAME, picture['file']):
                return {'kind': 'photo', 'file': picture['file']}
            if picture.get('kind') == 'avatar' and (style := readable_style(picture.get('style'))):
                return {'kind': 'avatar', 'style': style}
    except (ValueError, TypeError):
        pass
    return {'kind': 'initials'}

def assign_picture(user, picture):
    user.profile_picture = json.dumps(picture, separators=(',', ':'))
    # Legacy fields are migration archives only, never an alternative active selection.
    user.avatar, user.avatar_mode, user.avatar_style = '', 'photo', ''
