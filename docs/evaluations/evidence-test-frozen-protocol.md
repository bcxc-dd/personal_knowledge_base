# Evidence TEST_FROZEN v1 协议

## 边界

本协议只评 Evidence Matcher。现有 31 条主集加 5 条 stress 全部为 DEV：真实或可信受控样本进 PRIMARY_DEV，边界/受控错误/压力样本进 DIAGNOSTIC_DEV。两类都可开发、调试和消融，不能汇报为泛化性能。英文历史 PDF 不进入本轮中文主指标。生产 parser、chunker、embedding、retrieval、索引、服务和 `assess_evidence()` 不改。

## 新文档与独立性

独立 TEST 需至少覆盖第二份中文政策/规范、中文技术资料、中文论文、表格密集资料，每份 5–10 个真实用户问题，总数 20–40。每份记录发布机构、正式 URL、题名/版本、下载时间、PDF SHA-256、页数、文本层状态、许可证/可使用范围及与既有 DEV 文档的不同点；对照现有开发文档 ID/SHA，确认该来源未参与 E4 规则设计。来源与题集一旦被 E0/E4 运行，测试版本永久保留；若用结果调规则，该版本降为 DEV，下一次需要全新独立 TEST。

## 逐题人工流程

1. **先写 query 和 required facts**：覆盖 WH、YES_NO、COMPARISON、DEFINITION、NUMERIC_LOOKUP、CONDITION、COMPOUND、TABLE_LOOKUP。选自然提问，保留数值、范围、例外、否定、跨句、同义表达等真实难点。
2. **定位 PDF 原页与 evidence**：记录 page、bbox（如有）、chunk ID、原文及 SHA/来源。正例和 hard negative 分开成 evidence pair；负例优先同文档真实 chunk，受控 synthetic 仅放 DIAGNOSTIC_DEV。
3. **先查 parser correctness**：人工对照 PDF 页图和 parser 输出。若答案在 PDF 但 parser 丢失、乱码或表格错列，标 `PARSING_FAILURE`；该 pair 不纳入 matcher 主指标，同时保留独立解析失败统计。此步在看 matcher 输出之前完成。
4. **标 gold**：在当前 evidence 上确定 covered/missing、FULL/PARTIAL/NONE、expected facts/answer、relation/risk/canonical；YES/NO 允许有据的 NO 为 FULL；旧版现行范围必须分离。
5. **真人签核**：复核人逐条确认/更正/排除并记录理由、身份和时间。agent 暂拟不等于人工签核。

## 运行门槛与冻结

运行 E0/E4 前，必须同时存在：36 条 DEV 人工签核；新 TEST 每个 pair 的人工签核；所有 parser failure 在先验清单中；query、gold、来源、split 的规范化文件及 SHA-256；E0/E4 代码 commit、文件哈希、规则版本和配置哈希；一次性只读运行脚本及固定评分器版本。冻结清单记录 UTC 时间、文件字节数与 SHA-256；任何字段变更产生新版本，不覆盖旧版本。首次冻结后只运行 E0 production matcher 对 E4 current prototype，不引入 E5。

## 评分与报告

三分类分别计算 precision/recall/F1、macro F1 和混淆矩阵；按文档与问题类型分层报告，防止单一来源主导。另报 required fact recall、fact precision、full fact coverage；没有结构化 matcher 输出的字段一律 `NOT_OBSERVABLE`，不能从 gold 猜测。可观察的 numeric value、operator、scope、relation、table cell、YES/NO polarity 单独计正确率。正负 pair 分开报，重点列 `NONE→FULL`、`NONE→PARTIAL`、`PARTIAL→FULL`，逐题列 stale、否定、数字、scope、表格错误。人工错误分析归纳 false positives/false negatives。

生产迁移要看多文档独立改善、FULL recall、NONE precision、结构取值与真实失败 `policy-team`/`policy-gpa`，同时查系统性退化、延迟、复杂度；没有单一 accuracy 阈值。TEST 运行后不据该集调 E4；如需 rule refinement 或 NLI，先将其转 DEV，再另建独立集。

## 当前状态

截至 2026-10-03，旧 36 条 v2 DEV 已依据用户逐条复核意见冻结：27 条 `CONFIRMED`、9 条 `RELABELLED`，见 `test-results/evidence-annotation-freeze-2026-10-03/dataset-v2-dev-frozen.json` 及其 SHA manifest。四份独立中文 PDF 的 21 题和 21 个同文档真实负例已形成 agent 暂拟审阅包，仍须真人核对 query、gold、PDF 原页、parser、正负例。正式 TEST_FROZEN 数量为 0；新资料尚未运行 E0/E4，不能支持生产迁移。

后续执行状态（同日）：用户完成 21 题逐题签核，17 条确认、4 条修订、0 条排除。`test-results/evidence-test-frozen-2026-10-03-v1/` 保存 TEST_FROZEN v1、最终审阅表和 manifest；20 道单 chunk 主集与 1 道 F03 跨 chunk 诊断分开计分。`test-results/evidence-test-blind-2026-10-03-v1/` 保存唯一一次 E0/E4 盲测输出及失败分析。两者在 40 个主指标 pair 上均为 20/40，未观察到 E4 增量；不迁移，不据这份冻结 TEST 调整 E4 或 gold。上段是签核前的历史状态，不代表现状。
