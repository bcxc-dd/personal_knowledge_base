from dataclasses import dataclass
import re

from .terms import lexical_terms


@dataclass(frozen=True)
class EvidenceAssessment:
    status: str
    supported_subquestions: tuple[str, ...]
    unsupported_subquestions: tuple[str, ...]
    evidence_chunk_ids: tuple[str, ...]

    def to_dict(self):
        return {
            'status': self.status,
            'supported_subquestions': list(self.supported_subquestions),
            'unsupported_subquestions': list(self.unsupported_subquestions),
            'evidence_chunk_ids': list(self.evidence_chunk_ids),
        }


def split_core_subquestions(question):
    match = re.fullmatch(r'\s*([^和、，,？?]+?)和([^分？?]+?)分别(.+?[？?])\s*', question)
    if match:
        return (f'{match.group(1).strip()}{match.group(3)}', f'{match.group(2).strip()}{match.group(3)}')
    return (question.strip(),)


def _substantive(text):
    return len(text) >= 8 and not re.search(r'^\s*(目录|contents|参考文献|references)\b', text, re.I)


def _supports(part, hit):
    text = str(hit.get('text', ''))
    if not _substantive(text):
        return False
    terms = [term for term in lexical_terms(part) if len(term) >= 2]
    if not terms or not any(term.lower() in text.lower() for term in terms):
        return False
    if re.search(r'精确(数量|单价)|多少张卡|未指名|虚构缩写', part):
        return bool(re.search(r'\d', text) and re.search(r'(GPU|价格|单价|ZZQ)', text, re.I))
    return True


def assess_evidence(question, citations):
    parts = split_core_subquestions(question)
    supported, unsupported, evidence_ids = [], [], []
    for part in parts:
        matches = [hit for hit in citations if _supports(part, hit)]
        if matches:
            supported.append(part)
            evidence_ids.extend(hit['chunk_id'] for hit in matches if hit.get('chunk_id'))
        else:
            unsupported.append(part)
    status = 'supported' if not unsupported else ('partial' if supported else 'insufficient')
    return EvidenceAssessment(status, tuple(supported), tuple(unsupported), tuple(dict.fromkeys(evidence_ids)))
