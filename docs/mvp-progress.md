# MVP execution ledger

Current roadmap: [项目路线图](project-roadmap.md). The original MVP ledger below is historical evidence, not a declaration that all current roadmap stages are complete.

Plan: docs/superpowers/plans/2026-09-19-rag-mvp.md

- User authorized implementation of v0.2. Native execution in current empty workspace.
- No repository exists; no worktree or automatic commit needed.
- Interface preflight: parser -> ingestion -> Chroma -> chat references all use stable document ID / chunk ID / location; frontend uses the API DTOs.
- User selected DeepSeek. Default local BGE embeddings avoid requiring a second key. DeepSeek key configured by user in the local UI during implementation; no secrets printed.
- Task 1: complete. Parser RED→GREEN for Chinese boundaries, empty input, DOCX tables, corrupt PDF; SQLite and ingestion tested.
- Task 2: complete. Real Chroma indexing, scope filtering, deletion, model fingerprint mismatch, missing config, answer citations and persisted history tested using controlled HTTP providers.
- Task 3: complete. Four responsive React pages, typed API and SSE client; build and front-end event tests passed. Browser uploaded sample.md and real local model generated 512-dimensional vectors.
- Review: independent read-only reviewer found cancellation stall, silent mixed-PDF page loss, and missing replacement history. Added regressions and fixed cancellation using async HTTP streaming; PDF empty extraction now reports pages and fails explicitly.
- Ruling: full document versions remain outside this MVP. Same-name changed content is rejected with explicit guidance to delete old version or rename; prevents accidental mixing of revisions. Cost: no seamless replacement or history restoration.
- Ruling: character chunking reduced to 400 with 60 overlap for BGE input headroom; embedding fingerprint bumped so prior indexes require rebuild. Existing documents are preserved and reindexed locally.
- Windows integration fix: registry mapped .js to text/plain, preventing module execution. Explicit JS/CSS MIME overrides added with a regression test.
- Ruling: single in-process worker instead of a separate process keeps Chroma ownership simple. Cost: one server process only, no multi-worker scaling.
- Ruling: local server-bound static assets and sample document download replace the need for two user-facing development servers; front-end routes are lazy-loaded.
- User's uploaded files and existing DeepSeek settings preserved during service update. Real backend network-disconnect regression passed.
- Task 4: complete. Setup/start scripts and README delivered. 19 backend tests + 2 frontend tests pass; production build passes with route splitting. Two test-dependency deprecation warnings remain (httpx TestClient / anyio alias), no functional failures.
- Real local BGE embedding + Chroma query verified in a separate process; stopped-process data copied and restored in a second process, retrieval correct. Evidence command: `.venv/Scripts/python scripts/verify_local.py`.
- Browser real-provider acceptance: sample.md uploaded, answered prototype review time and owner correctly with citation [2]; selecting reference reveals exact source paragraph. Follow-up about budget explicitly states insufficient information with citation [3]. DeepSeek key and user's existing PDFs untouched.
- Desktop and narrow-browser layouts inspected; temporary viewport override reset. Original paper PDFs successfully reindexed with smaller chunks; no original file deleted.
- Final scope: no account/auth, OCR, document version history, full export UI, or pgvector yet. Manual stopped-process backup is documented and verified. Missing extraction pages fail visibly; updates use delete/reupload rather than silent revision mixing.

## 2026-09-24：项目路线与状态校准

- 用户明确：个人实际使用价值优先，简历与面试适度考虑；暂不投入注册、多租户和复杂权限，没有具体问题前不引入更强检索策略。
- 新增 [项目路线图](project-roadmap.md)，规定阶段目标、退出证据和跨会话接续方式；当前为阶段 A（可信问答与质量闭环）。
- 核对本地 master 的 5bee8c3：已合并 RRF、中文词法、初步证据判定与诊断字段；用户反馈 q04 问题已解决。
- 尚未完成：评测与回答路径语义对齐，partial 回答约束和历史保存，诊断中的最终证据与实际生成证据一致性。不能以已有规则或单题通过认定阶段 A 完成。
- 本次仅更新文档与接续入口，未修改产品代码，未重新运行模型评测或应用测试。历史 47 项后端、2 项前端及构建通过记录来自合并时验证。

## 2026-09-24：阶段 A 题集原文校准

- 保留 v1 不变，新增 [校准说明](evaluations/2026-09-24-ai-infra-calibration.md) 与 [v2 金标准](evaluations/ai-infra-answerability-v2.json)：25 题逐项标注核心子问题、必要事实、原文证据；6 个独立受控 fixture 覆盖三种充分度状态。
- 发现 q16/q17/q18 的旧页码指向错误章节；q12 定义证据不足以支持负载差异；q23/q24 是指代不明需澄清，不应当作语料不存在事实的负例。
- 新增只读校验脚本 `scripts/verify_ai_infra_calibration.py`，验证语料身份、题号/题文保留、片段定位、fixture 分区和全文 ZZQ 搜索；该脚本不衡量 RAG 回答质量。
- 本轮校验命令见校准说明：退出码 0，519 页、25 原题、6 个 fixture、76 次定位检查均通过，ZZQ 无匹配，errors 为空；`git diff --check` 通过。未重新运行产品测试。
- 当前仍未接入 v2 运行器，未产生新的模型通过率，未改产品检索/回答/前端，不需重启或重建索引。下一步为运行器与实际回答路径对齐及真实资料逐题审阅。

## 2026-09-25：阶段 A 首次 v2 全题评测

- 新增 v2 运行记录与只读人工审阅入口，沿实际 `Engine.answer` 的 `sources`、`done` 事件保存向量/词法候选、融合前六、证据过滤后输入、回答和引用。评测在 SQLite/Chroma 快照运行，用户日常会话不增加评测题。
- [结果与逐题分析](evaluations/2026-09-25-ai-infra-v2-result.md)：25/25 回答流有 done；22 道语料可回答题中，候选完整 20、前六完整 19、送答完整 17、回答核心内容完整 15。q12/q18 是证据误拒；q05 是融合选中损失；q09/q10 候选不足；q23/q24 需澄清；f05 partial 误判。25/25 次重排因 CUDA 提供器不可用回退为 RRF。
- 原始报告保存在忽略目录 `test-results/`，含私有语料片段和回答；[人工审阅数据](evaluations/ai-infra-v2-manual-review-20260925.json)及公开摘要在 `docs/evaluations/`。新代码测试覆盖记录层次、引用编号、快照关闭和异常标签；需核对最新完整测试记录。
- 尚未修改产品问答规则或前端；用户运行服务无需重启，除非后续要使用新版评测脚本，只需重新运行脚本。

