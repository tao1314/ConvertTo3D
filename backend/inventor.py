"""Convert IPT geometry using the project's portable open-source runtime."""

from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile

from backend.drawing import ROOT

OLE_HEADER = bytes.fromhex('D0CF11E0A1B11AE1')
PYTHON = ROOT / 'tools' / 'freecad' / 'bin' / 'python.exe'
PARAMETRIC_UNAVAILABLE = (
    '原始参数化 SLDPRT 转换尚未实现：当前引擎只能读取 IPT 实体几何，'
    '尚无完整草图、尺寸约束、特征依赖迁移及原生 SLDPRT 写入能力。'
    '请选择 STEP；STEP 不包含原始草图和特征历史。'
)


# Retain the existing health field while detecting the independent IPT engine.
def inventor_available():
    paths = [PYTHON, PYTHON.parent / 'FreeCAD.pyd',
             ROOT / 'tools' / 'InventorLoader-master' / 'Import_IPT.py']
    paths.extend(ROOT / 'tools' / 'ipt-python' / package / '__init__.py'
                 for package in ('olefile', 'xlrd', 'xlutils', 'xlwt'))
    return all(path.is_file() for path in paths)


# Reject unrelated containers before starting the full geometry parser.
def validate_ipt(source):
    with Path(source).open('rb') as stream:
        if stream.read(len(OLE_HEADER)) != OLE_HEADER:
            raise ValueError('IPT 文件头无效；请选择 Inventor 零件文件。')


# Isolate each upload so upstream diagnostic dumps never touch the original file.
def convert_ipt(source, target):
    validate_ipt(source)
    if not inventor_available():
        raise ValueError('IPT 开源转换环境未就绪，请运行 scripts/setup-ipt.ps1；无需安装 Inventor。')
    target = Path(target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ipt-', dir=target.parent) as directory:
        work = Path(directory)
        isolated_source, translated = work / 'source.ipt', work / 'model.step'
        shutil.copyfile(source, isolated_source)
        environment = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'PYTHONIOENCODING': 'utf-8'}
        try:
            result = subprocess.run(
                [str(PYTHON), str(ROOT / 'scripts' / 'convert-ipt-open.py'),
                 str(isolated_source), str(translated)],
                cwd=work, env=environment, capture_output=True, timeout=240,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except subprocess.TimeoutExpired as error:
            raise ValueError('IPT 转换超过 240 秒，已停止；请检查文件大小或几何复杂度。') from error
        diagnostic = (result.stdout + result.stderr).decode('utf-8', errors='replace')[-4000:]
        if result.returncode or not translated.is_file() or not translated.with_suffix('.json').is_file():
            raise ValueError('IPT 开源转换失败，未提供不完整模型。' + diagnostic)
        report = json.loads(translated.with_suffix('.json').read_text(encoding='utf-8'))
        shutil.copyfile(translated, target)
        return json.dumps(report, ensure_ascii=False)
