"""Explicit agent-proposed v2 annotations; no matcher output is consulted here.

`CONFIRMED` and `RELABELLED` describe the proposed review action, not a human
sign-off. Every generated record carries human_review_state=PENDING.
"""
from __future__ import annotations


def slot(fact_id, fact_type, **target):
    return {"fact_id": fact_id, "fact_type": fact_type, "target": target}


REQUIREMENTS = {
    "team_formula_only": [slot("team_formula", "conditional_adjustment", subject="团队成员", output="分值扣减式")],
    "team_rule": [slot("team_formula", "conditional_adjustment", subject="团队成员", output="分值扣减式"),
                  slot("team_floor", "numeric_floor", subject="团队成员得分", output="最低分")],
    "team_factor_yesno": [slot("team_factor_verdict", "yes_no", proposition="扣减系数为0.01")],
    "team_universal_yesno": [slot("team_universal_verdict", "yes_no", proposition="所有团队成员均按完整分值计分")],
    "gpa": [slot("gpa_threshold", "numeric_requirement", metric="必修课程平均学分绩点", scope="普通推免推荐条件")],
    "gpa_and_exemption": [slot("gpa_threshold", "numeric_requirement", metric="必修课程平均学分绩点", scope="推免推荐条件"),
                          slot("innovation_exemption", "yes_no", proposition="创新班是否豁免该门槛")],
    "gpa_yesno": [slot("gpa_verdict", "yes_no", proposition="必修课程平均学分绩点至少3.2")],
    "csp": [slot("csp_output", "conditional_value", condition={"metric": "CSP考试成绩", "operator": ">=", "value": 300}, output="g_i计分值")],
    "gqa_mqa": [slot("gqa_sharing", "relation", subject="GQA", relation="KV共享范围"),
                slot("mqa_sharing", "relation", subject="MQA", relation="KV共享范围")],
    "prefill_decode": [slot("prefill_action", "relation", subject="预填充", relation="执行动作"),
                       slot("decode_action", "relation", subject="解码", relation="执行动作")],
    "ai_infra": [slot("ai_infra_definition", "definition", subject="AI Infra"),
                 slot("ai_infra_components", "composition", subject="AI Infra")],
    "table": [slot("table_cell", "table_lookup", row="Ⅱ级甲等", column="第二等次")],
    "award_yesno": [slot("award_accumulation_verdict", "yes_no", proposition="只取最高一项且不累加")],
}


def fact(fact_id, fact_type, **value):
    return {"fact_id": fact_id, "fact_type": fact_type, **value}


TEAM_FORMULA = fact("team_formula", "conditional_adjustment", factor=0.01, expression="对应分值-0.01×(团队排名-1)", scope="团队成员")
TEAM_FLOOR = fact("team_floor", "numeric_floor", value=0, unit="分")
GPA = fact("gpa_threshold", "numeric_requirement", metric="必修课程平均学分绩点", operator=">=", value=3.2, scope="推免推荐条件")
CSP = fact("csp_output", "conditional_value", condition={"metric": "CSP考试成绩", "operator": ">=", "value": 300}, output={"metric": "g_i", "value": 0.2})
GQA = fact("gqa_sharing", "relation", subject="GQA", relation="KV共享", object="每组Q头共享一组KV")
MQA = fact("mqa_sharing", "relation", subject="MQA", relation="KV共享", object="所有Q头共享一组KV")
PREFILL = fact("prefill_action", "relation", subject="预填充", relation="处理输入")
DECODE = fact("decode_action", "relation", subject="解码", relation="逐步生成新token")
INFRA_DEF = fact("ai_infra_definition", "definition", subject="AI Infra", value="支撑AI训练和推理的基础设施")
INFRA_PARTS = fact("ai_infra_components", "composition", subject="AI Infra", components=["计算设备", "存储与互联", "组织资源的软件"])
TABLE = fact("table_cell", "table_lookup", row="Ⅱ级甲等", column="第二等次", value=0.05)


