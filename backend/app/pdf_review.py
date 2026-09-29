"""Source-page access and conservative PDF extraction anomaly signals."""

import hashlib
from pathlib import Path

from pypdf import PdfReader


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def has_suspect_glyphs(text: str) -> bool:
    return any('\ue000' <= char <= '\uf8ff' or char == '\ufffd' for char in text)


def read_pdf_page(path: Path, page_number: int) -> tuple[str, int]:
    if page_number < 1:
        raise ValueError('PDF 页码必须从 1 开始。')
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError('请先解密 PDF 再上传。')
        count = len(reader.pages)
        if count > 1500:
            raise ValueError('PDF 超过 1500 页，请拆分后上传。')
        if page_number > count:
            raise ValueError('PDF 页码超出范围。')
        return (reader.pages[page_number - 1].extract_text() or '').replace('\x00', '').strip(), count
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('PDF 解析失败，请检查文件是否完整。') from exc
