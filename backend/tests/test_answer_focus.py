from app.answer_focus import answer_focus_note


def test_chapter_resource_focus_requires_all_facts_in_supplied_evidence():
    question = '第 2 章模型架构主要要解决什么资源问题？'
    evidence = [
        {'text': '第 2 章模型架构。哪些权重可以共享，哪些上下文状态需长期保存，哪些只需暂存。'},
        {'text': '本章小结。矩阵尺寸影响容量和运算量，batch、上下文长度、KV 组织与专家激活改变不同资源项。'},
    ]
    note = answer_focus_note(question, evidence)
    assert all(term in note for term in ('容量', '运算量', '读写量', '权重', '状态', '临时数据',
                                        'batch', '上下文长度', 'KV', '专家激活'))
    assert answer_focus_note(question, evidence[:1]) == ''
    assert answer_focus_note('长上下文为什么会变慢？', evidence) == ''


def test_technical_answer_focus_mentions_only_source_supported_missing_dimensions():
    cases = [
        ('为什么先做数量级估算？', '先列出约束和遗漏，实际开销要继续用测量校正。', ('遗漏', '测量校正')),
        ('长上下文怎样改变计算和存储需求？', '全局 KV 随上下文增长，每步读取旧 KV 并计算注意力；递推状态大小固定。',
         ('处理更多 token', '逐 token', '旧 KV', '固定状态')),
        ('prefill 和 decode 的负载特点有什么差异？',
         'prefill 同时处理已知 token；低并发 decode 读取旧 KV，瓶颈受 batch、上下文、模型和硬件影响。',
         ('旧 KV', '低并发', 'batch')),
    ]
    for question, source, terms in cases:
        note = answer_focus_note(question, [{'text': source}])
        assert all(term in note for term in terms)
        assert answer_focus_note(question, [{'text': '只给出了概念名称。'}]) == ''
