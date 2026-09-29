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

## 2026-09-29：PDF 公式人工校对闭环

- [实施与隔离验收记录](evaluations/2026-09-29-pdf-formula-review.md)：PDF 可疑字符提示、原页图与整页提取文本对照、公式截图和框选、确认后修订、撤销及资料重建索引已实现；原 PDF 保持不变。功能提交已快进合并至本地 `master`（`bd2a3b5`），工作区先前未提交的 RAG 改动仍保留。
- 后端 159 passed、前端 7 passed，生产构建成功。推免细则第 9 页 CSP 公式在隔离资料库中修订后可检索，实际回答包含三段公式及第 9 页引用；页面保存与撤销后均回到 `ready`，撤销恢复原异常提示并清理截图。现有 8765 服务和用户资料库未修改；真人最终公式核对尚待用户完成。
- 使用时需重启后端、重新构建前端；现有 PDF 无需批量重建索引，提交或撤销某页时自动重建对应资料。其他公式的识别和效果仍需逐份验证，阶段 A 未完成。