def annotation(requirement, covered, answerability, relation, expected_answer, reason,
               *, facts=(), query_type="WH", status="CONFIRMED", main=True,
               risks=(), canonical=()):
    return {"requirement_set": requirement, "covered_fact_ids": list(covered),
            "answerability": answerability, "relation_status": relation,
            "risk_flags": list(risks), "query_type": query_type,
            "expected_answer": expected_answer, "expected_facts": list(facts),
            "review_status": status, "review_reason": reason,
            "main_metric_eligible": main, "canonical_reference": list(canonical)}


A = annotation
MAIN = {
    "team-real": A("team_formula_only", ["team_formula"], "FULL", "ENTAILS", "按对应分值减去0.01×(团队排名-1)，最低0分。", "显式问题要求扣减方式；原片段给出公式，下限可作附带说明。", facts=[TEAM_FORMULA]),
    "team-alias": A("team_formula_only", ["team_formula"], "FULL", "ENTAILS", "按对应分值减去0.01×(团队排名-1)，最低0分。", "扣除与原文减去是表达差异；显式需求为扣减方式。", facts=[TEAM_FORMULA]),
    "team-topic-only": A("team_formula_only", [], "NONE", "MISSING_FACT", "证据不足，未给出团队扣减规则。", "片段只谈审核，没有扣减方式。"),
    "team-wrong-factor": A("team_factor_yesno", ["team_factor_verdict"], "FULL", "CONTRADICTS_QUERY_PROPOSITION", "否。该片段写的是0.02×(团队排名-1)。", "是否题可依据0.02明确否定0.01命题；但该受控片段与原PDF的0.01冲突，退出普通充分度主指标。", facts=[fact("team_factor_verdict", "yes_no", answer="NO", queried_factor=0.01, evidence_factor=0.02)], query_type="YES_NO", status="REMOVE_FROM_MAIN_SET", main=False, risks=["SOURCE_CONTRADICTS_CANONICAL"], canonical=[TEAM_FORMULA]),
    "team-partial-floor": A("team_rule", ["team_formula"], "PARTIAL", "MISSING_FACT", "可确定按0.01×(团队排名-1)扣减；最低分未给出。", "两项显式需求只覆盖扣减式。", facts=[TEAM_FORMULA]),
    "team-exception": A("team_universal_yesno", ["team_universal_verdict"], "FULL", "CONTRADICTS_QUERY_PROPOSITION", "否。排名第一成员例外，其余成员按排名扣减。", "例外条款足以否定全体完整计分；v1将命题冲突误当无法回答。", facts=[fact("team_universal_verdict", "yes_no", answer="NO", exception="排名第一成员", remaining="按排名扣减")], query_type="YES_NO", status="RELABELLED"),
    "gpa-real": A("gpa", ["gpa_threshold"], "FULL", "ENTAILS", "必修课程平均学分绩点不低于3.2。", "源片段给出指标、比较方向、数值和范围。", facts=[GPA], query_type="NUMERIC_LOOKUP"),
    "gpa-newline": A("gpa", ["gpa_threshold"], "FULL", "ENTAILS", "必修课程平均学分绩点不低于3.2。", "文本层断行不改变原条款。", facts=[GPA], query_type="NUMERIC_LOOKUP"),
    "gpa-ranking-negative": A("gpa", [], "NONE", "WRONG_METRIC", "证据不足，绩点排名豁免不是平均学分绩点门槛。", "排名与课程平均学分绩点是两个指标。", query_type="NUMERIC_LOOKUP"),
    "gpa-other-metric": A("gpa", [], "NONE", "WRONG_METRIC", "证据不足，3.2属于综合素质能力分。", "数字与错误指标绑定。", query_type="NUMERIC_LOOKUP"),
    "gpa-partial-exemption": A("gpa_and_exemption", ["gpa_threshold"], "PARTIAL", "MISSING_FACT", "门槛为平均学分绩点不低于3.2；创新班是否豁免未说明。", "双需求中只覆盖数值门槛。", facts=[GPA], query_type="COMPOUND"),
    "gpa-exception-scope": A("gpa", [], "NONE", "WRONG_SCOPE", "证据不足，3.2只属于创新班专项选拔。", "受控片段明确普通推免另行规定。", query_type="NUMERIC_LOOKUP"),
    "gpa-operator-negative": A("gpa_yesno", ["gpa_verdict"], "FULL", "CONTRADICTS_QUERY_PROPOSITION", "否。该片段声称低于3.2即可申请。", "是否题可依据低于3.2否定至少3.2；但受控片段与原PDF相反，退出普通主指标。", facts=[fact("gpa_verdict", "yes_no", answer="NO", queried_operator=">=", evidence_operator="<", value=3.2, metric="必修课程平均学分绩点")], query_type="YES_NO", status="REMOVE_FROM_MAIN_SET", main=False, risks=["SOURCE_CONTRADICTS_CANONICAL"], canonical=[GPA]),
    "gpa-synthetic-positive": A("gpa", ["gpa_threshold"], "FULL", "ENTAILS", "必修课程平均学分绩点不低于3.2。", "受控同义表述完整给出数值门槛。", facts=[GPA], query_type="NUMERIC_LOOKUP"),
    "csp-real": A("csp", ["csp_output"], "FULL", "ENTAILS", "CSP成绩达到300分时g_i=0.2。", "公式分支同时绑定条件和输出。", facts=[CSP], query_type="CONDITION"),
    "csp-wrong-input": A("csp", [], "NONE", "WRONG_VALUE", "证据不足，只给出达到400分时的计分。", "条件400分不能推出300分分支。", query_type="CONDITION"),
    "csp-no-output": A("csp", [], "NONE", "MISSING_FACT", "证据不足，未给出300分时g_i的计分值。", "问题只请求输出值；重复300分前提不构成部分回答。", query_type="CONDITION", status="RELABELLED"),
    "gqa-mqa-real": A("gqa_mqa", ["gqa_sharing", "mqa_sharing"], "FULL", "ENTAILS", "GQA按Q头分组共享KV；MQA所有Q头共享一组KV。", "两侧共享范围均明确。", facts=[GQA, MQA], query_type="COMPARISON"),
    "gqa-mqa-partial": A("gqa_mqa", ["mqa_sharing"], "PARTIAL", "MISSING_FACT", "只知道MQA所有Q头共用一组KV；GQA一侧未说明。", "仅有MQA一侧关系。", facts=[MQA], query_type="COMPARISON"),
    "gqa-mqa-topic": A("gqa_mqa", [], "NONE", "MISSING_FACT", "证据不足，只说两者都减少KV缓存。", "没有任一共享范围关系。", query_type="COMPARISON"),
    "gqa-mqa-swapped": A("gqa_mqa", ["gqa_sharing", "mqa_sharing"], "FULL", "SOURCE_CONTRADICTS_CANONICAL", "按该受控片段：GQA所有Q头共用一组KV，MQA按组共享；这与原书相反。", "片段形式上完整回答WH比较，但两侧事实与已核原文颠倒，退出普通充分度主指标。", facts=[fact("gqa_sharing", "relation", subject="GQA", relation="KV共享", object="所有Q头共用一组KV"), fact("mqa_sharing", "relation", subject="MQA", relation="KV共享", object="按组共享不同KV")], query_type="COMPARISON", status="REMOVE_FROM_MAIN_SET", main=False, canonical=[GQA, MQA]),
    "prefill-decode-real": A("prefill_decode", ["prefill_action", "decode_action"], "FULL", "ENTAILS", "预填充处理输入；解码逐步生成新token。", "两个阶段的动作均明确。", facts=[PREFILL, DECODE], query_type="COMPARISON"),
    "prefill-only": A("prefill_decode", ["prefill_action"], "PARTIAL", "MISSING_FACT", "只知道预填充处理输入；解码未说明。", "只覆盖一个阶段。", facts=[PREFILL], query_type="COMPARISON"),
    "ai-infra-real": A("ai_infra", ["ai_infra_definition", "ai_infra_components"], "FULL", "ENTAILS", "AI Infra是支撑训练和推理的基础设施，包含计算、存储互联和组织资源的软件。", "定义与组成同段。", facts=[INFRA_DEF, INFRA_PARTS], query_type="DEFINITION"),
    "ai-infra-topic": A("ai_infra", [], "NONE", "MISSING_FACT", "证据不足，只出现主题词。", "没有定义或组成。", query_type="DEFINITION"),
    "ai-infra-parts-only": A("ai_infra", ["ai_infra_components"], "PARTIAL", "MISSING_FACT", "可回答组成部分，定义未给出。", "只覆盖组成。", facts=[INFRA_PARTS], query_type="DEFINITION"),
    "table-real": A("table", ["table_cell"], "FULL", "ENTAILS", "Ⅱ级甲等第二等次为0.05分。", "目标行和目标列交叉值为0.05。", facts=[TABLE], query_type="NUMERIC_LOOKUP"),
    "table-header": A("table", [], "NONE", "MISSING_FACT", "证据不足，只有列名没有目标行值。", "表头本身不能回答单元格值。", query_type="NUMERIC_LOOKUP"),
    "table-wrong-row": A("table", [], "NONE", "TABLE_MAPPING_ERROR", "证据不足，只给出Ⅱ级乙等的行值。", "目标行Ⅱ级甲等缺席。", query_type="NUMERIC_LOOKUP"),
    "award-real": A("award_yesno", ["award_accumulation_verdict"], "FULL", "ENTAILS", "对，只取最高一项，不累加。", "条款明确两项限制。", facts=[fact("award_accumulation_verdict", "yes_no", answer="YES", highest_only=True, accumulates=False)], query_type="YES_NO"),
    "award-contradiction": A("award_yesno", ["award_accumulation_verdict"], "FULL", "CONTRADICTS_QUERY_PROPOSITION", "否。该受控片段说可累加多个奖项。", "证据足以回答否；但与原PDF最高一项、不累加的规则相反，退出普通主指标。", facts=[fact("award_accumulation_verdict", "yes_no", answer="NO", highest_only=False, accumulates=True)], query_type="YES_NO", status="REMOVE_FROM_MAIN_SET", main=False, risks=["SOURCE_CONTRADICTS_CANONICAL"], canonical=[fact("award_accumulation_verdict", "yes_no", answer="YES", highest_only=True, accumulates=False)]),
}


