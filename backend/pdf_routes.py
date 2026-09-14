"""Expose engineering PDF generation for existing validated STEP results."""

import json
import logging
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field


# Bound drawing settings and leave design intent fields explicitly user-supplied.
class PdfSettings(BaseModel):
    title: str = Field(default='零件工程图', min_length=1, max_length=24)
    drawingNumber: str = Field(default='', max_length=32)
    organization: str = Field(default='', max_length=32)
    material: str = Field(default='', max_length=24)
    notes: str = Field(default='', max_length=800)
    paper: Literal['A3', 'A4'] = 'A3'
    axis: Literal['auto', 'x', 'y', 'z'] = 'auto'
    rotation: float = Field(default=0, ge=-180, le=180, allow_inf_nan=False)
    sectionPercent: float = Field(default=50, gt=0, lt=100, allow_inf_nan=False)
    sectionOffset: float = Field(default=0, ge=-100000, le=100000, allow_inf_nan=False)
    scale: float = Field(default=0, ge=0, le=10, allow_inf_nan=False)
    hiddenLines: bool = True
    dimensions: bool = True
    centerlines: bool = True


# Reuse the app's job resolver without importing its mutable runtime directory.
def create_pdf_router(resolve_job):
    router = APIRouter()

    # Restrict artifact identifiers to server-created hexadecimal names.
    def artifact_directory(job_id, generation_id):
        if len(generation_id) != 32 or any(c not in '0123456789abcdef' for c in generation_id):
            raise HTTPException(404, '模型不存在。')
        directory = resolve_job(job_id) / generation_id
        if not (directory / 'model.step').is_file():
            raise HTTPException(404, '请先生成 STEP 模型。')
        return directory

    # Store each PDF revision separately so failure never replaces a good drawing.
    @router.post('/api/drawings/{job_id}/outputs/{generation_id}/engineering-pdf')
    def generate(job_id: str, generation_id: str, settings: PdfSettings):
        directory = artifact_directory(job_id, generation_id)
        revision = uuid4().hex
        target = directory / f'drawing-{revision}.pdf'
        try:
            from backend.engineering_pdf import generate_pdf
            from pypdf import PdfReader
            report = generate_pdf(directory / 'model.step', target, settings.model_dump())
            if len(PdfReader(target).pages) != 1:
                raise ValueError('PDF 回读校验失败。')
            target.with_suffix('.json').write_text(
                json.dumps({'settings': settings.model_dump(), 'verification': report}, ensure_ascii=False, indent=2),
                encoding='utf-8',
            )
        except Exception as error:
            target.unlink(missing_ok=True)
            logging.exception('Engineering PDF generation failed')
            raise HTTPException(422, str(error) if isinstance(error, ValueError) else '工程图生成失败，请检查模型或服务日志。') from error
        return {'pdfUrl': f'/api/drawings/{job_id}/outputs/{generation_id}/engineering-pdf/{revision}',
                'verification': report}

    # Serve inline previews and explicit downloads from the same checked artifact.
    @router.get('/api/drawings/{job_id}/outputs/{generation_id}/engineering-pdf/{revision}')
    def download(job_id: str, generation_id: str, revision: str, download: bool = False):
        directory = artifact_directory(job_id, generation_id)
        if len(revision) != 32 or any(c not in '0123456789abcdef' for c in revision):
            raise HTTPException(404)
        target = directory / f'drawing-{revision}.pdf'
        if not target.is_file():
            raise HTTPException(404, '工程图不存在。')
        return FileResponse(target, media_type='application/pdf', filename='engineering-drawing.pdf',
                            content_disposition_type='attachment' if download else 'inline')

    return router
