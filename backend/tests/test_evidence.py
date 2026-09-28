from app.evidence import assess_evidence


def test_requirement_question_accepts_the_gpa_rule_without_exact_question_wording():
    result = assess_evidence('推免是否有绩点要求  ', [{
        'chunk_id': 'promotion-page-2', 'document_id': 'promotion',
        'name': '2027届本科毕业生推免工作细则.pdf',
        'text': '二、推荐条件。申请者须通过全部应修必修课程，必修课程平均学分绩点大于等于3.2。',
    }])

    assert result.status == 'supported'
    assert result.evidence_chunk_ids == ('promotion-page-2',)


def test_requirement_question_does_not_borrow_an_unrelated_policy_or_bare_metric():
    citations = [
        {'chunk_id': 'scholarship', 'document_id': 'scholarship', 'name': '2027年奖学金细则',
         'text': '奖学金申请条件：必修课程平均学分绩点大于等于3.2。'},
        {'chunk_id': 'mention', 'document_id': 'promotion', 'name': '2027届推免细则',
         'text': '推免工作小组会记录所有申请者的绩点统计信息。'},
    ]

    result = assess_evidence('推免是否有绩点要求？', citations)

    assert result.status == 'insufficient'
    assert result.evidence_chunk_ids == ()


def test_requirement_question_does_not_use_a_different_year():
    result = assess_evidence('2027届推免是否有绩点要求？', [
        {'chunk_id': 'next-year', 'document_id': 'promotion', 'name': '2027届推免细则',
         'text': '2028年起，申请推免者的平均学分绩点须达到3.4。'},
    ])

    assert result.status == 'insufficient'


def test_requirement_question_rejects_a_document_for_another_explicit_year():
    result = assess_evidence('2028届推免是否有绩点要求？', [
        {'chunk_id': 'old-year', 'document_id': 'promotion', 'name': '2027届推免细则',
         'text': '推荐条件：必修课程平均学分绩点大于等于3.2。'},
    ])

    assert result.status == 'insufficient'


def test_requirement_lookup_generalizes_to_another_policy_and_metric_wording():
    result = assess_evidence('奖学金是否有平均分要求？', [
        {'chunk_id': 'award-rule', 'document_id': 'award', 'name': '2027年奖学金细则',
         'text': '奖学金申请条件：平均成绩应达到80分，且所有课程合格。'},
    ])

    assert result.status == 'supported'
    assert result.evidence_chunk_ids == ('award-rule',)


def test_gpa_threshold_question_does_not_cite_rank_exception_or_score_weight():
    result = assess_evidence('推免是否有绩点要求？', [
        {'chunk_id': 'rank-exception', 'document_id': 'promotion', 'name': '2027届推免细则',
         'text': '人工智能创新班学生无绩点排名要求。申请人应对照相应条件选择一类进行申请。'},
        {'chunk_id': 'score-weight', 'document_id': 'promotion', 'name': '2027届推免细则',
         'text': '学习能力分主要依据必修课平均学分绩点，在综合评价分中所占比率不低于70%。'},
        {'chunk_id': 'base-threshold', 'document_id': 'promotion', 'name': '2027届推免细则',
         'text': '推荐条件：须通过当前全部应修必修课程，必修课程平均学分绩点大于等于3.2。'},
    ])

    assert result.status == 'supported'
    assert result.evidence_chunk_ids == ('base-threshold',)


def test_numeric_requirement_uses_absolute_gpa_rule_not_ranking_or_score_weight():
    citations = [
        {'chunk_id': 'rank', 'document_id': 'promotion', 'name': '2027届推免细则',
         'text': '申请推免者，必修课程平均学分绩点原则上在专业排名前35%。'},
        {'chunk_id': 'weight', 'document_id': 'promotion', 'name': '2027届推免细则',
         'text': '学习能力分依据平均学分绩点，在综合评价分中占比不低于70%。'},
        {'chunk_id': 'threshold', 'document_id': 'promotion', 'name': '2027届推免细则',
         'text': '推荐条件：必修课程平均学分绩点大于等于3.2。'},
    ]
    result = assess_evidence('推免需要多少绩点？', citations)
    assert result.status == 'supported'
    assert result.evidence_chunk_ids == ('threshold',)


