"""Create vector engineering sheets from STEP projections and actual plane sections."""

import math
from pathlib import Path

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepLib import BRepLib
from OCP.Bnd import Bnd_Box
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
from OCP.GeomAbs import GeomAbs_Circle
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_EDGE, TopAbs_SOLID, TopAbs_IN
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Ax2, gp_Dir, gp_Pln, gp_Pnt, gp_Trsf
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from shapely.geometry import LineString
from shapely.ops import polygonize, unary_union


# Obtain tight, unit-preserving model bounds for orientation and dimension values.
def bounds(shape):
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box)
    return box.Get()


# Map the chosen longitudinal axis to sheet X and rotate the section orientation.
def read_model(source, axis, angle):
    reader = STEPControl_Reader()
    if reader.ReadFile(str(source)) != IFSelect_RetDone or not reader.TransferRoots():
        raise ValueError('无法读取 STEP 模型。')
    shape = reader.OneShape()
    limits = bounds(shape)
    lengths = [limits[i + 3] - limits[i] for i in range(3)]
    selected = lengths.index(max(lengths)) if axis == 'auto' else 'xyz'.index(axis)
    center = [(limits[i] + limits[i + 3]) / 2 for i in range(3)]
    order = [(0, 1, 2), (1, 2, 0), (2, 0, 1)][selected]
    rows = [[float(j == i) for j in range(3)] for i in order]
    sine, cosine = math.sin(math.radians(angle)), math.cos(math.radians(angle))
    rows = [rows[0], [cosine * a - sine * b for a, b in zip(rows[1], rows[2])],
            [sine * a + cosine * b for a, b in zip(rows[1], rows[2])]]
    matrix = []
    for row in rows:
        matrix.extend(row + [-sum(a * b for a, b in zip(row, center))])
    transform = gp_Trsf()
    transform.SetValues(*matrix)
    shape = BRepBuilderAPI_Transform(shape, transform, True).Shape()
    return shape, 'xyz'[selected]


# Sample analytic edges to bounded-deflection vector polylines, never raster images.
def edge_lines(shape, coordinates=(0, 1)):
    if shape.IsNull():
        return []
    BRepLib.BuildCurves3d_s(shape)
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    lines = []
    while explorer.More():
        edge = TopoDS.Edge_s(explorer.Current())
        explorer.Next()
        if BRep_Tool.Degenerated_s(edge):
            continue
        curve = BRepAdaptor_Curve(edge)
        sampling = GCPnts_QuasiUniformDeflection(curve, 0.025)
        if not sampling.IsDone():
            raise ValueError('部分曲线无法离散为工程图线条。')
        points = []
        for index in range(1, sampling.NbPoints() + 1):
            point = sampling.Value(index)
            values = (point.X(), point.Y(), point.Z())
            points.append(tuple(round(values[i], 5) for i in coordinates))
        if len(points) > 1 and LineString(points).length > 1e-7:
            lines.append(points)
    return lines


# Calculate visible and hidden projection edges using Open CASCADE hidden-line removal.
def projection(shape, direction, horizontal, hidden):
    algorithm = HLRBRep_Algo()
    algorithm.Add(shape)
    algorithm.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(), gp_Dir(*direction), gp_Dir(*horizontal))))
    algorithm.Update()
    algorithm.Hide()
    result = HLRBRep_HLRToShape(algorithm)
    visible = edge_lines(result.VCompound()) + edge_lines(result.OutLineVCompound())
    obscured = edge_lines(result.HCompound()) + edge_lines(result.OutLineHCompound()) if hidden else []
    return {'lines': visible, 'hidden': obscured, 'polygons': []}


