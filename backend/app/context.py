"""Bounded adjacent evidence for chapter-wide questions."""

import re

from .evidence import is_eligibility_question


def chapter_context_hits(question, selected, store):
    chapter = re.search(r'第\s*(\d+)\s*章', question)
    if not chapter or not re.search(r'重点|总结|概括|主要|哪些', question):
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
            other_heading = re.match(r'^\s*第\s*(\d+)\s*章[^\n]*\r?\n', rows[i]['text'])
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

        already_selected = {item['chunk_id'] for item in selected}
        context = []
        for row, reason in [*adjacent, *summary]:
            if row['id'] in already_selected:
                continue
            already_selected.add(row['id'])
            context.append({
                'chunk_id': row['id'], 'document_id': anchor['document_id'],
                'name': anchor['name'], 'location': row['location'], 'text': row['text'],
                'retrieval_sources': ['context'], 'context_reason': reason, 'selected': True,
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