def test_numeric_requirement_does_not_treat_percentage_rank_as_score_threshold():
    result = assess_evidence('推免需要多少绩点？', [
        {'chunk_id': 'rank', 'document_id': 'promotion', 'name': '2027届推免细则',
         'text': '推免的必修课程平均学分绩点原则上在专业排名前35%。'},
    ])
    assert result.status == 'insufficient'
    assert result.evidence_chunk_ids == ()


def test_numeric_requirement_generalizes_to_income_and_respects_policy_scope():
    citations = [
        {'chunk_id': 'other', 'document_id': 'scholarship', 'name': '奖学金细则',
         'text': '奖学金申请者月收入不得超过8000元。'},
        {'chunk_id': 'income', 'document_id': 'rental', 'name': '租房补贴细则',
         'text': '租房补贴申请者月收入不超过5000元。'},
    ]
    result = assess_evidence('租房补贴需要多少月收入？', citations)
    assert result.status == 'supported'
    assert result.evidence_chunk_ids == ('income',)


def test_numeric_requirement_does_not_borrow_threshold_from_another_section_of_same_document():
    result = assess_evidence('奖学金要多少平均分？', [
        {'chunk_id': 'award-heading', 'document_id': 'handbook', 'name': '学生事务汇编',
         'text': '奖学金评审办法：学生可依据综合评价结果申请。'},
        {'chunk_id': 'grant-rule', 'document_id': 'handbook', 'name': '学生事务汇编',
         'text': '助学金申请条件：平均成绩应达到80分。'},
    ])
    assert result.status == 'insufficient'
    assert result.evidence_chunk_ids == ()


def test_numeric_requirement_does_not_treat_ranking_position_as_score():
    result = assess_evidence('推免需要多少绩点？', [
        {'chunk_id': 'rank', 'document_id': 'promotion', 'name': '推免细则',
         'text': '推免申请条件：绩点排名不低于10名。'},
    ])
    assert result.status == 'insufficient'


def test_numeric_requirement_accepts_numeric_range_wording():
    for wording in ('推免申请条件：绩点为3.2以上。', '推免申请条件：绩点3.2及以上。'):
        result = assess_evidence('推免需要多少绩点？', [
            {'chunk_id': 'threshold', 'document_id': 'promotion', 'name': '推免细则',
             'text': wording},
        ])
        assert result.status == 'supported'
        assert result.evidence_chunk_ids == ('threshold',)


def test_numeric_requirement_rejects_other_policy_in_shared_title():
    result = assess_evidence('奖学金要多少平均分？', [
        {'chunk_id': 'grant', 'document_id': 'handbook', 'name': '奖学金与助学金实施细则',
         'text': '助学金申请条件：平均成绩应达到80分。'},
    ])
    assert result.status == 'insufficient'


def test_numeric_requirement_uses_year_of_the_threshold_clause():
    result = assess_evidence('2027届推免需要多少绩点？', [
        {'chunk_id': 'next-year', 'document_id': 'promotion', 'name': '2027届推免细则',
         'text': '2027届推免条件如下。2028年起，绩点不低于3.5。'},
    ])
    assert result.status == 'insufficient'


def test_numeric_requirement_rejects_other_policy_in_same_chunk():
    result = assess_evidence('奖学金要多少平均分？', [
        {'chunk_id': 'mixed', 'document_id': 'handbook', 'name': '奖学金与助学金实施细则',
         'text': '奖学金评审方式按综合表现确定。助学金申请条件：平均成绩应达到80分。'},
    ])
    assert result.status == 'insufficient'


def test_numeric_requirement_rejects_mixed_year_clause():
    result = assess_evidence('2027届推免需要多少绩点？', [
        {'chunk_id': 'mixed-year', 'document_id': 'promotion', 'name': '2027届推免细则',
         'text': '2027届推免条件如下，2028年起绩点不低于3.5。'},
    ])
    assert result.status == 'insufficient'


def test_numeric_requirement_rejects_negated_threshold():
    result = assess_evidence('推免需要多少绩点？', [
        {'chunk_id': 'not-required', 'document_id': 'promotion', 'name': '推免细则',
         'text': '推免申请条件：绩点未达到3.2时也可以报名。'},
    ])
    assert result.status == 'insufficient'


