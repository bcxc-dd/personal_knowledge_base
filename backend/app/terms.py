import re


def acronym_terms(question):
    return list(dict.fromkeys(re.findall(r'(?<![A-Za-z0-9])([A-Z][A-Z0-9]{1,})(?![A-Za-z0-9])', question)))


def latin_technical_terms(question):
    phrases = re.findall(r'(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9]*(?:[ -][A-Za-z][A-Za-z0-9]*)+)(?![A-Za-z0-9])', question)
    return list(dict.fromkeys([*acronym_terms(question), *phrases]))


def chinese_technical_terms(question):
    content = re.sub(
        r'第\s*\d+\s*章|什么是|是什么|为什么|有什么|怎么|如何|请|书中|分别|各自|主要|哪些|'
        r'什么|多久|从|到|和|与|及|、|在|的|对|相比|吗|呢|它|会|改变|导致|影响|做|组织|作用',
        ' ',
        question,
    )
    return list(dict.fromkeys(re.findall(r'[\u4e00-\u9fff]{2,}', content)))


def lexical_terms(question):
    return list(dict.fromkeys([*latin_technical_terms(question), *chinese_technical_terms(question)]))
