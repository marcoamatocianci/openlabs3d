import cadquery as cq
def rack(nx,ny,p,d,h,style):
    # A connected bed lattice with individually supported tube sleeves.
    w=(nx-1)*p+d+8; depth=(ny-1)*p+d+8
    base=cq.Workplane("XY").box(w,depth,3,centered=(True,True,False)).edges("|Z").fillet(4)
    pts=[((i-(nx-1)/2)*p,(j-(ny-1)/2)*p) for i in range(nx) for j in range(ny)]
    for x,y in pts:
        sleeve=cq.Workplane("XY").center(x,y).circle(d/2+2.4).circle(d/2).extrude(h)
        if style>0:
            # Vertical open windows with pointed self-supporting roofs.
            z=h-6; a=d*.28
            cutter=cq.Workplane("XZ").polyline([(-a,5),(a,5),(a,z-a),(0,z),(-a,z-a)]).close().extrude(d+8,both=True).translate((x,y,0))
            sleeve=sleeve.cut(cutter)
            if style==2:
                sleeve=sleeve.cut(cutter.rotate((x,y,0),(x,y,1),90))
        base=base.union(sleeve)
    if style>0:
        for i in range(nx-1):
            for j in range(ny-1):
                x=(i-(nx-2)/2)*p;y=(j-(ny-2)/2)*p
                base=base.cut(cq.Workplane("XY").center(x,y).circle(p*.22).extrude(3))
    return base
result=cq.Compound.makeCompound([rack(nx,ny,p,d,h,s).val().translate((s*150,k*130,0)) for k,(nx,ny,p,d,h) in enumerate([(6,4,18,11.8,32),(4,3,25,17,52),(3,2,39,30,62)]) for s in range(3)])