def test_lexical_only_prefill_decode_body_supports_both_parts():
    result = assess_evidence('预填充和解码分别做什么？', [{
        'chunk_id': 'page-14',
        'retrieval_sources': ['lexical'],
        'vector_similarity': None,
        'text': '模型先处理输入，这一阶段称为预填充；随后逐步生成新 token，这一阶段称为解码。',
    }])

    assert result.status == 'supported'
    assert result.evidence_chunk_ids == ('page-14',)


def test_generic_gpu_evidence_does_not_support_precise_cluster_count():
    result = assess_evidence('书中给出了某特定公司内部 GPU 集群的精确数量吗？', [{
        'chunk_id': 'gpu',
        'retrieval_sources': ['vector'],
        'vector_similarity': 0.8,
        'text': 'GPU 是人工智能训练常用的加速硬件。',
    }])

    assert result.status == 'insufficient'


def test_contents_hit_is_not_usable_definition_evidence():
    result = assess_evidence('什么是 AI Infra？', [{
        'chunk_id': 'contents',
        'retrieval_sources': ['lexical'],
        'text': '目录：第 1 章 AI Infra',
    }])

    assert result.status == 'insufficient'


def test_prefill_decode_workload_keeps_comparative_body_not_generic_performance():
    result = assess_evidence('prefill 和 decode 的负载特点有什么差异？', [
        {'chunk_id': 'generic', 'text': '不同任务的性能有差异，批处理能复用权重。'},
        {'chunk_id': 'workload', 'text': 'prefill 可以同时处理较多已知 token，一次权重读取参与更多乘加，通常受算力限制；低并发 decode 逐步生成，每步读取权重和旧 KV，通常受内存带宽限制。'},
    ])

    assert result.status == 'supported'
    assert result.evidence_chunk_ids == ('workload',)


def test_chapter_summary_keeps_substantive_intro_but_does_not_count_it_as_complete():
    result = assess_evidence('第 10 章训练系统重点讨论哪些系统问题？', [
        {'chunk_id': 'contents', 'text': '第 10 章 训练系统：训练状态、通信与恢复。'},
        {'chunk_id': 'chapter', 'text': '第 10 章 训练系统\n全参数训练需要保存权重、梯度和优化器状态。反向传播需要保留激活和缓冲区，状态分片带来通信，长期训练还要保存 checkpoint 并应对故障恢复。'},
    ])

    assert result.status == 'partial'
    assert result.evidence_chunk_ids == ('chapter',)


def test_chapter_intro_without_long_term_recovery_is_only_partial():
    result = assess_evidence('第 10 章训练系统重点讨论哪些系统问题？', [
        {'chunk_id': 'intro', 'text': '第 10 章 训练系统\n全参数训练需要保存权重、梯度和优化器状态。反向传播还要保存激活和缓冲区，分片减轻显存压力，但通信带来等待。训练持续数周时，等待输入、保存 checkpoint 和'},
    ])

    assert result.status == 'partial'
    assert result.evidence_chunk_ids == ('intro',)
    assert len(result.supported_subquestions) == 1
    assert len(result.unsupported_subquestions) == 2


def test_chapter_overview_requires_state_execution_and_long_term_summary_evidence():
    result = assess_evidence('第 10 章训练系统重点讨论哪些系统问题？', [
        {'chunk_id': 'intro', 'text': '第 10 章 训练系统\n全参数训练需要保存权重、梯度和优化器状态。反向传播还需要激活和缓冲区，占用显存。系统要确定这些状态存放在哪里以及需要保留多久，还需比较不同训练方案的容量开销。'},
        {'chunk_id': 'execution', 'text': '本章小结\nZeRO 减少状态复制，重计算与卸载换取显存空间；通信与计算决定每步关键路径。'},
        {'chunk_id': 'recovery', 'text': '长期训练要计入数据准备、checkpoint 保存和故障重做；RL 要跟踪策略版本并保证训推一致性。'},
    ])

    assert result.status == 'supported'
    assert result.evidence_chunk_ids == ('intro', 'execution', 'recovery')


