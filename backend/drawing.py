"""Local DWG conversion and DXF geometry inspection. No cloud upload."""
from collections import Counter
import math
import os
from pathlib import Path
import subprocess

import ezdxf
from ezdxf import path as dxfpath
from shapely.geometry import LineString
from shapely.ops import polygonize, unary_union

ROOT = Path(__file__).resolve().parents[1]
MAX_ENTITIES = 30000


def converter_path():
    configured = os.getenv('DWG2DXF_PATH')
    if configured and Path(configured).is_file():
        return Path(configured)
    return next((ROOT / 'tools' / 'libredwg').rglob('dwg2dxf.exe'), None)


def convert_dwg(source, target):
    converter = converter_path()
    if not converter:
        raise ValueError('缺少 LibreDWG：请运行 scripts/setup.ps1，或设置 DWG2DXF_PATH。')
    result = subprocess.run([str(converter), '-o', str(target), str(source)],
                            capture_output=True, timeout=90)
    if result.returncode or not target.is_file():
        diagnostic = result.stderr.decode('utf-8', errors='replace')[-1200:]
        raise ValueError('DWG 转换失败，文件可能损坏或包含不支持的对象。' + diagnostic)
    # LibreDWG 0.14 emits null DICTIONARY entries in some R2000 exports.
    # These are missing metadata references, not geometry. Keep all entity data.
    removed = clean_null_dictionary_entries(target)
    return result.stderr.decode('utf-8', errors='replace')[-3000:] + f'\nRemoved {removed} null dictionary references.'


def clean_null_dictionary_entries(target):
    lines = Path(target).read_bytes().splitlines(keepends=True)
    result, current, removed, index = [], b'', 0, 0
    while index + 1 < len(lines):
        code, value = lines[index].strip(), lines[index+1].strip()
        if code == b'0':
            current = value
        if (current in (b'DICTIONARY', b'ACDBDICTIONARYWDFLT') and code == b'3'
                and index+3 < len(lines) and lines[index+2].strip() in (b'350', b'360')
                and lines[index+3].strip() == b'0'):
            removed += 1
            index += 4
            continue
        result.extend(lines[index:index+2])
        index += 2
    if index < len(lines):
        result.append(lines[index])
    if removed:
        Path(target).write_bytes(b''.join(result))
    return removed


def point(v):
    return [round(float(v[0]), 7), round(float(v[1]), 7)]


def flatten(entities, inherited_layer='0', depth=0):
    if depth > 16:
        raise ValueError('块嵌套过深，无法安全解析。')
    for entity in entities:
        layer = entity.dxf.get('layer', '0')
        if layer == '0':
            layer = inherited_layer
        if entity.dxftype() == 'INSERT':
            block = entity.doc.blocks.get(entity.dxf.name) if entity.doc else None
            if block is None or block.block.dxf.flags & 4:
                yield entity, layer
            else:
                yield from flatten(entity.virtual_entities(), layer, depth + 1)
        else:
            yield entity, layer


