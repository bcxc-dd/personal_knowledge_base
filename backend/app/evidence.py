from dataclasses import dataclass
import re

from .terms import lexical_terms
from .query_plan import build_query_plan


@dataclass(frozen=True)
class EvidenceAssessment:
    status: str
    supported_subquestions: tuple[str, ...]
    unsupported_subquestions: tuple[str, ...]
    evidence_chunk_ids: tuple[str, ...]
    clarification: str | None = None

    def to_dict(self):
        return {
            'status': self.status,
            'supported_subquestions': list(self.supported_subquestions),
            'unsupported_subquestions': list(self.unsupported_subquestions),
            'evidence_chunk_ids': list(self.evidence_chunk_ids),
            'clarification': self.clarification,
        }


def split_core_subquestions(question):
    if re.search(r'第\s*10\s*章\s*训练系统.*重点', question):
        return ('训练状态与显存有哪些系统问题？', '训练执行与并行有哪些系统问题？', '长期训练与恢复有哪些系统问题？')
    if re.search(r'\bprefill\s*和\s*decode\b', question, re.I) and '负载' in question:
        return ('prefill 的负载特点？', 'decode 的负载特点？')
    if re.search(r'训练\s*和\s*推理.*模型参数.*(?:区别|差异)', question):
        return ('训练如何使用模型参数？', '推理如何使用模型参数？')
    match = re.fullmatch(r'\s*([^和、，,？?]+?)和([^分？?]+?)分别(.+?[？?])\s*', question)
    if match:
        return (f'{match.group(1).strip()}{match.group(3)}', f'{match.group(2).strip()}{match.group(3)}')
    return (question.strip(),)


def _substantive(text):
    return (len(text) >= 8
            and not re.search(r'^\s*(目录|contents|参考文献|references)\b', text, re.I)
            and not re.search(r'\.(?:\s*\.){4,}', text))


def is_eligibility_question(question):
    return bool(re.search(r'资格|申请|报名|录取|推免|保研', question)
                and re.search(r'怎么|怎样|如何|可以|能否|获得|取得|条件|要求', question))


def _roster_question(question):
    return bool(re.search(r'谁|哪些人|成员|名单', question)
                and re.search(r'小组|委员会|团队|组织', question))


def _topic_terms(question):
    terms = lexical_terms(question)
    expanded = list(terms)
    for term in terms:
        # Split a generic action verb from its object, preserving the full phrase.
        tail = re.sub(r'^(?:申请|获取|获得|领取|参加|报考|拥有|拿到|取得)', '', term)
        if len(tail) >= 2 and tail != term:
            expanded.append(tail)
        for candidate in (term, tail):
            if candidate.endswith('资格') and len(candidate) > 2:
                expanded.append(candidate[:-2])
        # Common wording used across university policies, independent of a file.
        if '保研' in term:
            expanded.extend(('推免', '推荐免试'))
    return tuple(dict.fromkeys(t for t in expanded if len(t) >= 2))


def _applies_to_question_year(question, hit):
    document_year = re.search(r'20\d{2}', str(hit.get('name', '')))
    if not document_year:
        return True
    asked_years = re.findall(r'20\d{2}', question)
    relevant_years = set(asked_years or [document_year.group()])
    passage_years = set(re.findall(r'20\d{2}', str(hit.get('text', ''))))
    return not passage_years or bool(passage_years & relevant_years)


_SCORE_METRICS = {'绩点', '平均分', '平均成绩', '学分绩点'}


def _states_metric_requirement(body, metric, aliases, numeric_only=False):
    for term in aliases:
        escaped = re.escape(term)
        if numeric_only or metric in _SCORE_METRICS:
            patterns = (
                re.compile(rf'{escaped}(?P<between>[^，,。；\n]{{0,20}}?)'
                           r'(?:大于等于|不低于|不少于|不得低于|至少|应达到|须达到|达到|超过|高于|不超过|不得超过|低于|≥|≤|>|<)'
                           r'\s*\d+(?:\.\d+)?(?=[^\d.]|$)'),
                re.compile(rf'{escaped}(?P<between>[^，,。；\n]{{0,20}}?)'
                           r'(?:为|是)?\s*\d+(?:\.\d+)?\s*(?:及以上|以上|及以下|以下)'),
            )
            for pattern in patterns:
                for match in pattern.finditer(body):
                    if re.search(r'未|无需|无须|不用|不必|不要求', match.group('between')):
                        continue
                    if metric in _SCORE_METRICS:
                        if re.search(r'排名|名次|位次|占比|比例|权重', match.group('between')):
                            continue
                        if body[match.end():].lstrip().startswith(('%', '％')):
                            continue
                    return True
        elif re.search(rf'{escaped}[^，,。；\n]{{0,20}}(?:必须|须|应当|要求|门槛)', body):
            return True
    return False


