"""A bounded interpretation of the current question shared by retrieval and evidence."""

from dataclasses import dataclass
import re

from .terms import lexical_terms as extract_lexical_terms


@dataclass(frozen=True)
class QueryPlan:
    original: str
    intent: str
    subject: str | None
    metric: str | None
    lexical_terms: tuple[str, ...]
    vector_queries: tuple[str, ...]
    required_facts: tuple[str, ...]
    explicit_year: str | None

    def to_dict(self):
        return {
            'original': self.original,
            'intent': self.intent,
            'subject': self.subject,
            'metric': self.metric,
            'lexical_terms': list(self.lexical_terms),
            'vector_queries': list(self.vector_queries),
            'required_facts': list(self.required_facts),
            'explicit_year': self.explicit_year,
        }


_REQUIREMENT_PATTERNS = (
    re.compile(r'(?P<subject>[\u4e00-\u9fff]{2,16}?)(?:是否有|有没有|有无)(?P<metric>[\u4e00-\u9fff]{2,16}?)(?:的)?(?:要求|门槛|条件)'),
    re.compile(r'(?P<subject>[\u4e00-\u9fff]{2,16}?)对(?P<metric>[\u4e00-\u9fff]{2,16}?)有什么(?:要求|门槛|条件)'),
    re.compile(r'(?P<subject>[\u4e00-\u9fff]{2,16}?)[，,、]\s*(?P<metric>[\u4e00-\u9fff]{2,16}?)有什么(?:要求|门槛|条件)'),
    re.compile(r'(?P<subject>[\u4e00-\u9fff]{2,16}?)的(?P<metric>[\u4e00-\u9fff]{2,16}?)(?:要求|门槛|条件)(?:是什么|有哪些)?'),
    re.compile(r'(?P<subject>[\u4e00-\u9fff]{2,16}?)有(?P<metric>[\u4e00-\u9fff]{2,16}?)(?:的)?(?:要求|门槛|条件)(?:吗|么)?'),
)

_NUMERIC_REQUIREMENT_PATTERNS = (
    re.compile(r'(?P<subject>[\u4e00-\u9fff]{2,16}?)(?:(?:最低|至少)?(?:需要|要|须达到|应达到)|(?:最低|至少)(?:需要|要)?)(?:多少|几)(?P<metric>[\u4e00-\u9fff]{2,16}?)(?=才能|才|可以|可|[？?。！!]|$)'),
    re.compile(r'(?P<subject>[\u4e00-\u9fff]{2,16}?)的(?P<metric>[\u4e00-\u9fff]{2,16}?)(?:最低|至少)(?:是|要|需要|达到)?(?:多少|几)'),
    re.compile(r'(?P<subject>[\u4e00-\u9fff]{2,16}?)的(?P<metric>[\u4e00-\u9fff]{2,16}?)(?:要求|门槛)(?:是|要|需要)?(?:多少|几)'),
    re.compile(r'(?P<subject>[\u4e00-\u9fff]{2,16}?)(?:最低|至少)(?P<metric>[\u4e00-\u9fff]{2,16}?)(?:是|要|需要|达到)?(?:多少|几)'),
    re.compile(r'(?P<metric>[\u4e00-\u9fff]{2,16}?)(?:多少|几)(?:才)?(?:可以|能|够)(?P<subject>[\u4e00-\u9fff]{2,16})'),
)

_UNDIVIDED_METRICS = ('平均学分绩点', '平均成绩', '学分绩点', '平均分', '月收入', '绩点', '收入', '年龄')


def _requirement_subject_metric(question):
    content = re.sub(r'^\s*(?:请问|请|关于)\s*', '', question)
    content = re.sub(r'^20\d{2}\s*届\s*', '', content)
    for pattern in _REQUIREMENT_PATTERNS:
        match = pattern.search(content)
        if match:
            subject = match.group('subject').strip()
            metric = match.group('metric').strip()
            if len(subject) >= 2 and len(metric) >= 2:
                return subject, metric
    return None


def _numeric_requirement_subject_metric(question):
    content = re.sub(r'^\s*(?:请问|请|关于)\s*', '', question)
    content = re.sub(r'^20\d{2}\s*届\s*', '', content)
    for pattern in _NUMERIC_REQUIREMENT_PATTERNS:
        match = pattern.search(content)
        if match:
            subject = re.sub(r'^(?:申请|报考)', '', match.group('subject').strip())
            metric = match.group('metric').strip()
            if len(subject) >= 2 and len(metric) >= 2 and not re.search(r'和|与|及|、', metric):
                return subject, metric
    match = re.search(r'(?P<prefix>[\u4e00-\u9fff]{4,20}?)(?:需要|要)(?:多少|几)(?=[？?。！!]|$)', content)
    if match:
        for metric in _UNDIVIDED_METRICS:
            if match.group('prefix').endswith(metric):
                subject = re.sub(r'^(?:申请|报考)', '', match.group('prefix')[:-len(metric)])
                if len(subject) >= 2:
                    return subject, metric
    return None


def _search_terms(subject, metric):
    terms = [subject, metric]
    if subject == '保研':
        terms.extend(('推免', '推荐免试'))
    if subject == '推免':
        terms.append('推荐免试')
    if metric == '绩点':
        terms.append('学分绩点')
    if metric == '平均分':
        terms.append('平均成绩')
    return tuple(dict.fromkeys(terms))


def build_query_plan(question: str) -> QueryPlan:
    original = str(question)
    normalized = original.strip()
    year = re.search(r'20\d{2}', normalized)
    numeric_requirement = _numeric_requirement_subject_metric(normalized)
    if numeric_requirement:
        subject, metric = numeric_requirement
        rewrite = f'{subject} {metric} 数值门槛'
        return QueryPlan(original, 'numeric_requirement_lookup', subject, metric,
                         _search_terms(subject, metric), (normalized, rewrite),
                         ('numeric_threshold', 'metric_scope'), year.group() if year else None)
    requirement = _requirement_subject_metric(normalized)
    if requirement:
        subject, metric = requirement
        rewrite = f'{subject} {metric} 要求'
        return QueryPlan(original, 'requirement_lookup', subject, metric,
                         _search_terms(subject, metric), (normalized, rewrite),
                         ('requirement', 'metric_scope'), year.group() if year else None)
    return QueryPlan(original, 'general', None, None,
                     tuple(extract_lexical_terms(normalized)), (normalized,), (),
                     year.group() if year else None)
