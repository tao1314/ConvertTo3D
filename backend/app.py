import json
import logging
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.drawing import ROOT, converter_path, convert_dwg, parse_dxf
from backend.inventor import convert_ipt, inventor_available

app = FastAPI(title='ConvertTo3D local CAD service')
DATA = ROOT / 'runtime' / 'jobs'
DATA.mkdir(parents=True, exist_ok=True)


class GenerateRequest(BaseModel):
    layout: str
    profileId: str
    operation: Literal['extrude', 'revolve'] = 'extrude'
    mmPerUnit: float = Field(gt=0, le=1000, allow_inf_nan=False)
    depthMm: float = Field(default=10, gt=0, le=10000, allow_inf_nan=False)
    axis: Literal['x', 'y'] = 'y'
    axisOffset: float = Field(default=0, ge=-1e8, le=1e8, allow_inf_nan=False)
    angleDeg: float = Field(default=360, gt=0, le=360, allow_inf_nan=False)
    confirmed: Literal[True]


class PartGenerateRequest(BaseModel):
    partId: str
    mmPerUnit: float = Field(gt=0, le=1000, allow_inf_nan=False)
    threadMode: Literal['omit', 'nominal-through'] = 'omit'
    edgeTreatment: Literal['omit'] = 'omit'
    confirmed: Literal[True]


class Feature(GenerateRequest):
    mmPerUnit: float = Field(default=1, gt=0, le=1000, allow_inf_nan=False)
    confirmed: Literal[True] = True
    combine: Literal['add', 'cut'] = 'add'
    plane: Literal['XY', 'XZ', 'YZ'] = 'XY'
    originU: float = Field(default=0, ge=-1e8, le=1e8, allow_inf_nan=False)
    originV: float = Field(default=0, ge=-1e8, le=1e8, allow_inf_nan=False)
    positionX: float = Field(default=0, ge=-1e6, le=1e6, allow_inf_nan=False)
    positionY: float = Field(default=0, ge=-1e6, le=1e6, allow_inf_nan=False)
    positionZ: float = Field(default=0, ge=-1e6, le=1e6, allow_inf_nan=False)


class FeaturesRequest(BaseModel):
    mmPerUnit: float = Field(gt=0, le=1000, allow_inf_nan=False)
    features: list[Feature] = Field(min_length=1, max_length=32)
    confirmed: Literal[True]


@app.post('/api/drawings/{job_id}/generate-features')
def generate_features(job_id: str, request: FeaturesRequest):
    directory = job_dir(job_id)
    drawing = json.loads((directory/'drawing.json').read_text(encoding='utf-8'))
    output = directory/uuid4().hex
    output.mkdir()
    try:
        from backend.features import build_features
        stats = build_features(drawing, request.model_dump(), output)
    except Exception as error:
        logging.exception('Feature composition failed')
        raise HTTPException(422, str(error) if isinstance(error, ValueError) else '特征组合失败，请查看服务日志。') from error
    recipe = {'source': drawing['name'], 'mode': 'feature-sequence-single-part',
              'parameters': request.model_dump(), 'verification': stats,
              'output': 'one STEP solid; no native feature history'}
    (output/'recipe.json').write_text(json.dumps(recipe, ensure_ascii=False, indent=2), encoding='utf-8')
    base = f'/api/drawings/{job_id}/outputs/{output.name}'
    return {'generationId': output.name, 'stats': stats, 'mode': recipe['mode'],
            'stepUrl': f'{base}/model.step', 'previewUrl': f'{base}/preview.stl', 'recipeUrl': f'{base}/recipe.json'}


def job_dir(job_id):
    if len(job_id) != 32 or any(c not in '0123456789abcdef' for c in job_id):
        raise HTTPException(404, '任务不存在。')
    directory = DATA / job_id
    if not (directory / 'drawing.json').is_file():
        raise HTTPException(404, '任务不存在。')
    return directory


@app.get('/api/health')
def health():
    try:
        from backend.modeling import build_model  # noqa: F401
        kernel = True
    except ImportError:
        kernel = False
    return {'dwgParser': converter_path() is not None, 'inventorImporter': inventor_available(), 'cadKernel': kernel,
            'nativeSolidWorks': False, 'outputFormats': ['step'] if kernel else [], 'mode': 'local'}


