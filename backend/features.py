"""Drawing-independent, explicitly positioned feature composition."""
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Cut
from OCP.gp import gp_Trsf
from backend.modeling import profile_shape, solid_stats, export_solid


def build_features(drawing, params, directory):
    shape = None
    trace = []
    for index, feature in enumerate(params['features']):
        layout = next((l for l in drawing['layouts'] if l['name'] == feature['layout']), None)
        profile = next((p for p in layout['profiles'] if p['id'] == feature['profileId']), None) if layout else None
        if profile is None:
            raise ValueError(f'特征 {index+1} 的布局或轮廓不存在。')
        if shape is None and feature['combine'] != 'add':
            raise ValueError('首个特征必须加料。')
        scale = params['mmPerUnit']
        tool = profile_shape(profile, {**feature, 'mmPerUnit': scale})
        u, v = feature['originU']*scale, feature['originV']*scale
        x, y, z = feature['positionX'], feature['positionY'], feature['positionZ']
        matrices = {
            'XY': (1,0,0,x-u, 0,1,0,y-v, 0,0,1,z),
            'XZ': (1,0,0,x-u, 0,0,-1,y, 0,1,0,z-v),
            'YZ': (0,0,1,x, 1,0,0,y-u, 0,1,0,z-v),
        }
        transform = gp_Trsf()
        transform.SetValues(*matrices[feature['plane']])
        tool = BRepBuilderAPI_Transform(tool, transform, True).Shape()
        before = solid_stats(shape)['volumeMm3'] if shape is not None else 0
        if shape is None:
            shape = tool
        else:
            operation = (BRepAlgoAPI_Fuse if feature['combine'] == 'add' else BRepAlgoAPI_Cut)(shape, tool)
            if not operation.IsDone():
                raise ValueError(f'特征 {index+1} 布尔运算失败。')
            operation.SimplifyResult(True, True)
            shape = operation.Shape()
        stats = solid_stats(shape)
        if not stats['valid'] or stats['volumeMm3'] < 1e-9:
            raise ValueError(f'特征 {index+1} 产生无效或空实体。')
        if feature['combine'] == 'cut' and before-stats['volumeMm3'] < 1e-8:
            raise ValueError(f'特征 {index+1} 未切到实体，请检查视图原点、平面及位置。')
        trace.append({'index': index+1, 'parameters': feature, 'profile': profile, 'volumeMm3': stats['volumeMm3']})
    if shape is None:
        raise ValueError('请添加特征。')
    return {**export_solid(shape, directory), 'featureCount': len(trace), 'features': trace}
