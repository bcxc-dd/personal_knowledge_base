"""Conservative, source-spanned chunking for the isolated Chinese RAG benchmark."""
from __future__ import annotations

import re
import unicodedata

from app.parsing import Section, split_sections


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)).casefold()


def _line_records(source: str):
    offset = 0
    for raw in source.splitlines(keepends=True):
        body = raw.rstrip("\r\n")
        yield offset, offset + len(raw), body
        offset += len(raw)
    if not source.endswith(("\r", "\n")) and offset < len(source):
        yield offset, len(source), source[offset:]


_HEADING = re.compile(r"^(?:第\s*[一二三四五六七八九十百0-9]+\s*[章节篇]|[一二三四五六七八九十]+、|\d+(?:\.\d+){1,3}\s+[\u4e00-\u9fffA-Za-z])")
_CAPTION = re.compile(r"^(?:图|表|Figure|Table)\s*\d+(?:[-—.]\d+)?[：:\s]", re.I)
_TABLE_HEADER = re.compile(r"(?:竞赛等级|第一等次|第二等次|第三等次)")
_TABLE_ROW = re.compile(r"^(?:[ⅠⅡⅢIVX]+级|[一二三四五六七八九十]+级|[ⅠⅡⅢIVX]+\s*级).*(?:\d+(?:\.\d+)?|/)\s*$")
_EQUATION = re.compile(r"(?:[=≤≥∑√∫]|\b[a-zA-Z]_[a-zA-Z0-9]+\b|[∗∞])")
_LIST = re.compile(r"^(?:[（(][一二三四五六七八九十\d]+[）)]|[-•]|\d+[、.])")


def _kind(line: str) -> str:
    value = line.strip()
    if not value:
        return "Blank"
    if re.fullmatch(r"[—–-]?\s*\d{1,4}\s*[—–-]?", value):
        return "Footer"
    if _CAPTION.match(value):
        return "Caption"
    if _TABLE_HEADER.search(value) and len(value.split()) >= 3:
        return "Table"
    if _TABLE_ROW.match(value) and len(value.split()) >= 3:
        return "Table"
    if _HEADING.match(value) and len(value) < 80:
        return "Heading"
    if _EQUATION.search(value) and (value.endswith("=") or (len(value) < 100 and (sum(ch in "=≤≥∑√∫*/+-" for ch in value) >= 2 or re.match(r"^\d+(?:\.\d+)?,.*[xX]_?[a-zA-Z0-9]*", value)))):
        return "Equation"
    if _LIST.match(value) and len(value) < 160:
        return "List"
    return "Paragraph"


def _paragraph_text(lines: list[str]) -> str:
    # Only physical line wraps *within a classified paragraph* are repaired.
    pieces = []
    for line in lines:
        value = line.strip()
        if not value:
            continue
        if pieces and re.search(r"[A-Za-z0-9]$", pieces[-1]) and re.match(r"[A-Za-z0-9]", value):
            pieces.append(" " + value)
        else:
            pieces.append(value)
    return "".join(pieces)


def blockify_page(document_id: str, page: int, source: str, inherited_section: list[str]):
    records = list(_line_records(source))
    blocks = []
    section = list(inherited_section)
    pending = None

    def flush():
        nonlocal pending
        if not pending:
            return
        start, end, kind, lines = pending
        raw = source[start:end]
        normalized = _paragraph_text(lines) if kind == "Paragraph" else "\n".join(x.strip() for x in lines if x.strip())
        if kind == "Heading":
            number = re.match(r"^(\d+(?:\.\d+){1,3})\s+", normalized)
            level = number.group(1).count(".") + 1 if number else 1
            section[:] = section[:level - 1] + [normalized]
        block = {
            "document_id": document_id, "page": page, "block_id": f"{document_id}:p{page}:b{len(blocks)}",
            "block_type": kind, "reading_order": len(blocks), "section_path": list(section),
            "source_start": start, "source_end": end, "source_text": raw,
            "normalized_text": normalized, "bbox": None,
            "parser_source": "pypdf+conservative-block-segmentation",
        }
        if kind == "Equation":
            block.update({"recognized_latex": None, "verified": False, "recognition_source": None})
        if kind == "Table":
            block.update({"caption": None, "header": None, "rows": [], "raw_structure": raw})
        if kind == "Caption":
            block.update({"figure_relation": None})
        blocks.append(block)
        pending = None

    for start, end, line in records:
        kind = _kind(line)
        if kind == "Blank":
            flush()
            continue
        if pending and pending[2] == kind and kind in {"Paragraph", "Equation", "Table"}:
            pending = (pending[0], end, kind, pending[3] + [line])
        else:
            flush()
            pending = (start, end, kind, [line])
    flush()
    return blocks, section


def legacy_chunks(document_id: str, pages: list[dict]):
    sections = [Section(p["text"], f'第 {p["page"]} 页') for p in pages]
    rows = split_sections(sections, size=400, overlap=60)
    return [{"id": f"{document_id}:B:{r['ordinal']}", "document_key": document_id,
             "page": int(re.search(r"\d+", r["location"]).group()),
             "text": r["text"], "source_block_ids": [], "ordinal": r["ordinal"]} for r in rows]


def _tokens(tokenizer, text):
    return len(tokenizer.encode(text, add_special_tokens=True).ids)


