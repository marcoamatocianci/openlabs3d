"""OpenLabs3D BRIDGE family. Millimeters; upright FDM orientation."""
import cadquery as cq

def build(length, width, height, columns, rows, pitch, bore):
    # Rounded continuous canopy and plinth, joined by intersecting vaulted webs.
    body = cq.Workplane("XY").box(length, width, height, centered=(True,True,False)).edges("|Z").fillet(7)
    body = body.faces(">Z").edges().fillet(1.6)
    body = body.faces("<Z").edges().chamfer(.8)
    xs=[(i-(columns-1)/2)*pitch for i in range(columns)]
    ys=[(j-(rows-1)/2)*pitch for j in range(rows)]
    # 45 degree vault roofs grow inward from vertical piers, no floating deck.
    half=(pitch-5)/2
    apex=height-4
    shoulder=apex-half
    profile=[(-half+2,4),(half-2,4),(half,shoulder),(0,apex),(-half,shoulder)]
    for y in ys:
        tool=cq.Workplane("YZ").polyline(profile).close().extrude(length+2,both=True).edges("|X").fillet(2).translate((0,y,0))
        body=body.cut(tool)
    for x in xs:
        tool=cq.Workplane("XZ").polyline(profile).close().extrude(width+2,both=True).edges("|Y").fillet(2).translate((x,0,0))
        body=body.cut(tool)
    # Smooth entry cones; full-clearance upper bores. Solid base catches tube tips.
    for x in xs:
        bore_tool=cq.Workplane("XY").workplane(offset=4).center(x,0).pushPoints([(0,y) for y in ys]).circle(bore/2).extrude(height)
        body=body.cut(bore_tool)
        for y in ys:
            entry=cq.Solid.makeCone(bore/2,bore/2+1.1,1.1,cq.Vector(x,y,height-1.1))
            body=body.cut(entry)
            # Shallow locating dimples keep conical tips from skating across the base.
            seat=cq.Solid.makeCone(1.2,2.4,1.2,cq.Vector(x,y,2.8))
            body=body.cut(seat)
    return body

PARAMETERS = [118,82,32,6,4,18,11.8]
result = build(*PARAMETERS)
