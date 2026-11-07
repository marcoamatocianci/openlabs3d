"""Manufacturing constraints for desktop FDM. One place, so a different process can replace them.

Walls, overhang, holes and features follow the conservative FDM defaults in the dfam-check process-limits table
(Hubs design guides, consistent with ISO/ASTM 52910). These are design rules, not measured strength.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class FdmRules:
    nozzle_mm: float = .4
    layer_mm: float = .2
    min_wall_mm: float = 1.6            # unsupported wall, 4 perimeters at 0.4 mm
    bore_web_mm: float = 2.4            # material kept between two neighbouring bores
    sleeve_wall_mm: float = 2.0         # Lightweight sleeve around a large tube
    fine_wall_mm: float = 1.6           # Lightweight funnel around a microtube: short, so the minimum wall is enough
    collar_mm: float = 4.5              # Lightweight ring at the top of a tube's funnel, and the bridges between rings
    bridge_mm: float = 3.0              # Lightweight bridge between two collars, in plan
    pillar_mm: float = 4.0              # Lightweight: least sleeve left standing between two windows
    web_mm: float = 2.0                 # Lightweight vertical web between sleeves
    rib_mm: float = 4.0                 # Lightweight base rib
    frame_mm: float = 5.5               # Lightweight base frame
    base_mm: float = 3.2                # Lightweight base plate and seat pad
    floor_mm: float = 2.4               # Premium floor under a seat: twelve layers, on a solid body
    grip_share: float = .85             # Premium: straight wall held above the cone, as a share of the tube's width
    grip_min_mm: float = 20.0           # ... and at least this, so a long thin tube stays upright (about 2 degrees of play)
    exposed_share: float = .46          # Premium: share of a tube's length left above the deck, for fingers
    # What the height control may do, for any tube. Design rules, not measured strength.
    low_grip_share: float = .4          # at the lowest: straight wall kept past the cone, as a share of the tube's width
    low_grip_min_mm: float = 10.0       # ... and at least this
    high_exposed_share: float = .38     # at the highest: share of a tube's length still left above the deck
    high_exposed_min_mm: float = 12.0   # ... and at least this, for fingers on a short tube
    outer_wall_mm: float = 3.2          # Premium: flat deck left between a bore and where the body starts to curve away
    tuck_max_deg: float = 30.0          # Premium: the steepest the convex wall may lean out above the bed, from vertical
    label_rake_deg: float = 30.0        # Lightweight nameplate leans back this far from vertical, to read from above and print cleanly
    label_flat_max_mm: float = 1.6      # Premium: the deepest the soft flat for a name may cut into the convex wall
    entry_chamfer_mm: float = .8
    self_support_deg: float = 45.0      # from horizontal
    window_roof_deg: float = 62.0       # steeper than the limit, so window roofs print without support, and slender
    max_bridge_mm: float = 10.0
    min_hole_mm: float = 2.0
    min_feature_mm: float = .8
    min_text_stroke_mm: float = .68     # a little under two extrusion widths; slicers fill this with gap fill
    min_text_size_mm: float = 6.0
    max_text_size_mm: float = 16.0
    engrave_depth_mm: float = .8        # four layers
    emboss_height_mm: float = .6        # three layers
    printer_margin_mm: float = 5.0      # kept free on each side for skirt or brim
    printer_margin_z_mm: float = 5.0
    tip_angle_deg: float = 20.0         # the loaded rack should tilt at least this far before tipping
    min_bed_contact_mm2: float = 400.0

RULES = FdmRules()

# Hard limits on what one request can ask the server to build.
MAX_TUBES = 120
MAX_FOOTPRINT_MM = 500.0
