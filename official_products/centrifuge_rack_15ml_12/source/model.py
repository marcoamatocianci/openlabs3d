import cadquery as cq
# Millimeters. Vertical blind bores, 3 mm floor; upright support-free print.
length,width,height=110,85,52
columns,rows=4,3
pitch_x,pitch_y=25,25
bore_diameter=17
floor=3
points=[((i-(columns-1)/2)*pitch_x,(j-(rows-1)/2)*pitch_y) for i in range(columns) for j in range(rows)]
result=cq.Workplane("XY").box(length,width,height,centered=(True,True,False)).edges("|Z").fillet(2)
result=result.faces(">Z").workplane().pushPoints(points).hole(bore_diameter,height-floor)