# Section the actual solid and hatch only regions classified inside source material.
def section(shape, axis, position):
    normal = (0, 0, 1) if axis == 'z' else (1, 0, 0)
    origin = (0, 0, position) if axis == 'z' else (position, 0, 0)
    operation = BRepAlgoAPI_Section(shape, gp_Pln(gp_Pnt(*origin), gp_Dir(*normal)), True)
    if not operation.IsDone():
        raise ValueError('剖切计算失败，请调整剖切位置。')
    coordinates = (0, 1) if axis == 'z' else (1, 2)
    lines = edge_lines(operation.Shape(), coordinates)
    circles = []
    edges = TopExp_Explorer(operation.Shape(), TopAbs_EDGE)
    while edges.More():
        curve = BRepAdaptor_Curve(TopoDS.Edge_s(edges.Current()))
        if curve.GetType() == GeomAbs_Circle and math.isclose(curve.LastParameter() - curve.FirstParameter(), 2 * math.pi, abs_tol=1e-6):
            circle = curve.Circle()
            center = (circle.Location().X(), circle.Location().Y(), circle.Location().Z())
            circles.append((center[coordinates[0]], center[coordinates[1]], circle.Radius()))
        edges.Next()
    solids = []
    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    while explorer.More():
        solids.append(explorer.Current())
        explorer.Next()
    polygons = []
    for polygon in polygonize(unary_union([LineString(line) for line in lines])):
        point = polygon.representative_point()
        coordinates = (point.x, point.y, position) if axis == 'z' else (position, point.x, point.y)
        if any(BRepClass3d_SolidClassifier(solid, gp_Pnt(*coordinates), 1e-6).State() == TopAbs_IN for solid in solids):
            polygons.append(polygon)
    if not polygons:
        raise ValueError('当前剖切平面未得到闭合材料区域，请调整剖切位置或方向。')
    return {'lines': lines, 'hidden': [], 'polygons': polygons, 'circles': circles}


# Register an embedded Chinese font where available, with a standard CID fallback.
def drawing_font():
    if 'EngineeringCN' not in pdfmetrics.getRegisteredFontNames():
        path = Path('C:/Windows/Fonts/simsun.ttc')
        if path.is_file():
            pdfmetrics.registerFont(TTFont('EngineeringCN', str(path), subfontIndex=0))
        else:
            pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
            return 'STSong-Light'
    return 'EngineeringCN'


# Measure all view geometry so a fixed sheet scale never clips the model.
def view_bounds(view):
    points = [point for line in view['lines'] + view['hidden'] for point in line]
    if not points:
        raise ValueError('未生成有效投影线条。')
    return min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)


# Draw a polyline in millimeter paper coordinates.
def polyline(pdf, points):
    path = pdf.beginPath()
    path.moveTo(*points[0])
    for point in points[1:]:
        path.lineTo(*point)
    pdf.drawPath(path)


# Draw dimension arrows and the true model measurement, independent of print scale.
def dimension(pdf, start, end, label, vertical=False):
    x1, y1 = start
    x2, y2 = end
    pdf.setLineWidth(0.15)
    pdf.line(x1, y1, x2, y2)
    for x, y, sign in [(x1, y1, 1), (x2, y2, -1)]:
        arrow = pdf.beginPath()
        arrow.moveTo(x, y)
        if vertical:
            arrow.lineTo(x - 0.6, y + sign * 2)
            arrow.lineTo(x + 0.6, y + sign * 2)
        else:
            arrow.lineTo(x + sign * 2, y - 0.6)
            arrow.lineTo(x + sign * 2, y + 0.6)
        arrow.close()
        pdf.drawPath(arrow, fill=1)
    pdf.saveState()
    pdf.translate((x1 + x2) / 2, (y1 + y2) / 2)
    if vertical:
        pdf.rotate(90)
    width = pdf.stringWidth(label) + 2
    pdf.setFillColorRGB(1, 1, 1)
    pdf.rect(-width / 2, -0.7, width, 3.5, stroke=0, fill=1)
    pdf.setFillColorRGB(0, 0, 0)
    pdf.drawCentredString(0, 0, label)
    pdf.restoreState()