def _table_units(block, section):
    lines = [x.strip() for x in block["normalized_text"].splitlines() if x.strip()]
    header = next((x for x in lines if _TABLE_HEADER.search(x) and len(x.split()) >= 3), None)
    if not header:
        return [(block["normalized_text"], [block["block_id"]])]
    fields = header.split()
    result = []
    for line in lines:
        if line == header:
            continue
        values = line.split()
        if len(values) == len(fields) + 1 and values[0] in {"I", "II", "III", "Ⅰ", "Ⅱ", "Ⅲ"}:
            values = [values[0] + values[1]] + values[2:]
        if len(values) == len(fields):
            result.append(("；".join(f"{name}：{value}" for name, value in zip(fields, values)), [block["block_id"]]))
        else:
            result.append((header + "\n" + line, [block["block_id"]]))
    return result or [(header, [block["block_id"]])]


def structure_chunks(document_id: str, pages: list[dict], tokenizer, target: int):
    if target < 8:
        raise ValueError("target too small")
    chunks = []
    current = []
    current_ids = []
    current_page = None
    heading = None
    previous_para = None

    def emit():
        nonlocal current, current_ids
        if current:
            value = "\n".join(current).strip()
            if value and not (heading and value == heading):
                chunks.append({"id": f"{document_id}:C{target}:{len(chunks)}", "document_key": document_id,
                               "page": current_page, "text": value, "token_count": _tokens(tokenizer, value),
                               "source_block_ids": list(dict.fromkeys(current_ids)), "ordinal": len(chunks)})
        current, current_ids = [], []

    def add(value, ids, page, prefix=None):
        nonlocal current_page, current, current_ids
        value = value.strip()
        if not value:
            return
        if current_page != page:
            emit()
            current_page = page
        candidate = "\n".join(current + [value])
        if current and _tokens(tokenizer, candidate) > target:
            emit()
        if not current and prefix and prefix != value and _tokens(tokenizer, prefix + "\n" + value) <= target:
            current.append(prefix)
        if _tokens(tokenizer, value) > target:
            # Split only an oversized single block at a token-safe boundary.
            words = re.findall(r"[^。！？；;，,\s]+[。！？；;，,]?|\s+", value)
            if len(words) == 1:
                words = list(value)
            piece = ""
            for word in words:
                if piece and _tokens(tokenizer, piece + word) > target:
                    if current and _tokens(tokenizer, "\n".join(current + [piece])) > target:
                        emit()
                    current.append(piece)
                    current_ids.extend(ids)
                    emit()
                    piece = ""
                piece += word
            if piece:
                current.append(piece)
                current_ids.extend(ids)
            return
        if current and _tokens(tokenizer, "\n".join(current + [value])) > target:
            emit()
        current.append(value)
        current_ids.extend(ids)

    for page in pages:
        for block in page["blocks"]:
            kind = block["block_type"]
            value = block["normalized_text"].strip()
            if not value:
                continue
            if kind == "Footer":
                continue
            if kind == "Heading":
                emit()
                heading = value
                previous_para = None
                continue
            if kind == "Table":
                emit()
                for row, ids in _table_units(block, block["section_path"]):
                    prefix = f"{heading}\n{block['caption']}" if heading and block.get("caption") else heading
                    add(row, ids, page["page"], prefix=prefix)
                    emit()
                previous_para = None
                continue
            if kind == "Equation":
                # Source text is preserved; no generated formula is introduced.
                add(value, [block["block_id"]], page["page"], prefix=heading if not current else None)
                previous_para = None
                continue
            add(value, [block["block_id"]], page["page"], prefix=heading if not current else None)
            previous_para = value if kind == "Paragraph" else None
        emit()
    emit()
    return chunks


def score_query(query: dict, chunks: list[dict], ranked: list[dict], source_text_by_doc: dict):
    if query.get("risk") == "unverified_formula_structure":
        return {**{f"evidence_at_{k}": False for k in (1, 3, 5, 10, 20, 50)},
                "first_full_evidence_rank": None, "mrr": 0.0,
                "failure_type": "PARSING_FAILURE", "fact_ids_found_top_50": []}
    key = query["document_key"]
    facts = query["facts"]

    def satisfied(text, fact):
        normalized = _norm(text)
        return all(_norm(term) in normalized for term in fact["all_terms"])

    source = source_text_by_doc.get(key, "")
    def on_page(chunk, fact):
        return not fact.get("source_pages") or chunk.get("page") in fact["source_pages"]

    if any(not satisfied(source, fact) for fact in facts):
        failure = "PARSING_FAILURE"
    elif any(not any(c["document_key"] == key and on_page(c, fact) and satisfied(c["text"], fact) for c in chunks) for fact in facts):
        failure = "CHUNKING_FAILURE"
    else:
        failure = None
    found = set()
    first = None
    for rank, chunk in enumerate(ranked, 1):
        if chunk["document_key"] == key:
            found.update(f["id"] for f in facts if on_page(chunk, f) and satisfied(chunk["text"], f))
        if len(found) == len(facts):
            first = rank
            break
    if failure is None:
        failure = "RETRIEVAL_FAILURE" if first is None or first > 50 else "RANKING_FAILURE" if first > 5 else "SUCCESS"
    result = {f"evidence_at_{k}": bool(first and first <= k) for k in (1, 3, 5, 10, 20, 50)}
    return {**result, "first_full_evidence_rank": first, "mrr": 1 / first if first else 0.0,
            "failure_type": failure, "fact_ids_found_top_50": sorted(found)}