## 2026-09-25：q12/q18、f05、q23/q24 定点修复与同题集回归

- 修改 `backend/app/evidence.py` 和 `backend/app/engine.py`：q12 按 prefill/decode 两侧的负载事实过滤证据；q18 的章节正文不再被泛词规则误拒；训练/推理参数比较按两侧判断；未指明公司集群或产品时先澄清目标且不引用邻近数字。
- 先写回归测试观察到 7 项失败，再改产品代码；q18 细分 partial 时又观察到 1 项预期失败。最终版后端测试 62 通过、2 条既有依赖弃用警告；同题集复跑结果见[定点回归报告](evaluations/2026-09-25-ai-infra-targeted-regression.md)。6 个受控 fixture 状态 6/6 匹配；仍是 CUDA 重排回退为 RRF 的本机配置。
- 本机忽略的 `test-results/ai-infra-v2-regression-repeat-20260925.json` 保存完整结果。q12 恢复第 84 页正文与完整核心回答，q23/q24 直接澄清；q18 只解除全拒并正确标 partial，仍只送第 401 页首段，完整章总结不足。首次报告把该首段记为完整证据，需更正评分后再发布人工汇总指标。最终版首次全题运行 q03 曾因生成无效引用编号报错，复跑 25/25 `done`；生成稳定性仍是未解决项。
- 未修改前端或索引，无需重新构建或重建索引；既有后端进程若无自动重载，需重启方可使用新判定。下一步先处理 q18 跨片段证据，再按路线图处理其余缺口。

## 2026-09-25：q18 章节上下文补齐与严格口径全题复核

- 新增受限章节上下文：仅对明确的章概览问题且选中该章正文开头时，追加最多两个同页续段、最多三个本章小结段落；单列 `context_items`，不冒充向量/词法命中，也不重建索引。q18 实际送答为第 401 页 `:1774–1776` 与第 446 页 `:1969–1971`，章末 32/48 卡训练期限结论正确进入最终回答。
- [全题报告](evaluations/2026-09-25-ai-infra-chapter-context-review.md)与[25 题人工判分](evaluations/ai-infra-v2-manual-review-chapter-context-20260925.json)按每个独立核心问题的全部必要事实重新审阅：22 道可回答题中候选完整 17、融合前六 15、上下文扩展后 16、送答 14、最终核心回答完整 12。自动 supported 22 不等于质量通过 22。q23/q24 澄清、q25 未编造；6 个 fixture 状态匹配。历史首次指标口径偏宽，不与本次直接比较。
- 原始完整运行 `test-results/ai-infra-v2-chapter-context-answer-final-20260925.json` 在本机忽略目录，含私人原文和生成文本，不提交；本机 CUDA 重排 25/25 回退 RRF。最终代码 `pytest -q` 为 67 通过、2 条既有依赖弃用警告。尚未做前端用户复测，阶段 A 未完成。
- 下一步按报告中的失败层排查 q05/q15、q09/q10/q17、q12/q16、q06/q07/q22；修正资料范围措辞，继续 partial 和诊断一致性验收。后端无自动重载时需重启；索引无需重建、前端无需构建。

## 2026-09-26：q05/q15 覆盖式证据组装的离线上限实验

- 新增仅供评测的 `scripts/probe_coverage_upper_bound.py` 与 8 项测试；片段由金标准人工指定，严控同文档、候选/章节上下文来源、最多两片，且同页邻片必须邻接已命中的片段。实验未接入 `Engine`，不会改变用户问答。
- [实验报告](evaluations/2026-09-26-ai-infra-coverage-upper-bound.md)：q15 补第 13 页六层图及第 30 页章末后核心答案齐；q05 仅补原候选第 40 页 `:185` 仍缺复用条件，同页前片 `:184` 加入后核心事实齐。原候选第 381 页也谈位置/版本条件，但与同请求生成语境不同，不宜视为最贴切证据。补证据之后仍有“本次片段不足→整书没有”的错误范围断言。
- 成对生成原文在本机忽略的 `test-results/ai-infra-coverage-upper-bound-pair-20260926.json`。原运行器只读重跑 25 题：状态仍 22 supported / 3 insufficient、6/6 fixture 匹配、25 题送答片段 ID 与基线一致；部分向量候选尾部及 q24 第六个选中片段不同。追加盲选实验后的完整后端测试 78 通过、2 条既有依赖弃用警告。
- 追加[无金标准盲选对照](evaluations/2026-09-26-ai-infra-coverage-upper-bound.md)：q05 部分有效但重复已送答片段，q15 仍漏六层图；q23/q24 错选邻近数字，q18 返回候选池外 ID 被严格校验阻止。此盲选器**不能上线**。下一步先明确自动选择契约与盲测/反例，再选择实现方式；继续整体阶段 A 闭环。未修改产品代码、索引或前端，无须重启或构建，未做用户复测。

## 2026-09-26：推免细则基础问题拒答定位

- 保留用户四个原题为[回归案例](evaluations/2026-09-26-promotion-regression.json)，含应答边界与证据页；[定位报告](evaluations/2026-09-26-promotion-regression-analysis.md)记录隔离快照中的真实排序、词法命中、RRF 回退与 CPU 对照。
- 受控证据判定测试先观察到 4/4 按预期失败，随后标为 strict xfail，以保留未修缺陷而不把它误报为通过。四题真实回答尚未改善；未改产品代码和用户数据，无需重启或重建索引。
- 全量后端测试最终复跑 78 passed、4 xfailed、2 条既有依赖弃用警告；首次全量运行的 Windows Chroma 快照文件占用错误在单项及第二次全量复跑时未复现，暂作为偶发测试风险记录，未进行修复。
- 下一步优先制定最小修复契约，兼顾相关证据识别、关键事实覆盖、3.1 口径澄清和小组名单完整性，再在原 PDF 上做实际检索与回答验收，并回归现有不足/澄清负例。

## 2026-09-26：本机 CUDA 重排恢复