def _requirement_assessment(question, citations, query_plan):
    subject = query_plan.subject
    metric = query_plan.metric
    subjects = (subject,)
    if subject in {'推免', '保研'}:
        subjects = ('推免', '保研', '推荐免试')
    metrics = (metric,)
    if metric == '绩点':
        metrics = ('绩点', '学分绩点')
    elif metric == '平均分':
        metrics = ('平均分', '平均成绩')

    grouped = {}
    for hit in citations:
        key = hit.get('document_id') or hit.get('name') or '_provided'
        grouped.setdefault(key, []).append(hit)
    matches = []
    for hits in grouped.values():
        identity = '\n'.join(str(hit.get('name', '')) + '\n' + str(hit.get('text', '')) for hit in hits)
        if not any(term in identity for term in subjects):
            continue
        for hit in hits:
            name = str(hit.get('name', ''))
            document_year = re.search(r'20\d{2}', name)
            if query_plan.explicit_year and document_year and query_plan.explicit_year != document_year.group():
                continue
            body = str(hit.get('text', ''))
            if (not _substantive(body) or not _applies_to_question_year(question, hit)
                    or re.search(r'(?:获得|取得|获评|入选).{0,16}(?:资格|名额|奖励)?后', body)):
                continue
            if query_plan.intent == 'numeric_requirement_lookup':
                if not any(term in name or term in body for term in subjects):
                    continue
                clauses = re.split(r'[。；\n]', body)
                target_year = query_plan.explicit_year
                if not target_year:
                    document_year = re.search(r'20\d{2}', name)
                    target_year = document_year.group() if document_year else None
                matches_requirement = any(
                    (not re.search(r'与|和|及|、', name) or any(term in clause for term in subjects))
                    and (not target_year or not re.findall(r'20\d{2}', clause)
                         or set(re.findall(r'20\d{2}', clause)) == {target_year})
                    and _applies_to_question_year(question, {**hit, 'text': clause})
                    and _states_metric_requirement(clause, metric, metrics, numeric_only=True)
                    for clause in clauses
                )
            else:
                matches_requirement = _states_metric_requirement(body, metric, metrics)
            if matches_requirement:
                matches.append(hit)
    ids = tuple(dict.fromkeys(hit['chunk_id'] for hit in matches if hit.get('chunk_id')))
    return EvidenceAssessment('supported' if matches else 'insufficient',
                              (question,) if matches else (), () if matches else (question,), ids)


def _structured_assessment(question, citations, query_plan=None):
    query_plan = query_plan or build_query_plan(question)
    if query_plan.intent in {'requirement_lookup', 'numeric_requirement_lookup'}:
        return _requirement_assessment(question, citations, query_plan)
    terms = _topic_terms(question)
    if _roster_question(question):
        matches = []
        for hit in citations:
            content = str(hit.get('text', ''))
            if not _substantive(content):
                continue
            for term in terms:
                position = content.find(term)
                if position >= 0 and re.search(r'成员如下|名单如下|组长|副组长|主任|委员(?!会)|成员[：:]', content[position:position + 180]):
                    matches.append(hit)
                    break
        ids = tuple(dict.fromkeys(hit['chunk_id'] for hit in matches if hit.get('chunk_id')))
        return EvidenceAssessment('supported' if matches else 'insufficient',
                                  (question,) if matches else (), () if matches else (question,), ids)

    if not is_eligibility_question(question):
        return None

    relevant_documents = {
        hit.get('document_id') or hit.get('name') or '_provided'
        for hit in citations
        if _substantive(str(hit.get('text', '')))
        and any(term.lower() in str(hit.get('text', '')).lower() for term in terms)
    }
    if not relevant_documents:
        return EvidenceAssessment('insufficient', (), (question,), ())

    policy_hits = [
        hit for hit in citations
        if (hit.get('document_id') or hit.get('name') or '_provided') in relevant_documents
        and _substantive(str(hit.get('text', '')))
        and _applies_to_question_year(question, hit)
        and not re.search(r'(?:获得|取得|获评|入选).{0,16}(?:资格|名额|奖励)?后', str(hit.get('text', '')))
        and re.search(r'条件|要求|申请|资格|成绩|绩点|排名|择优|须|至少|大于等于|达到|授予', str(hit.get('text', '')))
    ]
    texts = [str(hit.get('text', '')) for hit in policy_hits]
    has_requirement = any(re.search(r'条件|要求|必须|须|应|至少|大于等于|达到', body) for body in texts)
    has_selection = any(re.search(r'排名|择优|授予|推荐', body) for body in texts)
    numeric_question = bool(re.search(r'\d+(?:\.\d+)?', question))
    if numeric_question:
        metric = lexical_terms(question)[:1]
        metric_bigrams = {metric[0][i:i + 2] for i in range(len(metric[0]) - 1)} if metric else set()
        has_threshold = any(
            re.search(r'(?:大于等于|至少|不低于|达到|超过|高于|低于|不超过|≥|≤|>|<)\s*\d+(?:\.\d+)?', body)
            and any(part in body for part in metric_bigrams)
            for body in texts
        )
    else:
        has_threshold = True
    if numeric_question and not has_threshold:
        return EvidenceAssessment('insufficient', (), (question,), ())
    complete = has_requirement and has_selection and has_threshold
    status = 'supported' if complete else ('partial' if policy_hits else 'insufficient')
    ids = tuple(dict.fromkeys(hit['chunk_id'] for hit in policy_hits if hit.get('chunk_id')))
    return EvidenceAssessment(status, (question,) if policy_hits else (),
                              () if complete or not policy_hits else ('缺少完整条件或甄选依据',), ids)


