from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


def make_text_pdf(path: Path, texts: list[str]) -> bytes:
    writer = PdfWriter()
    font = DictionaryObject({
        NameObject('/Type'): NameObject('/Font'),
        NameObject('/Subtype'): NameObject('/Type1'),
        NameObject('/BaseFont'): NameObject('/Helvetica'),
    })
    font_ref = writer._add_object(font)
    for text in texts:
        page = writer.add_blank_page(width=300, height=300)
        page[NameObject('/Resources')] = DictionaryObject({
            NameObject('/Font'): DictionaryObject({NameObject('/F1'): font_ref}),
        })
        stream = DecodedStreamObject()
        stream.set_data(f'BT /F1 12 Tf 20 250 Td ({text}) Tj ET'.encode('ascii'))
        page[NameObject('/Contents')] = writer._add_object(stream)
    writer.write(path)
    return path.read_bytes()


def test_suspect_glyphs_flags_private_use_and_replacement_only():
    from app.pdf_review import has_suspect_glyphs

    assert has_suspect_glyphs('g_i = \uf03d 0.2')
    assert has_suspect_glyphs('g_i = \ufffd 0.2')
    assert not has_suspect_glyphs('g_i = 0.2 when x_i ≥ 300')


def test_read_pdf_page_returns_one_based_original_text_and_page_count(tmp_path):
    from app.pdf_review import read_pdf_page, text_hash

    path = tmp_path / 'two.pdf'
    make_text_pdf(path, ['First page', 'Second page'])

    assert read_pdf_page(path, 1) == ('First page', 2)
    assert read_pdf_page(path, 2) == ('Second page', 2)
    assert text_hash('First page') == '0bdbb750609ca61cb4a59ff84d565d437a5cd9a1abeb8abc0aaf243ceaec70b5'

    with pytest.raises(ValueError, match='页码'):
        read_pdf_page(path, 0)
    with pytest.raises(ValueError, match='页码'):
        read_pdf_page(path, 3)
