# Evidence Selection & Sufficiency 隔离评测计划

用户已指定组别、顺序与禁止事项；此计划记录可复现的执行口径。仅新增 `benchmarks/evidence_pipeline/`、忽略目录 `test-results/evidence-pipeline-2026-10-01-v1/` 和项目记录。生产代码、资料、服务与索引保持原样。

1. **冻结输入。** 校验上一轮 P0 的 14 道中文查询、2319 个 B chunk、源 PDF 和生产相关代码哈希。复用已验证的隔离 SQLite/Chroma、CUDA rerank 排名；S6 重放结果必须逐 ID 与 P0 selected/final 一致，D1 词法结果必须逐 ID 与生产 L0 一致。公式题只诊断解析失败，13 道可回答题作指标分母。
2. **S6/S8/S10。** 固定 P0 rerank 列表，分别调用生产 `select_evidence_items`、三个 context expansion 函数与 `assess_evidence`。保存每题候选、selected、expanded、final 全文及排名。用冻结 B tokenizer 计算 selected token，统计宏平均 gold fact coverage、selected chunk/token、Evidence@1/3/5/10/MRR；记录已成功题退化和 assessment 状态变化。
3. **判定路径。** 对所有查询保存 QueryPlan、人工 gold facts、`assess_evidence` 完整输入输出、每个子问题对每个片段的 `_supports` 判定、字面术语命中和 benchmark 派生拒绝原因。对 `policy-team` 逐条件复核源码，禁止把诊断 reason 误称为生产接口输出。
4. **A0/A1。** A0 使用当前过滤；A1 令最终上下文等于 selected。冻结 14 题未触发 context expansion，故本题集是纯过滤消融；另有章节 q18 的扩展能力独立记录，不计主分数。统计完整证据丢失、保留与非 gold 片段移除带来的 precision 改善，不把自动 supported 当成人工正确性。
5. **D1/D2/D3。** 对相同原始 SQL Top-100 按现有分数/顺序保留每页最多 1/2/3 条不同 ID，总候选仍最多 20。首版不按文本相似度删除，因为那会引入第二变量；记录相邻同页文本重叠、unique pages、same-page ratio。复用相同 Dense，调用现有 RRF、同一 CUDA reranker、selection、context 与 assessment；D1 与 P0 对齐。
6. **复核报告。** 每题标注正确证据最后所在层与 failure taxonomy；包括 `policy-gpa`、`policy-team`、`ai-q20` 和已成功题。总结独立获益、噪声/token 代价和迁移门槛。新中文资料需人工核验后才入分母；若当前没有合格新增资料，明确限制而不阻塞固定实验。

验证：先写 benchmark helper 测试并观察失败，再实现；运行固定结果审计、benchmark 测试、后端测试和 `git diff --check`。不生成回答，因此 `GENERATION_FAILURE` 未评估。
