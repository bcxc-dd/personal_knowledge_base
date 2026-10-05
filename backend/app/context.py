"""Bounded adjacent evidence for chapter-wide questions."""

import re

from .evidence import is_eligibility_question


def chapter_context_hits(question, selected, store):
    chapter = re.search(r'第\s*(\d+)\s*章', question)
    if not chapter or not re.search(r'重点|总结|概括|主要|主线|哪些', question):
        return []
    chapter_number = int(chapter.group(1))
    heading = re.compile(rf'^\s*第\s*{chapter_number}\s*章[^\n]*\r?\n')

    for anchor in selected:
        if not heading.match(anchor.get('text', '')) or len(anchor['text']) < 80:
            continue
        rows = store.chunks(anchor['document_id'])
        start = next((i for i, row in enumerate(rows) if row['id'] == anchor['chunk_id']), None)
        if start is None:
            continue
        end = len(rows)
        for i in range(start + 1, len(rows)):
            other_heading = re.search(r'(?m)^\s*第\s*(\d+)\s*章[^\n]*(?:\r?\n|$)', rows[i]['text'])
            if other_heading and int(other_heading.group(1)) != chapter_number:
                end = i
                break

        adjacent = []
        for row in rows[start + 1:end]:
            if row['location'] != anchor['location'] or len(adjacent) == 2:
                break
            adjacent.append((row, 'same_page'))
        summary_index = next((i for i in range(start + 1, end) if '本章小结' in rows[i]['text']), None)
        summary = ([(rows[i], 'chapter_summary') for i in range(summary_index, min(summary_index + 3, end))]
                   if summary_index is not None else [])

        resource_facts = []
        if '资源' in question and '计算图' in anchor['text'] and summary_index is not None:
            chapter_text = '\n'.join(row['text'] for row, _ in [*adjacent, *summary])
            if all(term in chapter_text for term in ('batch', '上下文', '专家')) and 'KV' in chapter_text:
                facets = (
                    lambda body: bool(re.search(r'全注意力.{0,35}运算量.{0,35}增长|注意力.{0,35}运算量.{0,35}上下文', body)),
                    lambda body: bool(re.search(r'batch.{0,35}每条独立请求|每条独立请求.{0,35}batch', body, re.I)
                                      and '上下文' in body),
                    lambda body: bool('KV' in body and '组数' in body and '容量' in body and '投影' in body),
                    lambda body: bool('专家' in body and re.search(r'单\s*token|每\s*token', body, re.I)
                                      and '运算' in body),
                )
                for matches in facets:
                    row = next((row for row in rows[start + 1:summary_index]
                                if matches(row['text'])), None)
                    if row is not None and row['id'] not in {item['id'] for item, _ in resource_facts}:
                        resource_facts.append((row, 'chapter_resource_fact'))

        chapter_positions = {row['id']: i for i, row in enumerate(rows[start:end], start)}
        for item in selected:
            if item.get('document_id') != anchor['document_id']:
                continue
            position = chapter_positions.get(item.get('chunk_id'))
            if position is None:
                continue
            item['chapter_evidence_role'] = (
                'intro' if position == start else
                'chapter_summary' if summary_index is not None and summary_index <= position < min(summary_index + 3, end) else
                'body'
            )

        already_selected = {item['chunk_id'] for item in selected}
        context = []
        for row, reason in [*adjacent, *summary, *resource_facts]:
            if row['id'] in already_selected:
                continue
            already_selected.add(row['id'])
            context.append({
                'chunk_id': row['id'], 'document_id': anchor['document_id'],
                'name': anchor['name'], 'location': row['location'], 'text': row['text'],
                'retrieval_sources': ['context'], 'context_reason': reason, 'selected': True,
                'chapter_evidence_role': 'body' if reason == 'chapter_resource_fact' else reason,
            })
        return context
    return []


def condition_context_hits(question, selected, store):
    if not is_eligibility_question(question) or not re.search(r'怎么|怎样|如何', question):
        return []
    already = {item['chunk_id'] for item in selected}
    context = []
    for anchor in selected:
        body = str(anchor.get('text', ''))
        if not (re.search(r'(?m)^\s*[一二三四五六七八九十]+[、.．][^\n]{0,24}(?:条件|要求)', body)
                and re.search(r'条件\s*\d+', body)):
            continue
        rows = store.chunks(anchor['document_id'])
        start = next((i for i, row in enumerate(rows) if row['id'] == anchor['chunk_id']), None)
        if start is None:
            continue
        for row in rows[start + 1:start + 3]:
            if re.match(r'^\s*[一二三四五六七八九十]+[、.．]', row['text']):
                break
            if row['id'] in already:
                continue
            already.add(row['id'])
            context.append({
                'chunk_id': row['id'], 'document_id': anchor['document_id'],
                'name': anchor['name'], 'location': row['location'], 'text': row['text'],
                'retrieval_sources': ['context'], 'context_reason': 'condition_continuation', 'selected': True,
            })
        if context:
            break
    return context


def sequence_gap_context_hits(question, selected, store, existing_context=()):
    """Fill tiny same-page gaps between selected steps, without expanding past a page."""
    if not re.search(r'步骤|流程|经历|处理过程', question):
        return []

    def shares_chunk_overlap(left, right):
        # split_sections repeats up to 60 characters across adjacent chunks.
        # Requiring a substantial exact overlap keeps unrelated same-page text out.
        limit = min(len(left), len(right), 80)
        return any(left[-width:] == right[:width] for width in range(limit, 23, -1))

    already = {item['chunk_id'] for item in [*selected, *existing_context]}
    by_document = {}
    for hit in selected:
        if hit.get('document_id') and hit.get('chunk_id') and hit.get('location'):
            by_document.setdefault(hit['document_id'], []).append(hit)
    context = []
    for document_id, hits in by_document.items():
        rows = store.chunks(document_id)
        positions = {row['id']: i for i, row in enumerate(rows)}
        by_page = {}
        for hit in hits:
            if hit['chunk_id'] in positions:
                by_page.setdefault(hit['location'], []).append(hit)
        for location, page_hits in by_page.items():
            ordered = sorted(page_hits, key=lambda hit: positions[hit['chunk_id']])
            for left, right in zip(ordered, ordered[1:]):
                gap = rows[positions[left['chunk_id']] + 1:positions[right['chunk_id']]]
                if not 0 < len(gap) <= 2 or any(row['location'] != location for row in gap):
                    continue
                if any(re.search(r'(?m)^\s*(?:第\s*\d+\s*(?:章|节)|\d+(?:\.\d+)+\s+)', row['text'])
                       for row in gap):
                    continue
                chain = [left, *gap, right]
                texts = [str(item['text']) for item in chain]
                if not all(shares_chunk_overlap(a, b) for a, b in zip(texts, texts[1:])):
                    continue
                for row in gap:
                    if row['id'] in already:
                        continue
                    already.add(row['id'])
                    context.append({
                        'chunk_id': row['id'], 'document_id': document_id,
                        'name': left['name'], 'location': row['location'], 'text': row['text'],
                        'retrieval_sources': ['context'], 'context_reason': 'same_page_gap',
                        'selected': True,
                    })
                    if len(context) == 2:
                        return context
    return context
