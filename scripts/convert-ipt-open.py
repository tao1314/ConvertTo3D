"""Translate embedded IPT geometry in an isolated portable FreeCAD process."""

import json
import math
import os
from pathlib import Path
import sys
import traceback
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'InventorLoader-master'))
sys.path.insert(0, str(ROOT / 'tools' / 'ipt-python'))


# Choose embedded geometry translation without displaying the strategy dialog.
def choose_step():
    import importerUtils
    importerUtils.setStrategy(importerUtils.STRATEGY_STEP)


# Refuse exporters that silently omit unsupported faces or boundary edges.
def require_translation(converter):
    # Preserve the upstream result only when geometry was produced.
    def checked(*args):
        result = converter(*args)
        if not result:
            raise ValueError('IPT 含当前解析器不支持的面或边，已停止导出，避免丢失几何。')
        return result
    return checked


# Keep every source body in one STEP file without reconstructing features.
def convert(source, target):
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PySide2.QtWidgets import QApplication
    application = QApplication.instance() or QApplication([])
    import FreeCAD
    import Part

    # The worker never enters feature reconstruction or GUI document insertion.
    native = types.ModuleType('importerFreeCAD')
    native.FreeCADImporter = None
    sys.modules['importerFreeCAD'] = native
    sys.modules['ImportGui'] = types.ModuleType('ImportGui')
    import importerUtils
    errors = []

    # Capture upstream errors even when the parser catches the original exception.
    def parser_error(message, *args):
        errors.append(message % args if args else str(message))

    importerUtils.logError = parser_error
    import Import_IPT
    import importerSAT
    import Acis2Step

    read_segment = Import_IPT.ReadRSeMetaDataB

    # Feature-tree and browser records are not needed to translate stored geometry.
    def read_geometry_segment(data, segment):
        if segment.isBRep():
            read_segment(data, segment)

    Import_IPT.ReadRSeMetaDataB = read_geometry_segment

    Acis2Step._convertFace = require_translation(Acis2Step._convertFace)
    Acis2Step._createCoEdge = require_translation(Acis2Step._createCoEdge)
    Import_IPT.chooseImportStrategy = choose_step
    ole = importerUtils.setInventorFile(str(source))
    try:
        Import_IPT.read(ole)
    finally:
        ole.close()
    if errors:
        raise ValueError('IPT 解析未完成：' + '\n'.join(errors)[-2000:])
    brep = Import_IPT.getModel().getBRep()
    if len(brep.AcisList) != 1:
        raise ValueError('当前支持一个明确的 IPT 实体数据集；未找到或存在多个候选数据集。')
    acis = brep.AcisList[0].SAT
    bodies = importerSAT.resolveNodes(acis)
    lumps = [lump for body in bodies for lump in body.getLumps()]
    if not lumps or any(body.getWires() for body in bodies):
        raise ValueError('IPT 不包含可完整转换的三维实体，或包含额外线框。')
    # Multiple shells per lump need cavity-aware construction; never guess here.
    if any(len(lump.getShells()) != 1 for lump in lumps):
        raise ValueError('当前开源转换器暂不支持含多个边界壳的实体。')
    source_faces = sum(len(shell.getFaces()) for lump in lumps for shell in lump.getShells())
    step = Acis2Step.export(acis.name, acis.header, bodies)
    if errors:
        raise ValueError('IPT 几何导出未完成：' + '\n'.join(errors)[-2000:])
    shape = Part.read(step)
    shells = shape.Shells
    if (len(shells) != len(lumps) or len(shape.Faces) != source_faces
            or sum(len(shell.Faces) for shell in shells) != source_faces):
        raise ValueError('STEP 回读面数或实体边界数量与 IPT 不一致，已拒绝不完整结果。')
    solids = []
    for shell in shells:
        if not shell.isClosed() or not shell.isValid():
            raise ValueError('IPT 导出的实体边界未闭合或无效。')
        solid = Part.makeSolid(shell)
        if not solid.isValid() or not math.isfinite(solid.Volume) or solid.Volume <= 1e-9:
            raise ValueError('IPT 导出的实体有效性或体积检查失败。')
        solids.append(solid)
    model = solids[0] if len(solids) == 1 else Part.makeCompound(solids)
    model.exportStep(str(target))
    roundtrip = Part.read(str(target))
    if (not roundtrip.isValid() or len(roundtrip.Solids) != len(solids)
            or len(roundtrip.Faces) != source_faces
            or not math.isclose(roundtrip.Volume, model.Volume, rel_tol=1e-6, abs_tol=1e-6)):
        raise ValueError('最终 STEP 回读完整性检查失败。')
    return {'engine': 'InventorLoader + FreeCAD', 'sourceBodies': len(bodies),
            'sourceFaces': source_faces, 'outputFaces': len(roundtrip.Faces),
            'solids': len(solids), 'volumeMm3': roundtrip.Volume,
            'faceCountVerified': True, 'stepRoundTripVerified': True}


# Report failures through a nonzero process exit and a readable log.
def main():
    source, target = (Path(value).resolve() for value in sys.argv[1:3])
    report = convert(source, target)
    target.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