def parse_dxf(source, name, version=None):
    doc = ezdxf.readfile(source)
    audit = doc.audit()
    if audit.has_errors:
        raise ValueError('DXF 数据审计失败，请先在 CAD 软件中修复图纸。')
    layouts = []
    for layout in doc.layouts:
        if len(layout) == 0:
            continue
        entities, annotations, counts, unknown = [], [], Counter(), Counter()
        curves, spatial, vertex_count = [], 0, 0
        for index, (entity, layer) in enumerate(flatten(layout)):
            if index >= MAX_ENTITIES:
                raise ValueError('图元数量超过 30000，请拆分图纸后再上传。')
            kind = entity.dxftype()
            counts[kind] += 1
            layer_def = doc.layers.get(layer) if layer in doc.layers else None
            if entity.dxf.get('invisible', 0) or (layer_def and (layer_def.is_off() or layer_def.is_frozen())):
                continue
            if kind in ('TEXT', 'MTEXT', 'ATTRIB', 'ATTDEF'):
                text = entity.plain_text() if hasattr(entity, 'plain_text') else entity.dxf.get('text', '')
                annotations.append({'type': kind, 'text': text, 'position': point(entity.dxf.insert)})
                continue
            if kind == 'DIMENSION':
                try:
                    # Aligned dimensions measure endpoint distance, independent of a DXF angle tag.
                    # LibreDWG can emit angle=0 for DIM_ALIGNED; ezdxf otherwise projects onto X.
                    measured = (entity.dxf.defpoint3-entity.dxf.defpoint2).magnitude if entity.dxf.dimtype & 7 == 1 else entity.get_measurement()
                    value = float(measured) if isinstance(measured, (float, int)) else None
                except (ValueError, TypeError, AttributeError):
                    value = None
                annotations.append({'type': kind, 'text': entity.dxf.get('text', '') or '<>',
                                    'measurement': value, 'dimensionType': entity.dxf.dimtype & 7,
                                    'sourceHandle': entity.dxf.handle,
                                    'definitionPoints': {key: point(entity.dxf.get(key)) for key in ('defpoint', 'defpoint2', 'defpoint3', 'defpoint4') if entity.dxf.hasattr(key)},
                                    'angle': entity.dxf.get('angle', 0),
                                    'position': point(entity.dxf.get('text_midpoint', (0, 0, 0)))})
                continue
            if kind not in ('LINE', 'ARC', 'CIRCLE', 'LWPOLYLINE', 'POLYLINE', 'ELLIPSE', 'SPLINE'):
                unknown[kind] += 1
                continue
            try:
                # Flattening is for preview/topology only; circles stay analytic in the model.
                if kind == 'CIRCLE':
                    radius = float(entity.dxf.radius)
                    if radius <= 0:
                        raise ValueError('圆半径无效')
                    count = max(32, min(10000, math.ceil(math.pi / math.acos(max(-1, 1-min(0.01/radius, 1))))))
                    vertices = list(entity.vertices([i*360/count for i in range(count)]))
                    vertices.append(vertices[0])
                else:
                    vertices = list(dxfpath.make_path(entity).flattening(0.01))
            except (TypeError, ValueError, ZeroDivisionError):
                unknown[kind] += 1
                continue
            if len(vertices) < 2:
                continue
            vertex_count += len(vertices)
            if vertex_count > 120000:
                raise ValueError('曲线离散顶点超过 120000，请拆分图纸。')
            is_planar = all(abs(v.z) < 1e-6 for v in vertices)
            if not is_planar:
                spatial += 1
            points = [point(v) for v in vertices]
            if not all(math.isfinite(n) and abs(n) < 1e8 for p in points for n in p):
                raise ValueError('图纸坐标无效或超出支持范围。')
            linetype = entity.dxf.get('linetype', 'BYLAYER')
            if linetype.upper() == 'BYLAYER' and layer_def:
                linetype = layer_def.dxf.linetype
            construction = any(word in (linetype + ' ' + layer).upper()
                               for word in ('CENTER', 'CENTRE', 'HIDDEN', 'DASH', 'ISO02', 'ISO04', '中心', '虚线'))
            record = {'id': f'e{index}', 'type': kind, 'layer': layer, 'points': points,
                      'sourceHandle': entity.dxf.handle,
                      'construction': construction, 'planar': is_planar}
            if kind == 'CIRCLE':
                record.update(center=point(entity.dxf.center), radius=float(entity.dxf.radius))
            entities.append(record)
            if is_planar and not construction:
                curves.append(LineString(points))
        # Closed bounded regions, never an arbitrary bounding-box extrusion.
        polygons = list(polygonize(unary_union(curves))) if curves else []
        profiles = []
        for poly in sorted(polygons, key=lambda p: p.area, reverse=True):
            if poly.area < 1e-8 or not poly.is_valid:
                continue
            outer = list(poly.exterior.coords)
            holes = [list(r.coords) for r in poly.interiors]
            circles = [e for e in entities if e['type'] == 'CIRCLE' and e['planar'] and not e['construction']]

            def ring_data(coords):
                for circle in circles:
                    cx, cy = circle['center']
                    if len(coords) > 8 and all(abs(math.hypot(x-cx, y-cy)-circle['radius']) < 1e-5 for x, y in coords):
                        return {'type': 'circle', 'center': [cx, cy], 'radius': circle['radius']}
                return {'type': 'polygon', 'points': coords}

            profiles.append({'id': f'p{len(profiles)}', 'area': poly.area,
                             'bounds': list(poly.bounds), 'outer': ring_data(outer),
                             'holes': [ring_data(h) for h in holes],
                             'preview': {'outer': outer, 'holes': holes}})
            if len(profiles) >= 500:
                raise ValueError('闭合区域达到 500 个，请拆分图纸后再试。')
        coords = [p for e in entities for p in e['points']]
        bounds = [min(p[0] for p in coords), min(p[1] for p in coords),
                  max(p[0] for p in coords), max(p[1] for p in coords)] if coords else [0, 0, 100, 100]
        layouts.append({'name': layout.name, 'entities': entities, 'annotations': annotations,
                        'entityCounts': dict(counts), 'unsupported': dict(unknown),
                        'nonPlanarCount': spatial, 'bounds': bounds, 'profiles': profiles})
    warnings = ['闭合区域只是候选轮廓，可能包含图框或不同视图；生成前需确认区域、单位及建模参数。',
                '圆保持精确圆形；圆弧、样条及其他曲线目前按 0.01 图纸单位离散，生成结果需复核。',
                '自动识别仅覆盖部分同轴台阶结构；其他视图关系需在通用特征组合中指定，螺纹与边处理需另外确认。']
    if not any(a['type'] == 'DIMENSION' for layout in layouts for a in layout['annotations']):
        warnings.insert(0, '图纸没有可读取的尺寸标注。不能据此自动确定原零件的厚度、深度或结构；轴测投影不能直接当作真实截面。')
    if audit.has_fixes:
        warnings.append(f'DXF 审计修复了 {len(audit.fixes)} 项问题。')
    from backend.multiview import recognize_parts
    parts = recognize_parts(layouts)
    return {'name': name, 'dwgVersion': version, 'dxfVersion': doc.dxfversion,
            'partCandidates': parts,
            'insunits': int(doc.header.get('$INSUNITS', 0)), 'layouts': layouts, 'warnings': warnings}