# Place projected geometry, clipped hatch strokes and overall dimension annotations.
def draw_view(pdf, view, box, scale, label, dimensions, centerlines, font):
    left, bottom, width, height = box
    x0, y0, x1, y1 = view_bounds(view)
    offset_x = left + width / 2 - (x0 + x1) * scale / 2
    offset_y = bottom + height / 2 - (y0 + y1) * scale / 2

    # Convert model-space positions into the common sheet scale.
    def paper(point):
        return point[0] * scale + offset_x, point[1] * scale + offset_y

    pdf.saveState()
    pdf.setFont(font, 2.8)
    for polygon in view['polygons']:
        pdf.saveState()
        clip = pdf.beginPath()
        for ring in [polygon.exterior, *polygon.interiors]:
            points = [paper(point) for point in ring.coords]
            clip.moveTo(*points[0])
            for point in points[1:]:
                clip.lineTo(*point)
            clip.close()
        pdf.clipPath(clip, stroke=0, fill=0, fillMode=0)
        pdf.setLineWidth(0.12)
        start = left - height
        while start < left + width:
            pdf.line(start, bottom, start + height, bottom + height)
            start += 2.5
        pdf.restoreState()
    pdf.setLineWidth(0.15)
    pdf.setDash(2, 1)
    for line in view['hidden']:
        polyline(pdf, [paper(point) for point in line])
    pdf.setDash()
    pdf.setLineWidth(0.3)
    for line in view['lines']:
        polyline(pdf, [paper(point) for point in line])
    lo, hi = paper((x0, y0)), paper((x1, y1))
    if centerlines:
        pdf.setDash([5, 1, 1, 1])
        pdf.setLineWidth(0.12)
        pdf.line(lo[0] - 4, offset_y, hi[0] + 4, offset_y)
        pdf.line(offset_x, lo[1] - 4, offset_x, hi[1] + 4)
        pdf.setDash()
    if dimensions:
        measured_width, measured_height = view.get('dimensionValues', (x1 - x0, y1 - y0))
        pdf.setLineWidth(0.15)
        for x in (lo[0], hi[0]):
            pdf.line(x, hi[1] + 1, x, hi[1] + 10)
        dimension(pdf, (lo[0], hi[1] + 8), (hi[0], hi[1] + 8), f'{measured_width:.2f}')
        for y in (lo[1], hi[1]):
            pdf.line(lo[0] - 1, y, lo[0] - 10, y)
        dimension(pdf, (lo[0] - 8, lo[1]), (lo[0] - 8, hi[1]), f'{measured_height:.2f}', vertical=True)
    if view.get('diameter'):
        cx, cy, radius = min(view['circles'], key=lambda circle: circle[2])
        dimension(pdf, paper((cx - radius, cy)), paper((cx + radius, cy)), f'Ø{2 * radius:.2f}')
    if view.get('cut'):
        axis, position, mark = view['cut']
        pdf.setLineWidth(0.35)
        pdf.setDash([6, 1, 1, 1])
        if axis == 'x':
            x, _ = paper((position, 0))
            pdf.line(x, lo[1] - 4, x, hi[1] + 4)
            pdf.drawString(x + 2, lo[1] - 4, mark)
            pdf.drawString(x + 2, hi[1] + 3, mark)
        else:
            _, y = paper((0, position))
            pdf.line(lo[0] - 4, y, hi[0] + 4, y)
            pdf.drawString(lo[0] - 5, y + 2, mark)
            pdf.drawString(hi[0] + 3, y + 2, mark)
        pdf.setDash()
    pdf.drawCentredString(left + width / 2, bottom - 5, label)
    pdf.restoreState()


# Wrap user-supplied engineering notes without overflowing the reserved footer.
def wrapped_lines(text, font, size, width):
    result = []
    for paragraph in text.splitlines():
        line = ''
        for character in paragraph:
            if pdfmetrics.stringWidth(line + character, font, size) > width:
                result.append(line)
                line = ''
            line += character
        result.append(line)
    return result


# Add a reference-inspired title block without copying authors, approvals or requirements.
def draw_footer(pdf, width, settings, scale, font, source_axis):
    block_width = min(174, width * 0.46)
    left, bottom = width - 12 - block_width, 12
    pdf.setLineWidth(0.25)
    pdf.rect(left, bottom, block_width, 49)
    for y in (22, 32, 42, 51):
        pdf.line(left, y, width - 12, y)
    pdf.setFont(font, 3)
    pdf.drawString(left + 3, 54.5, settings['organization'] or '工程图')
    pdf.drawString(left + 3, 45, '名称：' + settings['title'])
    pdf.drawString(left + 3, 35, '图号：' + (settings['drawingNumber'] or '未填写'))
    pdf.drawString(left + 3, 25, '材料：' + (settings['material'] or '未填写'))
    ratio = f'1:{1 / scale:g}' if scale < 1 else f'{scale:g}:1'
    pdf.drawString(left + 3, 15.5, f'比例 {ratio}    单位 mm    {settings["paper"]}    第 1 张 / 共 1 张')
    pdf.setFont(font, 2.8)
    pdf.drawString(15, 62, '技术要求 / 说明')
    notes = settings['notes'] or '未填写工艺、公差及表面要求。'
    lines = wrapped_lines(notes, font, 2.6, left - 23)
    if len(lines) > 10:
        raise ValueError('技术要求超出图框可用区域，请减少文字或选择 A3 图幅。')
    pdf.setFont(font, 2.6)
    for index, line in enumerate(lines):
        pdf.drawString(15, 56 - index * 3.5, line)
    pdf.setFont(font, 2.4)
    pdf.drawString(15, 15, f'长轴：原模型 {source_axis.upper()}；尺寸来自模型几何，未恢复原始公差/螺纹标注。')