- [定位与修复记录](evaluations/2026-09-26-cuda-reranker-repair.md)：原环境只装 CPU 版 ONNX Runtime；GPU 版仍需预加载随包 CUDA/cuDNN DLL，且原代码会在模型缓存后误报设备。增加 CUDA 安装与实际 session 验证入口，真实 GPU 重排可运行。
- 本机 GPU 包安装、原 PDF 隔离快照 CUDA 重排和 8765 服务重启已完成；全量后端测试最终复跑 80 passed、4 xfailed。初次全量运行有一次既有 Windows Chroma 快照清理文件占用，单项及第二次全量通过。无需重建索引或前端构建。
- 四个推免问题仍因词法与证据判定问题拒答；下一步只处理这一剩余问题并复核不足/澄清负例。
- CUDA 修复后对四个原题做了同一会话隔离快照复测，均为 `local-reranker / cuda / fallback=false`，但仍 4/4 被证据判定误拒。第 1 题的 3.2 门槛排第 2、第 4 题的完整名单排第 1，说明“全拒答”的直接原因在[证据判定规则](evaluations/2026-09-26-promotion-regression-analysis.md)；第 3 题的 3.2 门槛仍排第 11，另有前 6 条证据截断问题。原文正确片段直接送入判定也 4/4 `insufficient`。本轮只追加诊断记录，未改产品代码、索引或测试状态，无需重启或构建。

## 2026-09-26：推免四题修复与真实资料复测

