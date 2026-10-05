# Evidence Matching Robustness 隔离实验计划

本轮仅在 `benchmarks/evidence_matching/` 与忽略的 `test-results/evidence-matching-2026-10-03-v2/` 中构建规则对照；生产 `backend/app/evidence.py`、QueryPlan、检索与选证不改。用户给定的 E0→E4 顺序及正、负、partial 标签为执行准则。标签由 agent 暂标、待用户复核，分数仅作诊断。

1. 冻结上一轮已验证的 S6/S8 selected 输入、代码/题集/文档哈希。建立待人工复核的中文判定集，实际来源片段以既有 chunk ID 引用并复制全文到隔离数据文件；受控反例明确标记 agent synthetic。每项保存 query、当前 QueryPlan、gold facts、标签、理由、类别、dev/holdout 分组。标签是“片段是否支持问题要求的具体事实”，不是文档真实性判断。
2. E0 直接调用生产 `assess_evidence`，记录每条 status、证据 ID 与 gold 对照。E1 仅规范化 Unicode/空白/标点；E2 在 E1 上增加多核心短语覆盖，关键动作/关系不得被泛词覆盖；E3 只加入白名单别名；E4 对 numeric/comparison/table/definition 等意图增加独立事实约束与可解释 reason，尤其独立校验 metric/operator/value/scope。
3. 对开发集逐步比较 Support Recall/Precision、FPR/FNR、partial 准确率及 F1；holdout 只在规则冻结后运行。每个新 supported 保存 matched terms/aliases、数字约束和反例审计，任何 FALSE_SUPPORT 明列。
4. 规则级结果成立后，在冻结的原 13 题 selected 证据上回放 E0/E4：先 S6，再单独看已有 S8 的 policy-gpa 上限，不改变 evidence limit 或 location dedup。比较最终 Evidence@5、MRR、gold fact coverage、chunk/token 增量和原成功题退化。
5. 输出逐项报告、失败与迁移判断；缺新的人工核验独立中文 PDF 时保留范围限制，不用英文历史论文或待核译文充数。复验 benchmark 测试、生产后端测试、哈希与 `git diff --check`，并同步路线图与执行记录。