def test_chapter_overview_excludes_toc_and_sends_relevant_same_page_continuation():
    result = assess_evidence('第 10 章训练系统重点讨论哪些系统问题？', [
        {'chunk_id': 'intro', 'text': '第 10 章 训练系统\n全参数训练需要保存权重、梯度和优化器状态。反向传播还需要激活和缓冲区，占用显存。系统要确定这些状态存放在哪里以及需要保留多久，还需比较不同训练方案的容量开销。'},
        {'chunk_id': 'toc', 'text': '第 10 章 训练系统 . . . . . . . . 391\n10.2 训练状态的分片、重计算与卸载 . . . . . . . . 397\n10.3 训练步流水调度与通信重叠 . . . . . . . . 411'},
        {'chunk_id': 'continuation', 'context_reason': 'same_page', 'text': '训练持续数周时，等待输入、保存 checkpoint 和故障后的重复计算也会影响完成时间。训练计算图决定参数预取、梯度通信与后续反向计算如何重叠。'},
        {'chunk_id': 'execution', 'context_reason': 'chapter_summary', 'text': '本章小结\nZeRO 减少状态复制，重计算与卸载换取显存空间；通信与计算决定每步关键路径。'},
        {'chunk_id': 'recovery', 'context_reason': 'chapter_summary', 'text': '长期训练要计入数据准备、checkpoint 保存和故障重做；RL 要跟踪策略版本并保证训推一致性。'},
        {'chunk_id': 'result', 'context_reason': 'chapter_summary', 'text': '最终方案比较得出 48 卡可在期限内完成，而 32 卡不能按期完成训练任务。'},
    ])

    assert result.status == 'supported'
    assert result.evidence_chunk_ids == ('intro', 'continuation', 'execution', 'recovery', 'result')


def test_training_only_parameter_evidence_is_partial_for_comparison():
    result = assess_evidence('训练和推理在模型参数的作用上有什么区别？', [
        {'chunk_id': 'training', 'text': '训练通过样本调整模型参数'},
    ])

    assert result.status == 'partial'
    assert len(result.supported_subquestions) == 1
    assert '训练' in result.supported_subquestions[0]
    assert len(result.unsupported_subquestions) == 1
    assert '推理' in result.unsupported_subquestions[0]
    assert result.evidence_chunk_ids == ('training',)


def test_both_parameter_roles_are_supported_by_same_excerpt():
    result = assess_evidence('训练和推理在模型参数的作用上有什么区别？', [
        {'chunk_id': 'both', 'text': '训练通过样本调整模型参数；推理使用训练得到的参数处理输入、产生输出。'},
    ])

    assert result.status == 'supported'
    assert result.evidence_chunk_ids == ('both',)


def test_unspecified_company_cluster_count_requests_clarification_despite_numbers():
    result = assess_evidence('书中给出了某特定公司内部 GPU 集群的精确数量吗？', [
        {'chunk_id': 'gpu-count', 'text': '参考架构中有 2048 张 GPU，分布在多个机柜。'},
    ])

    assert result.status == 'insufficient'
    assert result.evidence_chunk_ids == ()
    assert '公司' in result.clarification
    assert '集群' in result.clarification
    assert '时间' in result.clarification


def test_unspecified_product_price_requests_clarification_despite_numbers():
    result = assess_evidence('书中给出了某个未指名产品的精确单价吗？', [
        {'chunk_id': 'price', 'text': '算例假设 GPU 的单价为 20000 元。'},
    ])

    assert result.status == 'insufficient'
    assert result.evidence_chunk_ids == ()
    assert '产品' in result.clarification
    assert '规格' in result.clarification
    assert '计价' in result.clarification
    assert '时间' in result.clarification


def test_other_policy_eligibility_question_uses_threshold_evidence():
    result = assess_evidence('我的平均分是79，可以申请奖学金吗？', [
        {'chunk_id': 'scholarship-terms', 'text': '奖学金申请条件：平均成绩达到80分，且没有课程不及格。满足要求后按综合成绩排名。'},
    ])

    assert result.status == 'supported'
    assert result.evidence_chunk_ids == ('scholarship-terms',)


def test_other_policy_member_question_requires_names_not_just_group_mention():
    result = assess_evidence('评审委员会都有谁？', [
        {'chunk_id': 'overview', 'text': '评审委员会负责审核报名材料，并对结果进行监督。'},
        {'chunk_id': 'members', 'text': '评审委员会成员如下：主任张甲，副主任李乙，委员王丙。'},
    ])

    assert result.status == 'supported'
    assert result.evidence_chunk_ids == ('members',)