STRESS = {
    "negated-gpa": A("gpa", [], "NONE", "NEGATED", "证据只排除3.2，正式门槛未公布，无法回答具体数值。", "否定一个候选值不等于给出真正门槛。", query_type="NUMERIC_LOOKUP"),
    "revoked-team": A("team_formula_only", [], "NONE", "STALE_OR_REVOKED", "证据只给废止旧规则，现行扣减方式未公布。", "旧规则不能回答当前时态的扣减问题。"),
    "negated-mqa": A("gqa_mqa", ["gqa_sharing"], "PARTIAL", "NEGATED", "可说明GQA按组共享；MQA只给出被否定的说法，真实共享范围未给出。", "GQA一侧可答，MQA一侧不可答；其否定说法还与已核原书冲突，保留诊断不用作主指标。", facts=[GQA], query_type="COMPARISON", status="REMOVE_FROM_MAIN_SET", main=False, risks=["SOURCE_CONTRADICTS_CANONICAL"], canonical=[MQA]),
    "negated-definition": A("ai_infra", ["ai_infra_components"], "PARTIAL", "NEGATED", "可列出计算、存储互联和软件组成；定义被否定，无法可靠回答。", "组成可用，定义句带否定。", facts=[INFRA_PARTS], query_type="DEFINITION", status="RELABELLED"),
    "table-column-order": A("table", ["table_cell"], "FULL", "ENTAILS", "Ⅱ级甲等第二等次为0.05分。", "表头顺序调整后第二等次位于数值第一列；原E4诊断错取0.06。", facts=[TABLE], query_type="NUMERIC_LOOKUP"),
}
