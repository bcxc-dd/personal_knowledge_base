"""Local HTTP endpoints for inspecting and correcting extracted PDF pages."""

from io import BytesIO
import json
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError

from .pdf_review import has_suspect_glyphs, read_pdf_page, text_hash
from .store import uid


def pdf_review_router(engine) -> APIRouter:
    router = APIRouter()
    images_dir = engine.root / 'review_images'

    def pdf_or_404(doc_id: str) -> dict:
        doc = engine.store.document(doc_id)
        if not doc:
            raise HTTPException(404, '资料不存在或已删除。')
        if doc['suffix'] != '.pdf':
            raise ValueError('此资料不是 PDF。')
        return doc

    @router.get('/api/documents/{doc_id}/pdf-pages/{page_number}')
    def get_pdf_page(doc_id: str, page_number: int):
        doc = pdf_or_404(doc_id)
        raw_text, page_count = read_pdf_page(Path(doc['path']), page_number)
        correction = engine.store.pdf_correction(doc_id, page_number)
        return {
            'raw_text': raw_text, 'page_count': page_count,
            'source_hash': doc['hash'], 'raw_text_hash': text_hash(raw_text),
            'suspected': has_suspect_glyphs(raw_text),
            'correction': correction['corrected_text'] if correction else None,
            'revision': correction['updated_at'] if correction else None,
            'rect': correction['rect'] if correction else None,
            'has_image': bool(correction and correction['image_path']),
        }

    @router.get('/api/documents/{doc_id}/pdf-pages/{page_number}/correction-image')
    def get_correction_image(doc_id: str, page_number: int):
        doc = pdf_or_404(doc_id)
        read_pdf_page(Path(doc['path']), page_number)
        correction = engine.store.pdf_correction(doc_id, page_number)
        if not correction or not correction['image_path']:
            raise HTTPException(404, '此页没有校对截图。')
        path = Path(correction['image_path']).resolve()
        if not path.is_relative_to(images_dir.resolve()) or not path.is_file():
            raise HTTPException(404, '校对截图不存在。')
        return FileResponse(path, media_type='image/png' if path.suffix == '.png' else 'image/jpeg')

    @router.put('/api/documents/{doc_id}/pdf-pages/{page_number}/correction')
    async def put_correction(doc_id: str, page_number: int,
                             source_hash: str = Form(...), raw_text_hash: str = Form(...),
                             corrected_text: str = Form(...), expected_revision: str = Form(''),
                             rect: str | None = Form(None), image: UploadFile | None = File(None)):
        pdf_or_404(doc_id)
        rectangle = None
        if rect:
            try:
                rectangle = json.loads(rect)
            except (ValueError, TypeError) as exc:
                raise ValueError('框选区域格式无效。') from exc
            if not isinstance(rectangle, list):
                raise ValueError('框选区域格式无效。')

        previous = engine.store.pdf_correction(doc_id, page_number)
        image_path = previous['image_path'] if previous else None
        new_path = None
        try:
            if image is not None:
                content = await image.read(2 * 1024 * 1024 + 1)
                if len(content) > 2 * 1024 * 1024:
                    raise ValueError('截图不能超过 2 MB。')
                try:
                    with Image.open(BytesIO(content)) as loaded:
                        fmt = loaded.format
                        width, height = loaded.size
                        loaded.verify()
                except (UnidentifiedImageError, OSError, ValueError) as exc:
                    raise ValueError('截图必须是真实的 PNG 或 JPEG 图片。') from exc
                if fmt not in {'PNG', 'JPEG'} or (image.content_type not in {'image/png', 'image/jpeg'}) \
                        or (fmt == 'PNG' and image.content_type != 'image/png') \
                        or (fmt == 'JPEG' and image.content_type != 'image/jpeg') \
                        or not (0 < width <= 10000 and 0 < height <= 10000):
                    raise ValueError('截图必须是真实的 PNG 或 JPEG 图片。')
                images_dir.mkdir(parents=True, exist_ok=True)
                new_path = images_dir / (uid() + ('.png' if fmt == 'PNG' else '.jpg'))
                new_path.write_bytes(content)
                image_path = str(new_path)
            result = engine.set_pdf_correction(doc_id, page_number, source_hash, raw_text_hash,
                                               corrected_text, rectangle, image_path, expected_revision or None)
        except Exception:
            if new_path:
                new_path.unlink(missing_ok=True)
            raise
        finally:
            if image is not None:
                await image.close()
        if previous and previous['image_path'] and previous['image_path'] != image_path:
            engine._delete_review_image(previous['image_path'])
        return {'ok': True, 'revision': result['updated_at']}

    @router.delete('/api/documents/{doc_id}/pdf-pages/{page_number}/correction')
    def delete_correction(doc_id: str, page_number: int, expected_revision: str = Query(..., min_length=1)):
        pdf_or_404(doc_id)
        engine.clear_pdf_correction(doc_id, page_number, expected_revision)
        return {'ok': True}

    return router
