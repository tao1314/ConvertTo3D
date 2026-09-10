"""Convert native Autodesk Inventor parts through a locally installed Inventor instance."""

from pathlib import Path
import subprocess
import winreg

from backend.drawing import ROOT

OLE_HEADER = bytes.fromhex('D0CF11E0A1B11AE1')


# Report whether the registered Inventor automation server is available.
def inventor_available():
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r'Inventor.Application\CLSID'):
            return True
    except OSError:
        return False


# Validate the container before passing the uploaded file to Inventor.
def validate_ipt(source):
    with Path(source).open('rb') as stream:
        if stream.read(len(OLE_HEADER)) != OLE_HEADER:
            raise ValueError('IPT 文件头无效；请选择 Inventor 零件文件。')


# Use Inventor's own translator so native geometry is retained in the STEP result.
def convert_ipt(source, target):
    validate_ipt(source)
    if not inventor_available():
        raise ValueError('本机未检测到 Autodesk Inventor，无法读取 IPT 实体。请安装并激活 Inventor 后重启服务。')
    script = ROOT / 'scripts' / 'convert-inventor.ps1'
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script),
         '-InputPath', str(Path(source).resolve()), '-OutputPath', str(Path(target).resolve())],
        capture_output=True, timeout=180,
    )
    diagnostic = (result.stdout + result.stderr).decode('utf-8', errors='replace')[-3000:]
    if result.returncode or not Path(target).is_file():
        raise ValueError('Inventor 转换 IPT 失败。' + diagnostic)
    return diagnostic
