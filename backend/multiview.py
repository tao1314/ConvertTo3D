"""Evidence-based recognition of coaxial stepped parts from paired front/side views.

This bounded recognizer does not treat arbitrary view islands as separate solids.
All radii must be supported by front circles and symmetric side-view lines.
"""
from collections import defaultdict
import math
import re

TOL = 1e-4


def near(a, b, tolerance=TOL):
    return abs(a-b) <= tolerance


def merge_stages(stages):
    result = []
    for stage in stages:
        if result and near(result[-1]['radius'], stage['radius']) and near(result[-1]['end'], stage['start']):
            result[-1]['end'] = stage['end']
        else:
            result.append(stage.copy())
    return result


def recognize_parts(layouts):
    candidates = []
    for layout in layouts:
        circles = [e for e in layout['entities'] if e['type'] == 'CIRCLE' and e['planar'] and not e['construction']]
        clusters = defaultdict(list)
        for circle in circles:
            clusters[tuple(round(v, 4) for v in circle['center'])].append(circle)
        for group in clusters.values():
            if len(group) < 2:
                continue
            cx, cy = group[0]['center']
            radii = sorted(set(round(e['radius'], 6) for e in group))
            outer_radius = max(radii)
            # Currently supports front view on the left and an aligned axial side view on the right.
            lines = [e for e in layout['entities'] if e['type'] == 'LINE' and e['planar']
                     and min(p[0] for p in e['points']) > cx+outer_radius+TOL]
            pairs = []
            for line in lines:
                a, b = line['points'][0], line['points'][-1]
                if not near(a[1], b[1]) or a[1] <= cy:
                    continue
                radius = a[1]-cy
                if not any(near(radius, r) for r in radii):
                    continue
                start, end = sorted([a[0], b[0]])
                reflected = next((other for other in lines if near(other['points'][0][1], cy-radius)
                                  and near(other['points'][-1][1], cy-radius)
                                  and near(min(p[0] for p in other['points']), start)
                                  and near(max(p[0] for p in other['points']), end)), None)
                if reflected and end-start > TOL:
                    pairs.append({'start': start, 'end': end, 'radius': radius,
                                  'sources': [line['sourceHandle'], reflected['sourceHandle']]})
            if len(pairs) < 2:
                continue
            stops = sorted(set(round(v, 5) for p in pairs for v in (p['start'], p['end'])))
            # Disallow a guessed axis profile if an interval has missing or conflicting boundaries.
            outer, inner = [], []
            for left, right in zip(stops, stops[1:]):
                middle = (left+right)/2
                boundaries = sorted(set(round(p['radius'], 5) for p in pairs if p['start']-TOL < middle < p['end']+TOL))
                if len(boundaries) != 2:
                    outer = []
                    break
                inner.append({'start': left-stops[0], 'end': right-stops[0], 'radius': boundaries[0]})
                outer.append({'start': left-stops[0], 'end': right-stops[0], 'radius': boundaries[1]})
            if not outer or not near(max(s['radius'] for s in outer), outer_radius):
                continue
            outer, inner = merge_stages(outer), merge_stages(inner)
            dims = [a for a in layout['annotations'] if a['type'] == 'DIMENSION']
            supported_diameters = [d['measurement'] for d in dims if d['dimensionType'] == 3 and d['measurement'] is not None]
            if not all(any(near(2*r, diameter) for diameter in supported_diameters) for r in radii):
                continue
            holes, notes = [], []
            expected_holes = [c for c in circles if TOL < math.dist(c['center'], [cx,cy])
                              and math.dist(c['center'], [cx,cy])+c['radius'] <= outer_radius+TOL]
            for circle in circles:
                x, y = circle['center'][0]-cx, circle['center'][1]-cy
                distance = math.hypot(x, y)
                if distance <= TOL or distance+circle['radius'] > outer_radius+TOL:
                    continue
                nominal = 2*circle['radius']
                thread = next((d['text'] for d in dims if re.fullmatch(r'M\s*\d+(?:\.\d+)?', d['text'], re.I)
                               and d['measurement'] is not None and near(d['measurement'], nominal)), None)
                # Dimension overrides have priority over tiny drafting deviations only when anchored to this hole row.
                for dim in dims:
                    anchors = dim.get('definitionPoints', {})
                    p, q = anchors.get('defpoint2'), anchors.get('defpoint3')
                    if not p or not q or not re.fullmatch(r'\d+(?:\.\d+)?', dim['text']):
                        continue
                    if near(p[0], q[0]) and near((p[1]+q[1])/2, cy) and any(near(circle['center'][1], v[1]) for v in (p,q)):
                        override = float(dim['text'])
                        if abs(override-abs(p[1]-q[1])) <= 0.1:
                            y = math.copysign(override/2, y)
                            note = f'孔距按标注 {override:g} 优先于绘制距离 {abs(p[1]-q[1]):.6f}（尺寸 {dim["sourceHandle"]}）。'
                            if note not in notes:
                                notes.append(note)
                if not thread:
                    # Require matching hidden side-view edges before inferring a through-hole group.
                    same_row = [c for c in circles if near(c['radius'], circle['radius']) and near(c['center'][0], cx)]
                    evidence = []
                    for c in same_row:
                        edges = [l for l in lines if near(l['points'][0][1], l['points'][-1][1])
                                 and any(near(l['points'][0][1], c['center'][1]+sign*c['radius']) for sign in (-1,1))]
                        if len(edges) >= 2:
                            evidence.extend(l['sourceHandle'] for l in edges)
                    if not evidence:
                        continue
                else:
                    evidence = []
                holes.append({'x': round(x, 7), 'y': round(y, 7), 'diameter': nominal,
                              'thread': thread, 'sourceHandle': circle['sourceHandle'], 'sideEvidence': evidence})
            if len(holes) != len(expected_holes):
                continue  # Do not present an incomplete hole set as a recognized complete part.
            # Solve an explicitly overridden vertical pitch together with an aligned diagonal pitch.
            for dim in dims:
                anchors = dim.get('definitionPoints', {})
                p, q = anchors.get('defpoint2'), anchors.get('defpoint3')
                if dim['dimensionType'] != 1 or p is None or q is None or not dim['measurement']:
                    continue
                first = next((c for c in circles if math.dist(c['center'], p) < TOL), None)
                last = next((c for c in circles if math.dist(c['center'], q) < TOL), None)
                if not first or not last:
                    continue
                a = next((h for h in holes if h['sourceHandle'] == first['sourceHandle']), None)
                b = next((h for h in holes if h['sourceHandle'] == last['sourceHandle']), None)
                if not a or not b or not a['thread'] or a['thread'] != b['thread']:
                    continue
                if not near(a['x'], -b['x']) or not near(a['y'], -b['y']):
                    continue
                dy = abs(b['y']-a['y'])
                if near(dy, abs(q[1]-p[1])):
                    continue
                diagonal = float(dim['text']) if re.fullmatch(r'\d+(?:\.\d+)?', dim['text']) else dim['measurement']
                if diagonal <= dy:
                    holes = []
                    break
                dx = math.sqrt(diagonal**2-dy**2)
                old_x = abs(a['x'])
                for h in holes:
                    if h['thread'] == a['thread'] and near(abs(h['x']), old_x):
                        h['x'] = math.copysign(dx/2, h['x'])
                notes.append(f'孔距联立竖向 {dy:g} 与对角 {diagonal:g}，解得水平间距 {dx:.6f}（尺寸 {dim["sourceHandle"]}）。')
            if len(holes) != len(expected_holes):
                continue
            candidates.append({'id': f'part{len(candidates)}', 'kind': 'coaxial-stepped-flange',
                               'label': '同轴台阶端盖 · 多视图单零件', 'layout': layout['name'],
                               'frontCenter': [cx, cy], 'frontRadius': outer_radius,
                               'sideBounds': [stops[0], cy-outer_radius, stops[-1], cy+outer_radius],
                               'totalLength': stops[-1]-stops[0], 'outerStages': outer, 'innerStages': inner,
                               'holes': holes, 'dimensionNotes': notes,
                               'evidence': {'frontCircles': [e['sourceHandle'] for e in group],
                                            'sideEdges': [s for p in pairs for s in p['sources']]},
                               'assumptions': ['右侧视图与正视图同尺度且轴线对齐；两视图共同描述一个零件。',
                                               'M 标注孔仅在用户选择后按图示公称直径通孔简化，不生成螺纹牙型或底孔。',
                                               'R3 未指定作用边，本次不施加圆角或倒角。']})
    return candidates