- [执行与验收记录](evaluations/2026-09-26-promotion-regression-analysis.md#修复与重新验收2026-09-26)：四题 `strict xfail` 已移除，原 PDF 的 CUDA 隔离快照四题均得到有引用的真实回答。第 1 题按绩点口径条件回答；第 2、3 题包含 3.2 门槛、学术条件四类、书面申请与择优；第 4 题完整列出院推免小组四类成员且未混入监督小组。
- 词语提取改用完整问句表达；政策资格与名单的证据判定不再依赖整段问题原样命中。对候选池做条件章节与申请步骤补证据，对条件列表做有界续段；跨届规则、获资格后的义务及其他小组不再送入相应回答。保研/推免使用跨学校领域同义词扩展，尚不代表全领域语义泛化。
- 全量后端测试 100 passed、2 条既有依赖弃用警告；AI Infra 25 题离线复跑为 22 supported / 3 insufficient、6/6 受控状态匹配，25 题 CUDA 重排无回退。后端 8765 已重启并通过健康检查；无需重建索引或前端构建。用户界面上的真人复测及独立真实政策资料盲测仍未完成，阶段 A 整体仍未完成。

## 2026-09-26：绩点要求新问法误拒定位

- 用户报告“推免是否有绩点要求  ”误拒；[隔离快照诊断](evaluations/2026-09-26-promotion-regression-analysis.md#新问法误拒定位推免是否有绩点要求2026-09-26)确认第 2 页“必修课程平均学分绩点大于等于 3.2”排第 6 且已选中，CUDA 正常，词法候选为 0。
- 词语提取保留整句 `推免是否有绩点要求`，资格证据规则又要求该整句在原文中出现，导致 `insufficient`；正确段落直送仍误拒。临时以 `绩点` 作主题词，同一批证据转为 `supported`。原四题回归未覆盖这一问法。
- 本轮仅定位并记录，未修改产品代码、测试、用户资料或索引，也未做 UI 复测；无需构建或重启。下一步将原句和相关改写、无关政策负例纳入回归，再修复词语抽取与证据匹配。

## 2026-09-26：查询理解层与绩点问法修复

- 新增共享 `QueryPlan`：对明确的要求/门槛问法提取主体和指标，词法检索使用独立词，一次额外向量查询用于受控改写，证据判定使用同一计划；原问题保留给最终回答。未识别问法沿用原路径，未增加模型生成调用、依赖或重建索引。[设计](superpowers/specs/2026-09-26-query-understanding-design.md)与[执行记录](evaluations/2026-09-26-promotion-regression-analysis.md#查询理解层实施与复测2026-09-26)。
- 原问题已增为第 5 个推免回归案例。真实 PDF 的隔离快照中，该问法只送第 2 页绩点门槛，实际答出“必修课程平均学分绩点大于等于 3.2”。前四题同会话真实生成保留有引用回答；相似问法通过、跨届及无关奖学金问法拒答。
- 后端 116 tests passed、2 条既有依赖弃用警告；AI Infra 25 题离线状态仍为 22 supported / 3 insufficient，6/6 fixture 匹配、CUDA 无回退。8765 服务已于 20:58:03 重启；真实 `/api/chat` 原句返回 `supported`、第 2 页唯一引用及“≥3.2”回答，验收临时会话已删除。尚无独立政策盲测或用户界面亲测；无需前端构建或重建索引。

## 2026-09-26：“需要多少绩点”误答定位

- 用户真实使用发现相邻问法答案矛盾：有无要求答出“≥3.2”，问数值却声称无统一最低数值。只读历史显示后问的最终引用缺第 2 页条款；[定位记录](evaluations/2026-09-26-promotion-regression-analysis.md#推免需要多少绩点误答定位2026-09-26)详列当前版本隔离快照的各阶段证据。
- 当前快照中第 2 页条款已召回且排第 6、已选中，但“需要多少绩点”走通用问法，证据判定把该片段过滤，仍将其他排名条款判为 `supported`；生成随后把本次证据缺数值误写成整份资料无数值门槛。CUDA 无回退。
- 本轮未改产品逻辑、测试、索引或用户资料；未修复。下一步先建立该问法及排名/跨政策负例回归，再按送答证据与真实回答验收。无需构建或重启。

## 2026-09-27：数值门槛问题类修复

- 将“需要多少绩点”抽象为可复用的 `numeric_requirement_lookup`，提取事项与指标，要求对应数值条款；排名百分比、评价分占比和同文档其他政策门槛不得冒充答案。[实施与复测](evaluations/2026-09-26-promotion-regression-analysis.md#数值门槛问题类修复与复测2026-09-27)。
- 回归先红后绿；代码审查发现的语序、排名名次、跨政策、跨届及否定句反例也已修复。完整后端 129 passed、2 条既有弃用警告。真实 PDF 隔离副本仅送第 2 页 3.2 条款，模型答出 ≥3.2；最终代码重启后的真实接口仍只送第 2 页并答出 ≥3.2，临时会话已删除。AI Infra 25 题离线状态保持 22 supported / 3 insufficient，6/6 fixture 匹配，CUDA 无回退，未复核该题集的生成答案。
- 尚无独立真实政策盲测，不能宣称所有相似中文问法已覆盖。未改索引或前端；后端 8765 已加载新代码并通过健康检查，前端无需构建。

## 2026-09-27：收窄资格问法的硬拒答

- 用户原句“怎么样可以拥有推免资格”在当前 PDF 隔离副本中复现 `insufficient`：第 2 页 3.2 条款和第 7 页遴选条件均已选中，CUDA 无回退；问题被抽成“拥有推免资格”，证据判定要求原样匹配而丢掉全部引用。同一批证据换成“获得推免资格”可判 `supported`。
- 资格主题抽取现在去掉“拥有／拿到／取得”等动作表述；有同主题条件却缺少甄选依据时返回 `partial`，向模型传递明确缺口。无关政策、明确数值门槛缺失、跨届及对象不明的硬拒答规则保留。先红后绿新增 4 项回归，完整后端 133 passed、2 条既有弃用警告。
- 原 PDF 隔离副本和更新后 8765 真实接口均对原句给出有引用回答，包含必修课程平均学分绩点 ≥3.2、学术条件及按综合评价择优；验收临时会话已删除。AI Infra 25 题离线判定仍为 22 supported / 3 insufficient，6/6 fixture 匹配，CUDA 无回退；未复核该题集生成答案。资格题送答证据仍包含同文档相邻政策，真实回答偏长，后续需单独收紧证据范围与审阅回答质量。独立政策盲测和用户界面亲测未完成，阶段 A 未完成；后端服务已加载改动，无需重建索引或前端构建。

## 2026-09-28：章节证据与流程断片定点修复

- [分析、改动与验证记录](evaluations/2026-09-28-failure-layer-small-optimizations.md)：明确章节概览保留本章已选小结和续段；步骤／流程问题补同页已选片段间最多两个缺口。q16 送答证据补齐，但实际回答仍漏资源变量；q06 补第 14 页第 76 段，实际回答覆盖此前遗漏的入口核验、token 化和排队。
- 完整后端测试 139 passed、2 条既有依赖弃用警告；最终代码 25 题离线充分度 22 supported / 3 insufficient，6/6 fixture 匹配、CUDA 无回退。跨章及同页无关片段反例已纳入回归。25 题尚未按金标准重新完整人工判分；单题改善不代表阶段 A 达标。
- 本轮代码仍在工作区；8765 后端已重启并通过健康检查与 q06 真实接口复测，验收临时会话已删除。索引无需重建，前端无需构建。

## 2026-09-29：六题定点证据与生成修复

- [逐题断点、改动与验证](evaluations/2026-09-29-targeted-evidence-and-generation.md)：q05 第 40 页复用条件、q09 第 3 页测量校正、q10 逐 token KV 与固定状态例外、q12 旧 KV 与趋势条件、q17 第 8 章章末判据已从相应失败层补入实际回答；q16 从章内正文补资源变量映射，并加来源条件下的生成核对。没有增加检索引擎或重建索引。
- 最终完整后端测试 147 passed、2 条既有弃用警告。原 PDF 的 25 题离线判定保持 22 supported / 3 insufficient，6/6 fixture 匹配、CUDA 重排无回退；q23–q25 无送答引用。六道目标题的真实生成按核心事实定点复核，不能由此更新 25 题整体人工得分。
- 本轮产品代码和文档仍在工作区。后端 8765 在最终代码微调后于 10:29（北京时间）重新启动，健康接口返回 `ok / Chroma / 0.1.0`；重启前实际接口 q09 包含第 3 页依据及测量校正，临时会话已删除。无需前端构建或重建索引。独立资料盲测、完整人工评分、前端真实使用与 partial／历史一致性仍待完成，阶段 A 未退出。

## 2026-09-29：25 题重新全题人工评分

- [全题报告](evaluations/2026-09-29-ai-infra-full-manual-review.md)及[逐题判分](evaluations/ai-infra-v2-manual-review-20260929.json)按 v2 金标准严格复核一次完整生成。原始私有报告为忽略目录的 `test-results/ai-infra-v2-answer-full-review-20260929.json`，隔离快照、25/25 `done`、22 supported / 3 insufficient、6/6 fixture 匹配、25/25 CUDA 重排无回退；引用编号均能映射到实际送答证据。
- 22 道可回答题中，候选/重排选中/章节扩展后/最终送答完整分别 19/18/21/19，最终回答核心完整 15；q04/q07/q14/q15/q18/q21/q22 未完整。q23/q24 正确澄清、q25 未编造。此前 9 月 25 日严格复核为送答 14、回答 12，运行配置和生成输出均有变化，不能把净增量归给单一修复。
- q14/q15 是必要片段已选中却被判定过滤；q22 是候选缺重算证据；q04/q07/q18/q21 是证据已送答但生成漏事实或范围限定。六道定点题 q05/q09/q10/q12/q16/q17 在这次运行答全。q07 存在书中常驻路径被说成普遍要求的范围风险。
- 本次只做评测与文档，不改产品代码、运行服务或索引，无需重启、构建或重建索引。独立政策盲测、真人前端使用、partial 回答与历史一致性，以及诊断与最终引用对齐仍未验收；阶段 A 未退出。下一步依失败位置小范围处理并复测。

## 2026-09-29：PDF 公式人工校对闭环

- [实施与隔离验收记录](evaluations/2026-09-29-pdf-formula-review.md)：PDF 可疑字符提示、原页图与整页提取文本对照、公式截图和框选、确认后修订、撤销及资料重建索引已实现；原 PDF 保持不变。功能提交已快进合并至本地 `master`（`bd2a3b5`），工作区先前未提交的 RAG 改动仍保留。
- 后端 159 passed、前端 7 passed，生产构建成功。推免细则第 9 页 CSP 公式在隔离资料库中修订后可检索，实际回答包含三段公式及第 9 页引用；页面保存与撤销后均回到 `ready`，撤销恢复原异常提示并清理截图。现有 8765 服务和用户资料库未修改；真人最终公式核对尚待用户完成。
- 后端 8765 已于 2026-09-29 23:01（北京时间）重启，监听进程 PID 32432；健康接口返回 `ok / Chroma / 0.1.0`，新 PDF 页校对路由已注册，现有 AI-Infra-Book.pdf 第 9 页只读请求返回 519 页总数及原文哈希。前端生产构建已在 22:54 完成。现有 PDF 无需批量重建索引，提交或撤销某页时自动重建对应资料；其他公式效果仍需逐份验证，阶段 A 未完成。

## 2026-09-30：校对本页点击后无可见反馈修复

- 真实长文档复现：按钮点击会生成校对面板，但面板插在正文列表上方；点击第 4 页片段时，面板位于视口上方约 5200 像素，用户看不到变化。现点击后立即滚动至校对面板；同一页再次点击也会定位。
- 新增回归测试覆盖首次点击和重复点击。前端 8 项测试通过，生产构建通过。已在当前 8765 服务的 AI-Infra-Book.pdf 详情页验证：点击第 4 页片段后，面板顶部位于视口内 24 像素处。仅前端改动，生产静态文件已重新构建；现有浏览器标签需刷新。无需后端重启或索引重建。推免细则第 9 页真人校对仍待用户进行。

## 2026-09-30：PDF Worker 模块 MIME 修复

- 用户打开校对面板后遇到浏览器拒绝执行模块脚本。当前 8765 实测普通 `.js` 返回 `text/javascript`，但 PDF.js Worker 的 `.mjs` 返回 `text/plain`；后端原 MIME 覆盖只处理 `.js` 和 `.css`。
- 后端为 `.mjs` 明确设置 `text/javascript`，并加入模拟错误系统映射的回归测试；PDF Worker 请求增加缓存版本，避免浏览器继续使用此前缓存的错误 MIME 响应。测试先红后绿：后端 API 10/10、前端 8/8，生产构建通过。
- 8765 服务已重启，健康接口返回 `ok / Chroma / 0.1.0`，Worker 实际响应为 `text/javascript`。刷新后的真实页面中，AI-Infra-Book.pdf 第 1 页校对画布渲染为 655×927，无预览错误或浏览器脚本错误。现有标签需刷新；无需重建索引或修改用户资料。推免细则第 9 页公式仍待用户亲自校对。

## 2026-09-30：四份现有 PDF 的解析器隔离评测

- 按用户要求，只在本地 `test-results/parser-benchmark-2026-09-30/` 运行 pypdf 6.19.0、Docling 2.131.0、Marker 2.0.0 fast/无 OCR、PyMuPDF4LLM 1.28.2。四份 PDF 共 13 个选定页，重点复核英文论文 p3/p5、AI-Infra-Book p24、推免细则 p9；保留每个工具的原始结构、统一 block 输出、ParseIssue、耗时/内存/缓存和固定检索结果。`REPORT.md`、`manifest.json`、`queries.json`、`evidence_review.json` 可复核范围与人工判据；目录被现有 ignore 规则忽略。
- 相同 400/60 chunking、本地 bge-small-zh-v1.5 向量和余弦排序下，九题的目标页 Recall@5 为 pypdf 9/9、Docling 9/9、Marker 7/9、PyMuPDF4LLM 9/9；人工核查“可回答证据进入 Top-5”仅分别为 4/9、3/9、2/9、3/9。Docling/PyMuPDF4LLM 标准配置在重点页公式块为空；Marker fast 在书 p24 空页；Docling 公式增强虽在书 p24 生成正确分式，却在细则 p9 生成幻觉内容。暂无生产迁移证据，保留现状，不启用自动 fallback。
- 验证命令包括 `normalize.py`、`retrieval.py --parser {pypdf,docling,marker_fast,pymupdf4llm}` 与 `score_evidence.py`；资源测量为隔离子进程 `measure.py`，PyMuPDF4LLM 已顺序重测。未修改生产解析器、用户资料、服务或索引；无需构建、重启、重建索引。后续需扩展公式真值、完整 Marker 模式与结构感知 chunking 的隔离试验，并以证据 Top-K 和错误答案核查作为迁移门槛；不能把九题结果推广到整个知识库。

## 2026-10-01：中文 Structure-aware Chunking B/C 隔离评测

- [固定中文题集](evaluations/structure-chunking-zh-v1.json)、`benchmarks/structure_chunking/` 与本地忽略目录 `test-results/structure-chunking-zh-2026-10-01-v2/` 已建立；保存 535 页有效文本与 Block 源位置、四组 chunk、独立 Chroma 索引、完整 Top-50、原始与人工审阅后指标。英文历史论文不进入本轮语料或评分。推免细则第 9 页的现有人工校对以相同版本应用于 B/C。
- B 的 AI 2287 + 推免 32 个 chunk 与当前 SQLite 文本、页码及顺序逐条完全一致。13 道可回答中文题的 Evidence@5：B 7/13，C256 6/13，C384 6/13，C512 7/13；MRR：0.3853、0.3322、0.3615、0.4292。公式题的 pypdf 分式关系损坏，四组均按 `PARSING_FAILURE` 计，不把字形命中算作可回答证据。
- C512 改善 MHA 与竞赛最高分条款等题，但预填充/解码由 rank 29 跌出 Top-50，MQA 变量关系由 rank 1 退到 25；Top-5 未净增。当前证据**不支持生产迁移**。下步补独立中文论文/规范文件与人工金标准，并诊断这两类退化；不启动 Hybrid/Reranker 或 parser 替换。
- 验证：`python -m pytest benchmarks/structure_chunking/test_core.py -q` 为 7 passed；正式 `python benchmarks/structure_chunking/run.py` 与 `rescore.py` 完成，报告在本地 `report.md`。未改生产 ingestion、索引或服务，无需构建、重启、重建索引。未进行生成回答或真人 UI 验证；阶段 A 仍未完成。

## 2026-10-01：中文 B/C 逐题诊断及冻结 B 的 Hybrid Retrieval 隔离评测

- 用户在上述 B/C 结果后明确要求先做退化诊断，再用冻结 B chunks 测 Dense/BM25/RRF；先前“不启动 Hybrid”是当时的下一步安排，已由最新指示取代。[Phase A 报告](../test-results/chunk-diagnosis-zh-2026-10-01/phase-a-report.md)与 `cases.md`/`cases.json` 保存 7 题的完整原文、页内跨度、token 数、Block ID 和逐题归因。C512 的预填充/解码 29→>50、MQA 1→25；MHA 5→1、GQA/MQA >50→19。C256 还将 MQA 共享事实切到相邻 chunk。诊断发现 C 超长 Block 分割丢独立分号；这属于 benchmark 实现缺陷，冻结结果未被暗中改写，后续 C 改良实验须先修复并重测。
- [Phase B 报告](../test-results/hybrid-retrieval-zh-2026-10-01/report.md)及本地 `metrics.json`、`query-results.jsonl`、`manifest.json`、`bm25-index.json.gz` 固定 2319 个中文 B chunks、相同 14 题与 gold、同一 dense Top-50；13 道可回答题的 Evidence@1/3/5/10/20/50 和 MRR 已逐项保存。Dense/BM25/RRF50 的 Evidence@5 为 7/13、10/13、11/13，MRR 为 0.3853、0.6528、0.5715。RRF50 相对 Dense 救回 4 道 Top-5 题、无 Top-5 出局；模型上下文与 MQA 独立性从 rank 1 降至 rank 2；独立新增的 Top-50 完整证据仅 GQA/MQA 比较 1 题。两道政策条款改善共用同一源 chunk，公式解析失败 1 题在所有组保持 `PARSING_FAILURE`。未运行回答生成，不能推断回答准确率。
- BM25 建索引 0.95 秒、压缩文件 1.42 MiB、Python allocation 峰值 52.6 MiB（非系统 RSS），查询平均 5.44 ms；与上轮 Dense 延迟不在同次运行，不能当成端到端对比。生产检索已具备简单词法候选与 RRF，因此这次相对 dense-only 的改进不是相对完整生产链路的增量证明。当前**不迁移** chunker、parser 或检索器；下一步增加独立中文资料与真实问题，并直接对比 BM25 与现有词法/RRF 的收益和退化。英文资料不参与当前指标。
- 验证：`.venv/Scripts/python.exe -m pytest benchmarks/structure_chunking/test_core.py benchmarks/structure_chunking/test_diagnose.py benchmarks/hybrid_retrieval/test_hybrid_core.py -q` 为 14 passed；`.venv/Scripts/python.exe -m pytest backend/tests -q --tb=short` 为 159 passed、2 条依赖弃用警告；输入/代码哈希、14 题及每组 50 条检索候选已核对。最初用系统 Python 运行后端测试因环境依赖冲突失败，改用项目 `.venv` 后通过。本轮只新增 benchmark 文件、文档及 ignored 实验产物，未改生产代码、用户索引或服务；无需构建、重启或重建索引。阶段 A 未因此完成。

## 2026-10-01：生产检索消融与 BM25 词法替换隔离评测

- [完整报告](../test-results/production-retrieval-ablation-2026-10-01-v2/report.md)和 `benchmarks/production_retrieval/` 复现实际 `Engine.retrieve` + CUDA reranker + 选证 + context expansion + `assess_evidence`，并做 P1–P5、现有/中文 ngram 两种 BM25、按页去重 L0/L1 对照。只读生产与隔离副本的 2319 个 B chunk/向量一致，14 道中文查询的 substring SQL Top-100 一致；原始轨迹、资源、逐题依据和验证文件均在本机忽略目录。英文资料没有进入本轮；公式解析失败题单列，不计入 13 道可回答题的分母。
- 13 题 P0 融合候选/重排后/已选/最终送答 Evidence@5 为 **7/11/11/10**，最终 MRR **0.6154**；中文 ngram BM25 的候选/已选/最终送答为 **11/12/11**，最终 MRR **0.5962**；现有 substring 只取消 `location` 去重也得最终 **11/13、0.5962**。BM25 仅新增 GQA/MQA 一题的最终 Top-5，关键 AI Infra 定义由 rank 1 退至 2；当前 tokenizer 版还让预填充/解码证据丢失。生产词法较 dense only 最终增加预填充/解码一题。绩点题证据在重排 rank 8、选取限额 6 被挡住；团队扣分已选 rank 1，却被 `assess_evidence` 清空。历史人工章节题 q18 单独探测到 5 条扩展上下文，未纳入主分数，也未做生成回答。
- **不迁移 BM25、chunker、parser 或重排配置。** BM25 最终 @5 只多 1/13，MRR 下降，且去重对照可得到相同 Top-5；只有两份独立中文 PDF，尚缺新的人工核验资料。下一步补中文技术文档/论文/第二份规范/表格资料，再分别验证去重、证据选取和判定误拒。复验为 benchmark 相关测试 19 passed、后端 159 passed（2 条依赖弃用警告）、14 题/2319 chunk/SQL/P0/P3/P4/excerpt 审计通过、`git diff --check` 无错误。当前仅为真实资料隔离检索验证，未生成回答、未进行用户使用验证；阶段 A 未退出。本轮未改生产代码、数据、索引或服务，无需构建、重启、重建索引。

## 2026-10-01：Evidence Selection & Sufficiency 隔离评测

- [完整报告](../test-results/evidence-pipeline-2026-10-01-v1/report.md)、`benchmarks/evidence_pipeline/` 与本机 ignored 原始轨迹在冻结 P0/同一 CUDA 排名上比较 S6/S8/S10、A0/A1，并在当前 SQL Top-100 上比较每 location 最多保留 1/2/3 条的 D1/D2/D3。14 题、2319 个中文 B chunk、生产代码和设置哈希一致；S6 与 P0 各层/判定逐题一致，D1 词法与 P0 逐条一致。英文历史资料没有进入主语料；公式解析失败题仍单列。
- 13 道可回答题的 S6/S8/S10 最终 Evidence@5/MRR 均为 **10/13、0.6154**。S8/S10 把绩点原文选至 rank 8，但判定仍为 insufficient；selected token 均值 1653→2201→2754，最终 gold coverage 没有提升。团队扣分题的已选 rank 1 完整证据被通用 `_supports` 的字面术语规则误拒；绩点题是结构化指标短语与原文不连续匹配。S6-A1 绕过过滤的完整证据为 11/13、MRR 0.6923，但 A0 在 5 题减少无关片段，未评估生成正确性，不能直接去掉过滤。
- D2 救回 GQA/MQA 最终 rank 4，最终 Evidence@5 **11/13**、MRR **0.5962**，AI Infra 定义题 1→2；D3 同指标、无新增 gold，但平均候选 unique pages 继续减少。P0 3 道最终失败题分别是 `LOCATION_DEDUP_DROP`、`SELECTION_CUTOFF`、`EVIDENCE_FILTER_DROP`，各 1；S8 后绩点题由选取截断转为过滤误拒。复验：14 题/2319 chunk/S6-P0/D1-D3 及逐层评分审计通过，benchmark 相关测试 **24 passed**、后端 **159 passed**（2 条现有依赖弃用警告）、`git diff --check` 无错误。当前**不修改生产**。后续优先隔离验证短语/指标误拒的最小修正，再补经人工核验的中文资料并复测 D2。没有生成回答或真人使用验证；阶段 A 未退出。本轮仅新增 benchmark 与文档、ignored 结果，无构建、重启或重建索引要求。

## 2026-10-03：Evidence Matching Robustness 隔离评测

- [完整报告](../test-results/evidence-matching-2026-10-03-v2/report.md)、`benchmarks/evidence_matching/`、`dataset.json`、`e0-baseline.json`、`results.json` 与 `stress.json` 冻结中文证据匹配对照；31 条主集含 11 支持、14 不支持、6 部分支持。标签由 agent 暂标，用户将稍后审阅；5 条原标 holdout 已进入开发测试，不能作为独立泛化证据。
- E0 Support Recall 6/11、Precision 6/12、负例误放行 6/14、partial 1/6；E1/E2/E3 完整支持依次 7/11、8/11、11/11，但 E3 负例误放行升至 8/14。E4 在同批开发集 31/31；冻结后新增 5 条压力样本暴露 4 条标签误判、1 条表格列序改变后错取值，不能据开发集满分迁移。
- 冻结 S6/D1 selected 回放的最终 Evidence@5 **10/13→11/13**、MRR **0.615→0.769**，救回 `policy-team`；仅作上限诊断的 S8 为 **10/13→12/13**、MRR **0.615→0.808**，救回 `policy-gpa`。13 题中原 10 道成功题按 gold fact/rank 无退化，但少量答案上下文增多，尚未检验生成答案。`ai-q20` 仍因 selected 缺正确片段无法救回；公式解析失败题不计分。
- 当前结论：**不修改生产判定、不增加 evidence limit、不改检索或索引**。先复核标签，补独立中文政策/技术/论文反例，重点约束否定、失效条款、范围和表格列绑定；再做 rule refinement 的独立验证，必要时才研究 rule-first NLI fallback。benchmark 5 项与生产证据/QueryPlan 51 项测试通过；未触及运行服务，无构建、重启或重建索引要求，阶段 A 未完成。

## 2026-10-03：Evidence Benchmark Annotation v2 草案与历史重算

- [v2 schema](evaluations/evidence-annotation-v2-schema.md)、[逐题报告](../test-results/evidence-matching-v2-2026-10-03/report.md)及 `benchmarks/evidence_annotation_v2/` 将旧五份输入按 SHA-256 冻结，新建 `dataset-v2.json`、`rescore-v2.json`、`verification.json`。没有覆盖 v1 或修改 E4 matcher。36 条（原主集 31 + stress 5）全部归 DEV/diagnostic，没有 `TEST_FROZEN`；标注由 agent 根据用户提出的新语义暂拟，`human_review_state=PENDING`，不能称为已完成独立人工复核。
- v2 区分证据能否回答（FULL/PARTIAL/NONE）、问句命题关系、与已核原文冲突风险，以及 required/covered/missing facts。主集 6/31 条改变三分类标签；4 条与已核原文冲突的受控来源移出普通充分度主指标。旧 E4 的 v1 31/31 在 v2 口径下为 **25/31**；普通 DEV 主指标 **25/27**，stress **2/5**，全部 DEV **27/36**。`table-column-order` 虽仍判 FULL，但输出 0.06，与正确的第二等次 0.05 不符；值级核验单列失败。
- v1 判定输出不普遍包含逐事实值、范围与极性，不能从三分类诚实推导全量 fact recall/precision；报告只审计显式 `matched/constraints` 的可观察数字和关系。当前**不迁移生产**、不继续修改 E4、不加 E5；下一步由用户复核 v2 gold，再从独立中文资料先标 gold/冻结，建立真正的 `TEST_FROZEN`。v2 + 旧 benchmark + 后端完整回归最终 **171 passed**、2 条既有弃用警告；此前一次完整运行有 1 项 Windows Chroma 快照文件占用失败，单测及完整复跑通过。未改生产索引、服务或用户资料，无构建、重启、重建索引要求；阶段 A 未退出。

## 2026-10-03：v2 复核包与独立中文 TEST 候选资料

- [v2 字段合同](evaluations/evidence-annotation-v2-schema.md)和 [TEST_FROZEN 协议](evaluations/evidence-test-frozen-protocol.md)明确 answerability 与命题/来源关系分离、事实槽位、来源定位、人工签核与测试失效规则。`benchmarks/evidence_annotation_v2/review_freeze.py` 从已有只读 v2 草案生成 [36 条逐案复核表](../test-results/evidence-annotation-freeze-2026-10-03/review-sheet.md)、JSON 与 SHA manifest；27 PRIMARY_DEV、9 DIAGNOSTIC_DEV 全部 `NEEDS_HUMAN_REVIEW`，用户尚未签核。
- [独立资料 intake](../test-results/test-frozen-intake-2026-10-03/intake-report.md)收集第二份中文推免细则、云密码技术白皮书、CCL 中文论文和表格密集的高校收费 PDF。四份新 PDF 的 SHA 与仓库现存四份均不同；现有 `parse_file` + 400/60 只读抽取为 9+87+11+4 页、311 chunk。另有加密 PDF、`/Gxx` 乱码与表头顺序错乱候选被排除；21 道 agent 暂拟查询和 6 个真实 chunk 负例候选待人工核定。
- **当前 TEST_FROZEN 仍为 0，未运行新资料 E0/E4，也无独立性能数字。** 待 36 条旧 DEV 与全部新 gold 经真人签核、逐题 PDF/parser 校验、hash 冻结后再首次运行。未改 E4/生产判定、索引或服务；无需构建、重启、重建索引。阶段 A 未因此完成。

## 2026-10-03：旧 DEV 人审冻结与独立 TEST 逐题审阅包

- 用户最新附件明确复核旧 36 条 v2 DEV：27 条保持现有标注，六条 GPA 题修正 required scope，`csp-no-output` 改成明确询问具体值，`gqa-mqa-swapped` 回答只据片段，`negated-definition` 消除句法歧义。新建只读 [DEV 冻结集](../test-results/evidence-annotation-freeze-2026-10-03/dataset-v2-dev-frozen.json)和 [SHA manifest](../test-results/evidence-annotation-freeze-2026-10-03/dev-freeze-manifest.json)，记录 27 `CONFIRMED`、9 `RELABELLED`、schema v2.0、复核日期及用户附件 SHA；原 v2 草案未覆盖。
- 四份新中文 PDF 的 21 题已逐题对照 12 张相关原页图、pypdf 页文本和现有 400/60 chunk，形成 [TEST 候选审阅表](../test-results/test-frozen-intake-2026-10-03/test-candidate-review-v4/review-sheet.md)、逐题结构化事实、原始 chunk 与页文本、21 个真实同文档 hard-negative pair（原 6 + 新 15）。P05/T02/T03/T04 改写以收窄问法；P06 的日期边界原文明确，保留；P04 在 `policy:8` 已含两项基本事实，不能当成严格跨 chunk 依赖证明。现有 21 题 parser 状态暂标 PASS，仍待真人逐题确认；若发现解析错列/丢事实，须先列入 parsing diagnostic。
- **TEST_FROZEN=0。** 新 TEST 的 query、gold、parser correctness、正负例与答案尚未得到人工签核，E0/E4 未在新资料运行，不能给独立泛化分数或迁移建议。下一步请用户复核审阅表；全部签核且版本/hash 冻结后，才一次性运行 E0 vs E4。benchmark 定向新增测试通过；未改生产代码、用户索引或服务，无需构建、重启、重建索引。阶段 A 未退出。

## 2026-10-03：TEST_FROZEN v1 人审签核与 E0/E4 首次盲测

- 用户逐题确认 17 题、修订 T03/A04/F03/F04 共 4 题、排除 0 题；机械检查复核 query、required facts、正负例、标签和 parser 状态。21 题均 parser PASS；F03 标为跨 chunk 诊断，不计 20 题单 chunk 主指标。签核来源、四份 PDF、chunk corpus、[最终 TEST JSON 与 SHA manifest](../test-results/evidence-test-frozen-2026-10-03-v1/test-frozen-v1-manifest.json)、E0/E4 文件哈希及[最终审阅表](../test-results/evidence-test-frozen-2026-10-03-v1/final-review-sheet.md)已冻结。TEST JSON SHA-256 为 `c81ad45cb79a518b4ebb5183952cd4a7e7e5a17b2a37bc56dfb62cee07f0a9d0`。
- 在该冻结输入上只运行一次 [E0 vs E4 盲测](../test-results/evidence-test-blind-2026-10-03-v1/report.md)。40 个主指标 pair 两者完全相同：accuracy **20/40**、macro F1 **0.351**；FULL recall **10/20**、PARTIAL **0/3**、NONE **10/17**。NONE→FULL 6、NONE→PARTIAL 1、PARTIAL→FULL 1、FULL→NONE 10、PARTIAL→NONE 2；收费表格 4 个正例全部误拒。F03 跨 chunk 诊断为 1/2：合并正例正确，单 chunk 部分证据误放行。
- [逐 pair 失败分析](../test-results/evidence-test-blind-2026-10-03-v1/failure-analysis.md)记录关系绑定、表格行列绑定、部分支持、范围、顺序和条件边界等表现；E4 42 个 pair 全部走 `NORMALIZED_PRODUCTION_ASSESSMENT`，无可观察新增规则收益。matcher 未显式输出表格值、数值范围或极性，值级准确率为 `NOT_OBSERVABLE`。此为给定证据的 matcher 试验，未测检索/生成或用户使用。**不迁移 E4**，也不据本 TEST 修改 matcher、gold 或建立 E5；继续研究需在 DEV 中处理并另建独立 TEST。
- 本轮新增/修改仅 `benchmarks/evidence_annotation_v2/`、评测文档与本地 ignored 结果；生产 parser、chunker、matcher、embedding、用户索引和服务未因本实验改动。无需构建、重启或重建索引；阶段 A 未退出。

## 2026-10-04：E4 方向收尾、硬否决生成对照与实验总报告

- [固定证据生成对照](../test-results/evidence-gate-ablation-2026-10-04-v1/report.md)在 TEST_FROZEN v1 的 21 题、42 个正负 evidence unit 上比较 E0 式 `hard_veto` 与只作可错提示的 `advisory`。完整原文、query、DeepSeek Flash 和基本来源约束相同；未把 gold 放入模型。20 道单 chunk 题 40 pair 的 agent 严格答案评分为 **26/40 vs 40/40**；FULL **9/20 vs 20/20**、PARTIAL **1/3 vs 3/3**、NONE **16/17 vs 17/17**。硬门槛直接误拒 10 个 FULL 和 2 个 PARTIAL；P06 输出自相矛盾，P01 负例带错范围附带断言。F03 跨 chunk 诊断为 1/2 vs 2/2，硬门槛路径将 99000 元错归非全日制 MBA。两项 advisory 答案评分为中等把握，保守扣除仍为 38/40。两组模型调用分别 20/42 次，记录模型调用耗时合计 19.507/38.012 秒；无服务端 token usage。
- 输出与评分见 `responses.jsonl`、`review-annotations.json`、`metrics.json` 和 SHA manifests。**诊断而非独立迁移验收**：同一 TEST v1 已被观察，评分由 agent 完成，每路径单次采样，仅固定 evidence unit，无真实混合检索或空证据。结论是结束 E4 规则优化；生产硬否决的降权／取消值得在新独立中文资料中验证，当前不改生产 `assess_evidence()`、索引或服务。
- 根据用户确认的大纲完成[内部技术决策版实验总报告](evaluations/2026-10-04-rag-experiments-decision-report.md)，覆盖基础问答、政策回归、PDF/parser/公式、结构切分、Hybrid 与生产消融、选证、matcher、冻结 TEST 和硬否决诊断。报告逐节区分分母、DEV/TEST、候选／送答／答案与实际用户验收。benchmarks 相关测试 **24 passed**；评分重算、39 个报告链接、冻结 TEST/E0/E4 哈希及 `git diff --check` 已核对。本轮无生产构建、重启或重建索引要求，阶段 A 未退出。
