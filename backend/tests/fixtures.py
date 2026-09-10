"""Synthetic, non-user-owned multi-view drawing for reproducible tests."""
import ezdxf


def endcap_drawing(path, shift=0, missing_side=False):
    doc = ezdxf.new('R2010')
    doc.header['$INSUNITS'] = 4
    m = doc.modelspace()
    cx, cy, x0 = 1000+shift, 2000+shift, 1100+shift
    for radius in (55, 37.5, 30, 27.5):
        m.add_circle((cx,cy), radius)
        m.add_diameter_dim((cx,cy), radius=radius, angle=30).render()
    for x, y in ((0,45),(0,-45),(-45,0),(45,0)):
        m.add_circle((cx+x,cy+y), 6.25)
    for x, y in ((24,24),(24,-24),(-24,24),(-24,-24)):
        m.add_circle((cx+x,cy+y), 2.5)
    m.add_diameter_dim((cx+24,cy+24), radius=2.5, angle=30, text='M5').render()
    if not missing_side:
        for start, end, radius in ((0,10,55),(10,30,37.5),(0,5,27.5),(5,30,30)):
            for sign in (-1,1):
                m.add_line((x0+start,cy+sign*radius),(x0+end,cy+sign*radius))
        for y in (-51.25,-38.75,38.75,51.25):
            m.add_line((x0,cy+y),(x0+10,cy+y))
    doc.saveas(path)
    return path
