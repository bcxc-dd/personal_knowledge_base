import re


def acronym_terms(question):
    return list(dict.fromkeys(re.findall(r'(?<![A-Za-z0-9])([A-Z][A-Z0-9]{1,})(?![A-Za-z0-9])', question)))


def latin_technical_terms(question):
    phrases = re.findall(r'(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9]*(?:[ -][A-Za-z][A-Za-z0-9]*)+)(?![A-Za-z0-9])', question)
    return list(dict.fromkeys([*acronym_terms(question), *phrases]))


def chinese_technical_terms(question):
    # Remove complete question expressions, not arbitrary characters inside
    # content words (for example, 请 in 申请 or 怎么 in 怎么样).
    content = re.sub(r'(?m)^\s*(?:请问|请|书中|我的)\s*', ' ', question)
    content = re.sub(r'第\s*\d+\s*章', ' ', content)
    content = re.sub(r'在([\u4e00-\u9fff]{2,})中(?=\s*[，,、])', r' \1 ', content)
    compare = '分别' in content
    content = re.sub(
        r'为什么|什么是|是什么|指什么|怎么样|怎样获得|怎样|怎么|如何|有什么|有哪些|做什么|'
        r'都有谁|可以获得|可以|强调先做|需要|驻留在|它会|的主线|分别|各自|主要|哪些|什么|多久|相比',
        ' ', content,
    )
    if compare:
        content = re.sub(r'和|与|及|、', ' ', content)
    content = re.sub(r'是(?=\s*\d)|[吗呢](?=\s*[？?。！!]|\s*$)', ' ', content)
    return list(dict.fromkeys(re.findall(r'[\u4e00-\u9fff]{2,}', content)))


def lexical_terms(question):
    return list(dict.fromkeys([*latin_technical_terms(question), *chinese_technical_terms(question)]))