@app.post('/api/drawings')
def upload_drawing(file: UploadFile = File(...)):
    name = Path((file.filename or '').replace('\\', '/')).name
    suffix = Path(name).suffix.lower()
    if suffix == '.idw':
        raise HTTPException(415, '这是 Inventor 原生 IDW 工程图；当前请先在 Inventor 中导出为二维 DWG 或 DXF 后上传。')
    if suffix == '.iam':
        raise HTTPException(415, 'IAM 是 Inventor 装配体；当前接收单个 IPT 零件。')
    if suffix not in ('.ipt', '.dwg', '.dxf'):
        raise HTTPException(415, '请上传 Inventor IPT 零件或 DWG / DXF 图纸。')
    directory = DATA / uuid4().hex
    directory.mkdir()
    source = directory / ('source' + suffix)
    size = 0
    try:
        with source.open('wb') as output:
            while chunk := file.file.read(1024*1024):
                size += len(chunk)
                if size > 100*1024*1024:
                    raise HTTPException(413, '文件不能超过 100 MB。')
                output.write(chunk)
        if size == 0:
            raise ValueError('上传文件为空。')
        if suffix == '.ipt':
            from backend.modeling import import_step
            generation_id = uuid4().hex
            output = directory / generation_id
            output.mkdir()
            diagnostic = convert_ipt(source, output / 'inventor.step')
            stats = import_step(output / 'inventor.step', output)
            recipe = {'source': name, 'jobId': directory.name, 'mode': 'inventor-native-part',
                      'verification': stats, 'output': 'one STEP B-rep solid; native IPT feature history is not included'}
            (output / 'recipe.json').write_text(json.dumps(recipe, ensure_ascii=False, indent=2), encoding='utf-8')
            metadata = {'id': directory.name, 'name': name, 'sizeBytes': size,
                        'sourceType': 'inventor-part', 'layouts': [], 'partCandidates': [],
                        'warnings': ['直接转换 IPT 中的完整零件实体，不执行二维截面识别。']}
            (directory / 'drawing.json').write_text(json.dumps(metadata, ensure_ascii=False), encoding='utf-8')
            (directory / 'converter.log').write_text(diagnostic, encoding='utf-8')
            base = f'/api/drawings/{directory.name}/outputs/{generation_id}'
            metadata['result'] = {'generationId': generation_id, 'stats': stats,
                                  'mode': 'inventor-native-part', 'stepUrl': f'{base}/model.step',
                                  'previewUrl': f'{base}/preview.stl', 'recipeUrl': f'{base}/recipe.json'}
            return metadata
        version = None
        diagnostic = ''
        dxf = source
        if suffix == '.dwg':
            with source.open('rb') as stream:
                version = stream.read(6).decode('ascii', errors='replace')
            if not version.startswith('AC10'):
                raise ValueError('文件头不是受支持的 DWG 格式。')
            dxf = directory / 'converted.dxf'
            diagnostic = convert_dwg(source, dxf)
        drawing = parse_dxf(dxf, name, version)
        drawing.update(id=directory.name, sizeBytes=size)
        (directory / 'converter.log').write_text(diagnostic, encoding='utf-8')
        (directory / 'drawing.json').write_text(json.dumps(drawing, ensure_ascii=False), encoding='utf-8')
        return drawing
    except HTTPException:
        raise
    except (ValueError, OSError) as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        logging.exception('Drawing parsing failed')
        raise HTTPException(422, '图纸解析失败，请检查文件或查看服务日志。') from error
    finally:
        file.file.close()


@app.post('/api/drawings/{job_id}/generate')
def generate(job_id: str, request: GenerateRequest):
    directory = job_dir(job_id)
    drawing = json.loads((directory / 'drawing.json').read_text(encoding='utf-8'))
    layout = next((x for x in drawing['layouts'] if x['name'] == request.layout), None)
    profile = next((p for p in layout['profiles'] if p['id'] == request.profileId), None) if layout else None
    if profile is None:
        raise HTTPException(422, '请选择有效的布局和闭合轮廓。')
    params = request.model_dump()
    generation_id = uuid4().hex
    output = directory / generation_id
    output.mkdir()
    try:
        from backend.modeling import build_model
        stats = build_model(profile, params, output)
    except Exception as error:
        logging.exception('Solid generation failed')
        raise HTTPException(422, str(error) if isinstance(error, ValueError) else '三维生成失败，请查看服务日志。') from error
    recipe = {'source': drawing['name'], 'jobId': job_id, 'parameters': params,
              'profile': profile, 'verification': stats,
              'limitations': drawing['warnings'], 'output': 'STEP B-rep, not native feature history'}
    (output / 'recipe.json').write_text(json.dumps(recipe, ensure_ascii=False, indent=2), encoding='utf-8')
    base = f'/api/drawings/{job_id}/outputs/{generation_id}'
    return {'generationId': generation_id, 'stats': stats,
            'stepUrl': f'{base}/model.step', 'previewUrl': f'{base}/preview.stl',
            'recipeUrl': f'{base}/recipe.json'}


@app.get('/api/drawings/{job_id}/outputs/{generation_id}/{filename}')
def download(job_id: str, generation_id: str, filename: str):
    directory = job_dir(job_id)
    if len(generation_id) != 32 or any(c not in '0123456789abcdef' for c in generation_id):
        raise HTTPException(404)
    if filename not in ('model.step', 'preview.stl', 'recipe.json'):
        raise HTTPException(404)
    target = directory / generation_id / filename
    if not target.is_file():
        raise HTTPException(404, '文件不存在。')
    return FileResponse(target, filename=filename)


@app.post('/api/drawings/{job_id}/generate-part')
def generate_part(job_id: str, request: PartGenerateRequest):
    directory = job_dir(job_id)
    drawing = json.loads((directory/'drawing.json').read_text(encoding='utf-8'))
    part = next((p for p in drawing.get('partCandidates', []) if p['id'] == request.partId), None)
    if part is None:
        raise HTTPException(422, '没有可用的多视图零件方案，请重新解析图纸。')
    output = directory/uuid4().hex
    output.mkdir()
    try:
        from backend.modeling import build_multiview
        stats = build_multiview(part, request.model_dump(), output)
    except Exception as error:
        logging.exception('Multi-view reconstruction failed')
        raise HTTPException(422, str(error) if isinstance(error, ValueError) else '整体建模失败，请查看服务日志。') from error
    recipe = {'source': drawing['name'], 'jobId': job_id, 'mode': 'multiview-single-part',
              'parameters': request.model_dump(), 'part': part, 'verification': stats,
              'output': 'one STEP B-rep solid; no native CAD feature history'}
    (output/'recipe.json').write_text(json.dumps(recipe, ensure_ascii=False, indent=2), encoding='utf-8')
    base = f'/api/drawings/{job_id}/outputs/{output.name}'
    return {'generationId': output.name, 'stats': stats, 'mode': 'multiview-single-part',
            'stepUrl': f'{base}/model.step', 'previewUrl': f'{base}/preview.stl', 'recipeUrl': f'{base}/recipe.json'}
