from app.query_plan import build_query_plan


def test_technical_questions_add_one_focused_vector_query_without_changing_original():
    examples = [
        ('为什么生成时复用 KV 缓存？', ('旧 token', '重算')),
        ('为什么先做数量级估算？', ('遗漏', '测量')),
        ('长上下文怎样改变计算和存储需求？', ('KV', '固定状态')),
    ]
    for question, expected_terms in examples:
        plan = build_query_plan(question)
        assert plan.vector_queries[0] == question
        assert len(plan.vector_queries) == 2
        assert all(term in plan.vector_queries[1] for term in expected_terms)
    assert build_query_plan('长上下文是什么意思？').vector_queries == ('长上下文是什么意思？',)


def test_requirement_question_keeps_original_and_extracts_independent_terms():
    question = '推免是否有绩点要求  '

    plan = build_query_plan(question)

    assert plan.original == question
    assert plan.intent == 'requirement_lookup'
    assert plan.subject == '推免'
    assert plan.metric == '绩点'
    assert {'推免', '绩点'} <= set(plan.lexical_terms)
    assert '推免是否有绩点要求' not in plan.lexical_terms
    assert plan.vector_queries[0] == question.strip()
    assert len(plan.vector_queries) == 2
    assert '3.2' not in ' '.join(plan.vector_queries)
    assert plan.required_facts == ('requirement', 'metric_scope')


def test_requirement_paraphrases_share_intent_without_adding_facts():
    for question in ('推免有无绩点门槛？', '推免对绩点有什么要求？',
                     '推免的绩点要求是什么？', '推免有绩点要求吗？', '奖学金是否有平均分要求？'):
        plan = build_query_plan(question)
        assert plan.intent == 'requirement_lookup'
        assert plan.subject in {'推免', '奖学金'}
        assert plan.metric in {'绩点', '平均分'}
        assert plan.subject in plan.lexical_terms
        assert plan.metric in plan.lexical_terms
        assert '3.2' not in ' '.join(plan.vector_queries)


def test_unknown_question_falls_back_to_original_query():
    question = '什么是 KV Cache？'

    plan = build_query_plan(question)

    assert plan.intent == 'general'
    assert plan.vector_queries == (question,)
    assert plan.subject is None
    assert plan.metric is None


def test_personal_gpa_question_preserves_user_number_and_does_not_invent_threshold():
    question = '我的绩点是3.1，可以保研吗？'

    plan = build_query_plan(question)

    assert plan.intent != 'requirement_lookup'
    assert '3.1' in plan.original
    assert all('3.2' not in query for query in plan.vector_queries)


def test_explicit_year_is_preserved_but_not_added_when_missing():
    assert build_query_plan('2027届推免是否有绩点要求？').explicit_year == '2027'
    assert build_query_plan('推免是否有绩点要求？').explicit_year is None


def test_numeric_requirement_questions_extract_subject_and_metric_across_domains():
    examples = (
        ('推免需要多少绩点？', '推免', '绩点'),
        ('推免需要多少绩点才能申请？', '推免', '绩点'),
        ('推免绩点需要多少？', '推免', '绩点'),
        ('推免最低绩点是多少？', '推免', '绩点'),
        ('绩点多少可以推免？', '推免', '绩点'),
        ('推免的绩点要求是多少？', '推免', '绩点'),
        ('申请推免需要多少绩点？', '推免', '绩点'),
        ('奖学金要多少平均分？', '奖学金', '平均分'),
        ('奖学金的平均分最低是多少？', '奖学金', '平均分'),
        ('租房补贴需要多少月收入？', '租房补贴', '月收入'),
    )
    for question, subject, metric in examples:
        plan = build_query_plan(question)
        assert plan.intent == 'numeric_requirement_lookup'
        assert plan.subject == subject
        assert plan.metric == metric
        assert {subject, metric} <= set(plan.lexical_terms)
        assert plan.vector_queries[0] == question
        assert all('3.2' not in query for query in plan.vector_queries)


def test_numeric_requirement_keeps_explicit_year_and_ignores_personal_eligibility():
    plan = build_query_plan('2027届推免需要多少绩点？')
    assert plan.intent == 'numeric_requirement_lookup'
    assert plan.explicit_year == '2027'
    assert build_query_plan('我的绩点是3.1，可以保研吗？').intent != 'numeric_requirement_lookup'
    assert build_query_plan('推免需要多少绩点和排名？').intent != 'numeric_requirement_lookup'
