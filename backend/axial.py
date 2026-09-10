"""Reconstruct symmetric axial sections and their end-view blind holes as one solid."""

import math

from shapely.affinity import affine_transform
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

TOL = 1e-4


# Keep the shared modeling engine's profile contract for reconstructed sections.
def polygon_profile(polygon):
    points = list(polygon.exterior.coords)
    holes = [list(ring.coords) for ring in polygon.interiors]
    return {
        'outer': {'type': 'polygon', 'points': points},
        'holes': [{'type': 'polygon', 'points': ring} for ring in holes],
        'bounds': list(polygon.bounds),
        'preview': {'outer': points, 'holes': holes},
    }


# Require opposing section halves, matching end circles and an axial dimension.
def recognize_axial_sections(layouts):
    candidates = []
    for layout in layouts:
        circles = [e for e in layout['entities']
                   if e['type'] == 'CIRCLE' and e['planar'] and not e['construction']]
        polygons = [(p['id'], Polygon(p['preview']['outer'], p['preview']['holes']))
                    for p in layout['profiles']]
        for front in circles:
            cx, cy = front['center']
            radius = front['radius']
            central = [c for c in circles if math.dist(c['center'], [cx, cy]) < TOL
                       and c['radius'] < radius - TOL]
            if len(central) != 1:
                continue
            upper = [(key, p) for key, p in polygons
                     if p.bounds[2] < cx - radius - TOL and p.bounds[1] > cy + TOL
                     and p.bounds[3] <= cy + radius + TOL]
            if not upper:
                continue
            main_id, main = max(upper, key=lambda item: item[1].area)
            left, _, right, _ = main.bounds
            selected = [(key, p) for key, p in upper
                        if p.bounds[0] >= left - TOL and p.bounds[2] <= right + TOL]
            section = unary_union([p for _, p in selected])
            if section.geom_type != 'Polygon' or section.interiors:
                continue
            lower = [p for _, p in polygons if p.bounds[0] >= left - TOL
                     and p.bounds[2] <= right + TOL and p.bounds[3] < cy - TOL
                     and p.bounds[1] >= cy - radius - TOL]
            reflected = affine_transform(unary_union(lower), [1, 0, 0, -1, 0, 2 * cy])
            if section.symmetric_difference(reflected).area > section.area * 1e-5:
                continue
            if (abs(section.bounds[3] - cy - radius) > TOL
                    or abs(section.bounds[1] - cy - central[0]['radius']) > TOL):
                continue
            dimensions = [d for d in layout['annotations'] if d['type'] == 'DIMENSION']
            length_dims = []
            for dim in dimensions:
                anchors = dim.get('definitionPoints', {})
                a, b = anchors.get('defpoint2'), anchors.get('defpoint3')
                if (a and b and dim.get('measurement') is not None
                        and abs(min(a[0], b[0]) - left) < TOL
                        and abs(max(a[0], b[0]) - right) < TOL
                        and abs(dim['measurement'] - (right - left)) < TOL):
                    length_dims.append(dim['sourceHandle'])
            axes = [e['sourceHandle'] for e in layout['entities']
                    if e['type'] == 'LINE' and e['construction'] and e['planar']
                    and all(abs(p[1] - cy) < TOL for p in e['points'])
                    and min(p[0] for p in e['points']) < right
                    and max(p[0] for p in e['points']) > left]
            if not length_dims or not axes:
                continue
            holes, notes = [], []
            offsets = [c for c in circles if math.dist(c['center'], [cx, cy]) > TOL
                       and math.dist(c['center'], [cx, cy]) + c['radius'] < radius]
            if any(not any(math.dist(other['center'], [c['center'][0], 2 * cy - c['center'][1]]) < TOL
                           and abs(other['radius'] - c['radius']) < TOL for other in offsets)
                   for c in offsets):
                continue
            for circle in offsets:
                hole = recognize_blind_hole(circle, polygons, left, right, cx, cy)
                if hole is None:
                    break
                holes.append(hole)
                if abs(hole['drawnRadius'] - circle['radius']) > TOL:
                    notes.append(f"孔径采用端面圆 Ø{2 * circle['radius']:g}，剖视图绘制为 "
                                 f"Ø{2 * hole['drawnRadius']:g}；孔深及钻尖按剖视轮廓。")
            else:
                # Off-axis cavities must be explained by matched holes, not revolved into grooves.
                explained = unary_union([Polygon(h['sourceOutline']) for h in holes])
                additions = section.difference(main)
                unexplained = additions.difference(explained)
                # Only the outer thread representation band may remain above the main section.
                if not unexplained.is_empty and unexplained.bounds[1] < main.bounds[3] - TOL:
                    continue
                local = affine_transform(section, [1, 0, 0, 1, -left, -cy])
                assumptions = [
                    '轴向剖视图与端面图同尺度、同轴，合并上下对称剖面后生成一个实体。',
                    '外螺纹按图示公称外形简化，不生成螺旋牙型；保留图示环槽、倒角和流道轮廓。',
                    '偏心孔按端面圆直径及剖视图盲孔深度、钻尖重建，不按通孔处理。',
                    '流道圆弧沿用解析器 0.01 图纸单位离散精度。',
                ]
                candidates.append({
                    'kind': 'axial-section', 'label': '轴向剖面 + 端面 · 整体零件',
                    'layout': layout['name'], 'frontCenter': [cx, cy], 'frontRadius': radius,
                    'sideBounds': [left, cy - radius, right, cy + radius],
                    'totalLength': right - left, 'section': polygon_profile(local),
                    'outerStages': [], 'innerStages': [], 'holes': holes,
                    'dimensionNotes': list(dict.fromkeys(notes)), 'assumptions': assumptions,
                    'evidence': {'profiles': [key for key, _ in selected],
                                 'mainProfile': main_id, 'axis': axes,
                                 'lengthDimensions': length_dims,
                                 'frontCircles': [front['sourceHandle'], central[0]['sourceHandle']]},
                })
    return candidates