# Produce a single vector sheet and return reproducible drawing settings and measurements.
def generate_pdf(source, target, settings):
    shape, source_axis = read_model(source, settings['axis'], settings['rotation'])
    limits = bounds(shape)
    transverse = limits[0] + (limits[3] - limits[0]) * settings['sectionPercent'] / 100
    front = projection(shape, (0, 0, 1), (1, 0, 0), settings['hiddenLines'])
    end = projection(shape, (1, 0, 0), (0, 1, 0), settings['hiddenLines'])
    longitudinal = section(shape, 'z', settings['sectionOffset'])
    cross = section(shape, 'x', transverse)
    front['dimensionValues'] = (limits[3] - limits[0], limits[4] - limits[1])
    end['dimensionValues'] = (limits[4] - limits[1], limits[5] - limits[2])
    front['cut'] = ('x', transverse, 'B')
    end['cut'] = ('y', settings['sectionOffset'], 'A')
    cross['diameter'] = bool(settings['dimensions'] and cross['circles'])
    width, height = (420, 297) if settings['paper'] == 'A3' else (297, 210)
    usable = width - 44
    main_width, end_width = usable * 0.67, usable * 0.29
    row_height = (height - 112) / 2
    boxes = [(26, height - 24 - row_height, main_width, row_height),
             (width - 16 - end_width, height - 24 - row_height, end_width, row_height),
             (26, 78, main_width, row_height), (width - 16 - end_width, 78, end_width, row_height)]
    views = [front, end, longitudinal, cross]
    fit = min(min((box[2] - 30) / max(view_bounds(view)[2] - view_bounds(view)[0], 1e-6),
                  (box[3] - 18) / max(view_bounds(view)[3] - view_bounds(view)[1], 1e-6))
              for view, box in zip(views, boxes))
    scale = settings['scale']
    if not scale:
        options = [0.01, 0.02, 0.025, 0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 5, 10]
        scale = max((value for value in options if value <= fit), default=0)
    if not scale or scale > fit:
        raise ValueError('所选比例无法放入图框，请使用自动比例或选择更小比例。')
    font = drawing_font()
    pdf = canvas.Canvas(str(target), pagesize=(width * mm, height * mm), pageCompression=1)
    pdf.setTitle(settings['title'] + ' - 工程图')
    pdf.scale(mm, mm)
    pdf.setLineWidth(0.4)
    pdf.rect(12, 12, width - 24, height - 24)
    labels = ['主视图（沿图纸 Z 方向）', '右向端视图（独立标注）',
              f'A-A 纵向剖视图（Z = {settings["sectionOffset"]:g} mm）',
              f'B-B 横截面（距左端 {transverse - limits[0]:.2f} mm）']
    for index, (view, box, label) in enumerate(zip(views, boxes, labels)):
        draw_view(pdf, view, box, scale, label, settings['dimensions'] and index < 2,
                  settings['centerlines'], font)
    draw_footer(pdf, width, settings, scale, font, source_axis)
    pdf.showPage()
    pdf.save()
    return {'paper': settings['paper'], 'scale': scale, 'axis': source_axis,
            'dimensionsMm': [limits[i + 3] - limits[i] for i in range(3)],
            'views': 4, 'sectionRegions': [len(longitudinal['polygons']), len(cross['polygons'])],
            'curveDeflectionMm': 0.025}