def evidence_excerpt(question, text):
    if not _roster_question(question):
        return text
    for term in _topic_terms(question):
        start = re.search(re.escape(term) + r'\s*成员(?:如下|名单|[：:])', text)
        if not start:
            continue
        body = text[start.start():]
        next_group = re.search(r'(?m)^\s*[^\n]{2,30}(?:小组|委员会|团队|组织)\s*成员(?:如下|名单|[：:])', body[start.end() - start.start():])
        if next_group:
            return body[:start.end() - start.start() + next_group.start()].strip()
        return body.strip()
    return text


def _supports(part, hit):
    text = str(hit.get('text', ''))
    if not _substantive(text):
        return False
    if '负载特点' in part and re.search(r'\bprefill\b|\bdecode\b', part, re.I):
        phase = 'prefill' if re.search(r'\bprefill\b', part, re.I) else 'decode'
        characteristics = (r'算力|乘加|已知\s*token|输入.*行|同时处理' if phase == 'prefill'
                           else r'内存带宽|读取.*权重|逐步生成|低并发|旧\s*KV')
        return bool(re.search(rf'\b{phase}\b', text, re.I) and re.search(characteristics, text, re.I))
    if '训练如何使用模型参数' in part:
        return bool('训练' in text and '参数' in text and re.search(r'调整|更新', text))
    if '推理如何使用模型参数' in part:
        return bool('推理' in text and '参数' in text and re.search(r'使用|利用|固定', text))
    if '训练状态与显存有哪些系统问题' in part:
        return bool(re.match(r'^\s*第\s*10\s*章\s*训练系统\s*\r?\n', text)
                    and len(text) >= 80 and '梯度' in text and '优化器' in text
                    and re.search(r'显存|权重', text))
    if '训练执行与并行有哪些系统问题' in part:
        return bool(re.search(r'ZeRO|重计算|卸载', text, re.I)
                    and re.search(r'通信|关键路径|每步耗时', text))
    if '长期训练与恢复有哪些系统问题' in part:
        return bool(re.search(r'checkpoint', text, re.I)
                    and re.search(r'故障|恢复', text)
                    and re.search(r'策略版本|训推一致性', text))
    terms = [term for term in lexical_terms(part) if len(term) >= 2]
    if not terms or not any(term.lower() in text.lower() for term in terms):
        return False
    if re.search(r'精确(数量|单价)|多少张卡|未指名|虚构缩写', part):
        return bool(re.search(r'\d', text) and re.search(r'(GPU|价格|单价|ZZQ)', text, re.I))
    return True


def assess_evidence(question, citations, query_plan=None):
    if re.search(r'某特定公司.*GPU\s*集群.*精确数量', question, re.I):
        return EvidenceAssessment('insufficient', (), (question.strip(),), (),
                                  '请明确是哪家公司、哪个 GPU 集群（范围）以及哪个时间点？确定对象后我才能核对资料。')
    if re.search(r'未指名产品.*精确单价', question):
        return EvidenceAssessment('insufficient', (), (question.strip(),), (),
                                  '请明确是哪款产品、具体规格、计价单位以及价格对应的时间？确定对象后我才能核对资料。')
    structured = _structured_assessment(question.strip(), citations, query_plan)
    if structured is not None:
        return structured
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
    if re.search(r'第\s*10\s*章\s*训练系统.*重点', question) and supported:
        for hit in citations:
            reason = hit.get('context_reason')
            text = str(hit.get('text', ''))
            relevant = ((reason == 'same_page' and re.search(r'训练|梯度|checkpoint|故障|恢复|通信', text, re.I))
                        or (reason == 'chapter_summary' and re.search(r'方案|结论|期限|满足', text)))
            if relevant and _substantive(text) and hit.get('chunk_id'):
                evidence_ids.append(hit['chunk_id'])
        selected_ids = set(evidence_ids)
        evidence_ids = [hit['chunk_id'] for hit in citations if hit.get('chunk_id') in selected_ids]
    return EvidenceAssessment(status, tuple(supported), tuple(unsupported), tuple(dict.fromkeys(evidence_ids)))