def test_similar_but_unrelated_policy_does_not_answer_eligibility_question():
    result = assess_evidence('怎么样可以获得推免资格？', [
        {'chunk_id': 'other-policy', 'text': '奖学金申请条件：平均成绩达到80分，且没有课程不及格。满足要求后按综合成绩排名。'},
    ])

    assert result.status == 'insufficient'


def test_eligibility_paraphrase_uses_relevant_conditions_instead_of_hard_refusal():
    result = assess_evidence('怎么样可以拥有推免资格', [
        {'chunk_id': 'basic', 'document_id': 'promotion',
         'text': '推荐条件：申请推免者须通过全部必修课程，必修课程平均学分绩点大于等于3.2。'},
        {'chunk_id': 'selection', 'document_id': 'promotion',
         'text': '申请推免资格者须满足一类学术条件，并按照综合评价分排名择优推荐。'},
    ])

    assert result.status == 'supported'
    assert result.evidence_chunk_ids == ('basic', 'selection')


def test_eligibility_paraphrase_with_incomplete_conditions_is_partial():
    result = assess_evidence('怎样拿到奖学金申请资格？', [
        {'chunk_id': 'basic', 'document_id': 'award',
         'text': '奖学金申请条件：平均成绩达到80分，所有课程合格。'},
    ])

    assert result.status == 'partial'
    assert result.evidence_chunk_ids == ('basic',)
    assert result.unsupported_subquestions == ('缺少完整条件或甄选依据',)


def test_eligibility_paraphrase_does_not_use_unrelated_policy():
    result = assess_evidence('怎么样可以拥有推免资格', [
        {'chunk_id': 'award', 'document_id': 'award',
         'text': '奖学金申请条件：平均成绩达到80分，按综合评价排名择优授予资格。'},
    ])

    assert result.status == 'insufficient'
    assert result.evidence_chunk_ids == ()


def test_supervisory_group_does_not_answer_selection_group_membership():
    result = assess_evidence('院推免小组都有谁', [
        {'chunk_id': 'supervision', 'text': '院推免工作监督小组成员如下：组长王甲，成员李乙。'},
    ])

    assert result.status == 'insufficient'


def test_eligibility_evidence_excludes_post_award_obligations():
    result = assess_evidence('怎样获得奖学金申请资格？', [
        {'chunk_id': 'conditions', 'document_id': 'award',
         'text': '奖学金申请条件：平均成绩达到80分。各专业按综合成绩排名择优授予资格。'},
        {'chunk_id': 'after-award', 'document_id': 'award',
         'text': '获得奖学金资格后必须参加宣传活动，明年起还须完成额外培训。'},
    ])

    assert result.status == 'supported'
    assert result.evidence_chunk_ids == ('conditions',)


def test_eligibility_evidence_excludes_next_year_rules_from_current_policy():
    result = assess_evidence('怎样获得奖学金申请资格？', [
        {'chunk_id': 'current', 'document_id': 'award', 'name': '2027年奖学金细则',
         'text': '2027年奖学金申请条件：平均成绩达到80分，按综合成绩排名择优授予资格。'},
        {'chunk_id': 'next-year', 'document_id': 'award', 'name': '2027年奖学金细则',
         'text': '2028年起申请奖学金资格须采用首次考试成绩，体质测评纳入综合评价。'},
    ])

    assert result.status == 'supported'
    assert result.evidence_chunk_ids == ('current',)


def test_technical_requirements_question_does_not_use_policy_eligibility_gate():
    result = assess_evidence('训练模型需要什么条件？', [
        {'chunk_id': 'training-needs',
         'text': '训练模型需要足够显存和训练数据，并有可靠的优化器配置。'},
    ])

    assert result.status == 'supported'
    assert result.evidence_chunk_ids == ('training-needs',)


def test_personal_numeric_eligibility_needs_matching_metric_threshold():
    result = assess_evidence('我的绩点是3.1，可以保研吗？', [
        {'chunk_id': 'age-rule',
         'text': '推免资格申请者年龄至少18岁，并按照综合评价结果择优推荐。'},
    ])

    assert result.status == 'insufficient'
    assert result.evidence_chunk_ids == ()
