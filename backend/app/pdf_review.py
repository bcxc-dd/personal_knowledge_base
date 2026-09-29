"""Source-page access and conservative PDF extraction anomaly signals."""

import hashlib
from pathlib import Path

from pypdf import PdfReader

from .parsing import Section


class PdfReviewConflict(ValueError):
    """A PDF review was superseded or its document is being processed."""


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


def apply_pdf_corrections(sections: list[Section], corrections: list[dict], source_hash: str) -> list[Section]:
    replacements = {}
    for correction in corrections:
        if correction['source_hash'] != source_hash:
            raise ValueError(f'第 {correction["page_number"]} 页对应的 PDF 文件已变化，请重新校对。')
        replacements[f'第 {correction["page_number"]} 页'] = correction
    result = []
    for section in sections:
        correction = replacements.pop(section.location, None)
        if correction is None:
            result.append(section)
            continue
        if text_hash(section.text) != correction['raw_text_hash']:
            raise ValueError(f'{section.location}的原文提取结果已变化，请重新校对。')
        result.append(Section(correction['corrected_text'], section.location))
    if replacements:
        raise ValueError('校对的 PDF 页码已变化，请重新校对。')
    return result