# Match each end-view hole to a symmetric, closed blind-hole section on the left face.
def recognize_blind_hole(circle, polygons, left, right, cx, cy):
    hx, hy = circle['center']
    radius = circle['radius']
    if abs(hx - cx) > TOL:
        return None
    pieces = [(key, p) for key, p in polygons
              if p.bounds[0] >= left - TOL and p.bounds[2] < right - TOL
              and p.bounds[1] >= hy - radius * 1.3
              and p.bounds[3] <= hy + radius * 1.3]
    cavity = unary_union([p for _, p in pieces])
    if cavity.geom_type != 'Polygon' or cavity.interiors or abs(cavity.bounds[0] - left) > TOL:
        return None
    mirror = affine_transform(cavity, [1, 0, 0, -1, 0, 2 * hy])
    if cavity.symmetric_difference(mirror).area > cavity.area * 1e-5:
        return None
    half = cavity.intersection(box(left - 1, hy, right + 1, hy + radius * 2))
    if half.geom_type != 'Polygon':
        return None
    coords = list(half.exterior.coords)
    horizontal = [(abs(y - hy), abs(x - nx))
                  for (x, y), (nx, ny) in zip(coords, coords[1:])
                  if abs(y - ny) < TOL and y > hy + TOL]
    if not horizontal:
        return None
    drawn_radius = max(horizontal, key=lambda item: item[1])[0]
    if abs(drawn_radius - radius) > radius * 0.06:
        return None
    # Preserve chamfer offsets and the drill tip while honoring the end-view diameter.
    corrected = [(x - left, y - hy + radius - drawn_radius if y > hy + TOL else 0)
                 for x, y in coords]
    tool = Polygon(corrected)
    if not tool.is_valid or tool.area <= TOL:
        return None
    return {'x': hx - cx, 'y': hy - cy, 'diameter': 2 * radius, 'thread': None,
            'depth': cavity.bounds[2] - left, 'drawnRadius': drawn_radius,
            'profile': polygon_profile(tool), 'sourceOutline': list(cavity.exterior.coords),
            'sourceHandle': circle['sourceHandle'], 'sectionProfiles': [key for key, _ in pieces]}


# Reuse the shared revolution/export pipeline and remove the matched off-axis cavities.
def build_axial_section(part, params, directory):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Trsf, gp_Vec
    from backend.modeling import profile_shape, solid_stats, export_solid

    scale = params['mmPerUnit']
    revolve = {'mmPerUnit': scale, 'operation': 'revolve', 'axis': 'x',
               'axisOffset': 0, 'angleDeg': 360}
    shape = profile_shape(part['section'], revolve)
    features = [{'type': 'merged-axial-section', 'sources': part['evidence']}]
    for hole in part['holes']:
        tool = profile_shape(hole['profile'], revolve)
        transform = gp_Trsf()
        transform.SetTranslation(gp_Vec(0, hole['y'] * scale, hole['x'] * scale))
        tool = BRepBuilderAPI_Transform(tool, transform, True).Shape()
        before = solid_stats(shape)['volumeMm3']
        cut = BRepAlgoAPI_Cut(shape, tool)
        if not cut.IsDone():
            raise ValueError('盲孔与主体的布尔运算失败。')
        cut.SimplifyResult(True, True)
        shape = cut.Shape()
        stats = solid_stats(shape)
        if not stats['valid'] or stats['solids'] != 1 or before - stats['volumeMm3'] < 1e-8:
            raise ValueError('盲孔未形成有效单实体，请检查视图对应关系。')
        features.append({'type': 'blind-hole-with-tip', 'diameterMm': hole['diameter'] * scale,
                         'depthIncludingTipMm': hole['depth'] * scale,
                         'sourceHandle': hole['sourceHandle']})
    return {**export_solid(shape, directory), 'featureCount': len(features),
            'features': features, 'threadMode': 'nominal-envelope',
            'edgeTreatment': 'section-outline', 'assumptions': part['assumptions']}
