"""Generate validated B-rep solids, not a renamed mesh."""
import math
from pathlib import Path

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism, BRepPrimAPI_MakeRevol, BRepPrimAPI_MakeCylinder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Cut
from OCP.TopoDS import TopoDS
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Ax1, gp_Ax2, gp_Circ
from OCP.STEPControl import STEPControl_Writer, STEPControl_Reader, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.StlAPI import StlAPI_Writer
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID
from shapely.geometry import Polygon


def ring_wire(ring, scale):
    if ring['type'] == 'circle':
        x, y = ring['center']
        circle = gp_Circ(gp_Ax2(gp_Pnt(x*scale, y*scale, 0), gp_Dir(0, 0, 1)), ring['radius']*scale)
        return BRepBuilderAPI_MakeWire(BRepBuilderAPI_MakeEdge(circle).Edge()).Wire()
    builder = BRepBuilderAPI_MakePolygon()
    for x, y in ring['points'][:-1]:
        builder.Add(gp_Pnt(x*scale, y*scale, 0))
    builder.Close()
    if not builder.IsDone():
        raise ValueError('无法建立闭合轮廓。')
    return builder.Wire()


def solid_stats(shape):
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    solids = 0
    while explorer.More():
        solids += 1
        explorer.Next()
    return {'valid': BRepCheck_Analyzer(shape).IsValid(), 'solids': solids, 'volumeMm3': abs(props.Mass())}


def build_model(profile, params, directory):
    return export_solid(profile_shape(profile, params), directory)


def profile_shape(profile, params):
    scale = params['mmPerUnit']
    # Normalize ring orientation independently of polygonize traversal direction.
    from shapely.geometry.polygon import orient
    poly = orient(Polygon(profile['preview']['outer'], profile['preview']['holes']), sign=1.0)
    outer = profile['outer'].copy()
    if outer['type'] == 'polygon':
        outer['points'] = list(poly.exterior.coords)
    maker = BRepBuilderAPI_MakeFace(ring_wire(outer, scale), True)
    for index, hole in enumerate(profile['holes']):
        hole = hole.copy()
        if hole['type'] == 'polygon':
            hole['points'] = list(poly.interiors[index].coords)
        wire = ring_wire(hole, scale)
        if hole['type'] == 'circle':
            wire.Reverse()
        maker.Add(wire)
    if not maker.IsDone():
        raise ValueError('轮廓无法形成有效平面。')
    face = maker.Face()
    if not BRepCheck_Analyzer(face).IsValid():
        raise ValueError('轮廓或孔洞无效，请重新选择闭合区域。')
    if params['operation'] == 'extrude':
        shape = BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, params['depthMm'])).Shape()
    else:
        axis = params['axis']
        offset = params['axisOffset']
        bounds = profile['bounds']
        low, high = (bounds[1], bounds[3]) if axis == 'x' else (bounds[0], bounds[2])
        if low + 1e-6 < offset < high - 1e-6:
            raise ValueError('旋转轴穿过轮廓内部，可能生成自交实体；请选择轴一侧的剖面。')
        origin = gp_Pnt(0, offset*scale, 0) if axis == 'x' else gp_Pnt(offset*scale, 0, 0)
        direction = gp_Dir(1, 0, 0) if axis == 'x' else gp_Dir(0, 1, 0)
        shape = BRepPrimAPI_MakeRevol(face, gp_Ax1(origin, direction), math.radians(params['angleDeg']), True).Shape()
    return shape


def export_solid(shape, directory):
    stats = solid_stats(shape)
    if not stats['valid'] or stats['solids'] != 1 or stats['volumeMm3'] < 1e-9:
        raise ValueError('建模结果未通过单实体有效性检查，请检查轮廓和参数。')
    # Boolean operations can return a compound containing one solid. Export the solid itself.
    shape = TopoDS.Solid_s(TopExp_Explorer(shape, TopAbs_SOLID).Current())
    directory = Path(directory)
    step_path = directory / 'model.step'
    writer = STEPControl_Writer()
    if writer.Transfer(shape, STEPControl_AsIs) != IFSelect_RetDone or writer.Write(str(step_path)) != IFSelect_RetDone:
        raise ValueError('STEP 文件写入失败。')
    # Validate the actual exported file by importing it through the CAD kernel.
    reader = STEPControl_Reader()
    if reader.ReadFile(str(step_path)) != IFSelect_RetDone or not reader.TransferRoots():
        raise ValueError('STEP 回读失败。')
    exported = solid_stats(reader.OneShape())
    if not exported['valid'] or exported['solids'] != 1 or not math.isclose(exported['volumeMm3'], stats['volumeMm3'], rel_tol=1e-6, abs_tol=1e-6):
        raise ValueError('STEP 回读实体或体积校验失败。')
    BRepMesh_IncrementalMesh(shape, 0.05, False, 0.3, True).Perform()
    stl = StlAPI_Writer()
    if not stl.Write(shape, str(directory / 'preview.stl')):
        raise ValueError('预览网格生成失败。')
    return {**stats, 'stepRoundTripVerified': True}


def build_multiview(part, params, directory):
    scale = params['mmPerUnit']
    if not math.isfinite(scale) or not 0 < scale <= 1000:
        raise ValueError('单位比例无效。')

    def cylinder(radius, start, end, x=0, y=0):
        return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x*scale, y*scale, start*scale), gp_Dir(0,0,1)),
                                       radius*scale, (end-start)*scale).Shape()

    def boolean(kind, first, second):
        operation = kind(first, second)
        if not operation.IsDone():
            raise ValueError('特征布尔运算失败。')
        operation.SimplifyResult(True, True)
        result = operation.Shape()
        if not BRepCheck_Analyzer(result).IsValid():
            raise ValueError('特征运算产生了无效几何。')
        return result

    shape, features = None, []
    for stage in part['outerStages']:
        feature = cylinder(stage['radius'], stage['start'], stage['end'])
        shape = feature if shape is None else boolean(BRepAlgoAPI_Fuse, shape, feature)
        features.append({'type': 'outer-cylinder', 'diameterMm': 2*stage['radius']*scale,
                         'startMm': stage['start']*scale, 'lengthMm': (stage['end']-stage['start'])*scale})
    for stage in part['innerStages']:
        shape = boolean(BRepAlgoAPI_Cut, shape, cylinder(stage['radius'], stage['start'], stage['end']))
        features.append({'type': 'stepped-bore', 'diameterMm': 2*stage['radius']*scale,
                         'startMm': stage['start']*scale, 'lengthMm': (stage['end']-stage['start'])*scale})
    for hole in part['holes']:
        if hole['thread'] and params['threadMode'] == 'omit':
            continue
        before = solid_stats(shape)['volumeMm3']
        # Cut across the full axial envelope; boolean intersection limits flange holes to flange thickness.
        shape = boolean(BRepAlgoAPI_Cut, shape, cylinder(hole['diameter']/2, -1, part['totalLength']+1, hole['x'], hole['y']))
        if before-solid_stats(shape)['volumeMm3'] < 1e-8:
            raise ValueError('孔未穿过实体，视图匹配可能不正确。')
        features.append({'type': 'simplified-thread-through-hole' if hole['thread'] else 'through-hole',
                         'diameterMm': hole['diameter']*scale, 'centerMm': [hole['x']*scale, hole['y']*scale],
                         'designation': hole['thread'], 'sourceHandle': hole['sourceHandle']})
    stats = export_solid(shape, directory)
    return {**stats, 'featureCount': len(features), 'features': features,
            'threadMode': params['threadMode'], 'edgeTreatment': 'omitted'}
