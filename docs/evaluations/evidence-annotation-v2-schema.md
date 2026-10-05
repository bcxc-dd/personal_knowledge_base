# Evidence Matching v2 标注协议（schema 候选冻结，gold 待人工签核）

本协议只回答：给定用户问题和**这份证据**，系统能否据此回答用户显式的信息需求。`answerability` 不判断证据与外部标准事实是否一致；后者单独记录于 `relation_status`、`risk_flags` 和 `canonical_reference`。本轮 36 条标注由 agent 按用户给定语义提出，`human_review_state=PENDING`；`CONFIRMED`/`RELABELLED` 是建议的复核动作，不代表用户已经签字。

## 标签与事实

| 字段 | 含义 |
|---|---|
| `answerability=FULL` | 当前证据覆盖全部显式所需事实；YES/NO 问题中有依据的“否”也属 FULL。 |
| `answerability=PARTIAL` | 覆盖非空、但不完整的所需事实。 |
| `answerability=NONE` | 未覆盖任何可回答的所需事实；重复 query 的前提不算覆盖答案。 |
| `required_facts` | 问题要求的事实槽位，不写“未给出……”作事实。 |
| `covered_facts` / `missing_facts` | 对 `required_facts` 的无交集划分。 |
| `expected_facts` | 证据中支持的具体值或关系；若证据与标准原文相反，这里仍如实记录**证据所述**。 |
| `canonical_reference` | 仅在受控错误来源时记录已核原文事实；不参与 answerability 打分。 |
| `expected_answer` | 只依据当前证据可做的回答；NONE 时说明不足。 |

`query_type` 覆盖 WH、YES_NO、COMPARISON、DEFINITION、NUMERIC_LOOKUP、CONDITION，并用 COMPOUND 表示同时索要门槛与豁免的题。`relation_status` 是主关系；同一片段若既否定命题又与已核原文冲突，在 `risk_flags` 中额外保留 `SOURCE_CONTRADICTS_CANONICAL`。`STALE_OR_REVOKED` 表示旧规则不能回答当前规则。

FULL/PARTIAL/NONE 由所需事实槽位的覆盖数量决定；这是一条标注一致性约束，不是自动理解 PDF 的算法。对于“300 分时 `g_i` 如何计分”，输出值是所需事实；只重复 300 分条件属于 NONE。对于“至少 3.2，对吗”，证据若写 `<3.2`，YES/NO 槽位得到有依据的 NO，属于 FULL，关系为 `CONTRADICTS_QUERY_PROPOSITION`。若该受控证据与原 PDF 相反，应退出普通充分度主指标，留在诊断集考察来源正确性与拒绝策略。

只标注问题显式要求的槽位：“团队成员如何扣减”要求扣减方式；“如何扣减，最低分是多少”才同时要求扣减方式与最低分。证据多给出的事实可以用于回答说明，但不反向增加 query 的必答槽位。

## 数据划分与评分

现有 31 条主集与 5 条压力样本全部标 `DEV`；其中与标准原文冲突的受控资料退出 `PRIMARY_DEV`，压力样本均为 `DIAGNOSTIC_DEV`。没有 `TEST_FROZEN`。未来独立中文资料必须先由人标注并冻结，再运行 matcher；一旦根据测试结果修改规则，该样本转回 DEV。

历史 E0–E4 的 status 只可映射成 FULL/PARTIAL/NONE 进行**分类重算**；它们不是 v2 原生输出，也没有普遍的逐事实值、极性或范围字段。分类报告需给每类召回率、macro F1 和混淆矩阵。事实覆盖报告须区分：金标证据覆盖、诊断中可观察到的 matcher 事实覆盖、不可观察字段。数值、比较符、表格单元格必须对输出值核对；只有 `SUPPORTED`/FULL 而取出错误值不算结构化正确。不能把“输出字段缺失”当成正确，也不能从 gold 反填 matcher 输出。

独立人工复核完成前，所有 v2 指标只作诊断，不作为生产迁移依据。v1 文件和原 E0–E4 输出按 SHA-256 冻结，不覆盖、不重写；E4 matcher 保持只读。

## v2.0 字段合同

`review-rows.json` 是现有 36 条的人工复核输入；旧 `dataset-v2.json` 是只读草案。以下字段为以后 DEV 与 TEST 共用合同：

| 字段 | 约束 |
|---|---|
| `case_id`, `query`, `query_type` | 非空；`query_type` 为 WH、YES_NO、COMPARISON、DEFINITION、NUMERIC_LOOKUP、CONDITION、COMPOUND、TABLE_LOOKUP 之一。 |
| `answerability` | FULL、PARTIAL、NONE；只判当前 evidence 能否回答明确的信息需求。 |
| `required_facts`, `covered_facts`, `missing_facts` | 按稳定 `fact_id` 划分；covered 与 missing 不交且合并恰等于 required。 |
| `expected_facts`, `expected_answer` | 仅来自当前 evidence；每个 expected fact 对应 covered fact，不能从 canonical 反填。 |
| `relation_status`, `risk_flags`, `canonical_reference` | 分别表示证据与问句命题的关系、时效/矛盾等风险、已核原文参照；不混进 answerability。 |
| `document_id`, `page`, `chunk_id`, `evidence_text`, `provenance` | 真实来源必须有可回溯文档、页、chunk 与原文。受控旧 DEV fixture 可为 null，但须注明来源。多片段证据使用 `provenance.evidence_refs` 保存所有来源，前三字段为主要来源。 |
| `split`, `review_state`, `review_reason` | DEV 为 PRIMARY_DEV 或 DIAGNOSTIC_DEV；独立集才可为 TEST_FROZEN。待签核为 NEEDS_HUMAN_REVIEW，只有真人逐条确认后才可成为 HUMAN_CONFIRMED。 |

`required_facts` 每条至少有 `fact_id`, `fact_type`, `target`；`expected_facts` 至少有 `fact_id`, `fact_type` 及该类型的值字段。最少支持 `numeric_requirement`（metric/operator/value/scope）、`conditional_value`（condition/output）、`comparison_relation`（subject/relation/object）、`definition`（subject/value）、`table_lookup`（row/column/value）、`boolean_claim`（answer=YES/NO）、`policy_rule`（scope/condition/consequence）。历史 DEV 中的 `relation`、`yes_no`、`composition`、`conditional_adjustment`、`numeric_floor` 保持原样，不追溯改写；新增 TEST 优先使用规范名称。

`answerability=FULL` 当且仅当全部显式 required facts 已覆盖；YES/NO 的有据可否定答案也是 FULL，并额外标 `CONTRADICTS_QUERY_PROPOSITION`。PARTIAL 要求非空真子集；NONE 要求 covered 为空。旧规则只有在 query 明确问对应历史版本时才可覆盖事实；问现行规则时，旧规则标 `STALE_OR_REVOKED`，不得当现行答案放行。`canonical_reference` 表示核查依据，不替换 evidence 内容。

`review_state=NEEDS_HUMAN_REVIEW` 的任何 case 不得作为正式 gold。复核人逐条查看 PDF 原页/真实 chunk，填入 CONFIRM、CORRECT 或 EXCLUDE、修订理由、复核身份与时间；修订后重验事实划分和结构字段。没有人工签核就没有正式冻结的 v2 gold，也不能运行独立 TEST。
