# PDF 公式人工校对 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户在 PDF 原页核对和修订乱码公式，并让确认后的页文本可靠地进入新索引。

**Architecture:** 继续用 `pypdf` 提取原页，把人工修订作为独立的按页覆盖层保存在 SQLite。后台处理在切片前应用覆盖层并重建该文档的 Chroma 向量；资料详情页用 PDF.js 呈现原页、框选区域、截图和文本差异。

**Tech Stack:** FastAPI、pypdf、SQLite、Chroma、Pillow、React 19、Vite、pdfjs-dist、Vitest、pytest。

**Spec:** [2026-09-29-pdf-formula-review-design.md](../specs/2026-09-29-pdf-formula-review-design.md)

## Global Constraints

- 只处理文本型 PDF；TXT、Markdown、DOCX 的解析与切分行为保持现状。
- 自动异常提示识别 `U+E000–U+F8FF` 和 `U+FFFD`；无异常的 PDF 页仍有手动入口。
- 修订是整页文本，不能为空、不能与当前索引文本相同、不能超过 100,000 字符；截图只接受真实 PNG/JPEG 且不超过 2 MB。
- 修订绑定文档内容哈希、1 起始页码和原始页文本哈希；原 PDF 不改动，截图不入向量索引。
- 前端遵守 `AGENTS.md` 页面和组件目录规则；`src/app.tsx` 只放路由 config。
- 先在隔离数据目录验证私人 PDF，不能直接改写现有知识库；用户界面核对是单独的最终验收。
- 执行前按 `superpowers:using-git-worktrees` 检查隔离环境；当前 `master` 有其他未提交改动，不覆盖它们。实现按 TDD 红→绿，每个任务只提交自己的文件。

## Review Focus

- 原页含多个异常字符但修订只改变公式：测试保存后同页其他正文仍在 chunk 中（Task 2）。
- PDF 解析库升级后原始页文本变化：测试旧修订拒绝静默套用并明确报错（Task 2）。
- 两个页面同时编辑同一页：测试旧的修订版本提交被拒绝，避免覆盖较新修订（Task 3）。
- 截图扩展名正确但字节不是真实图片：测试返回 400 且不留下文件（Task 3）。
- 重新切分后旧 chunk 数量减少：测试 Chroma 不再含该文档旧 chunk ID（Task 2）。

---

### Task 1: PDF 原页读取与异常信号

**Files:**
- Create: `backend/app/pdf_review.py`（原页读取、哈希、异常检测）
- Modify: `backend/app/main.py`（详情响应增加 PDF 可疑页和可疑 chunk 标记）
- Test: `backend/tests/test_pdf_review.py`, `backend/tests/test_api.py`

**Interfaces:**
- Produces: `read_pdf_page(path: Path, page_number: int) -> tuple[str, int]`，返回原始页文本和总页数，页码从 1 开始；`text_hash(text: str) -> str` 为 SHA-256 十六进制；`has_suspect_glyphs(text: str) -> bool`。
- Detail 响应增加 `suspicious_pages: number[]`；PDF chunk 增加 `suspected: boolean`，由当前索引文本判断。校对后的页不再显示当前乱码提示；校对接口仍可查看原始提取文本和原始异常标志。

- [ ] **Step 1: Write failing tests.** 用受控文本分别验证 `\uf03d`、`\ufffd` 和普通公式的检测结果；用受控两页 PDF 验证 `read_pdf_page(..., 1)` 的原文和总页数；第 0 页、越界页和非 PDF 请求拒绝。API 详情标记含可疑字符的 chunk/页，正常页仍可访问。
- [ ] **Step 2: Verify red.** Run: `.venv/Scripts/python -m pytest backend/tests/test_pdf_review.py backend/tests/test_api.py -q`。Expected: 新接口或字段缺失导致测试失败。
- [ ] **Step 3: Implement.** 用 `pypdf.PdfReader` 按需读取一页；沿用现有加密/页数限制；详情响应只增加轻量标记，不批量返回全书原文。非 PDF 与非法页号抛可映射为 400 的 `ValueError`。
- [ ] **Step 4: Verify green.** Run: `.venv/Scripts/python -m pytest backend/tests/test_pdf_review.py backend/tests/test_api.py -q`。Expected: 全通过。
- [ ] **Step 5: Commit.** `git add backend/app/pdf_review.py backend/app/main.py backend/tests/test_pdf_review.py backend/tests/test_api.py`，提交 `feat: flag suspicious PDF text and expose page source`。

### Task 2: 修订持久化与索引重建

**Files:**
- Modify: `backend/app/store.py`, `backend/app/engine.py`, `backend/app/pdf_review.py`
- Test: `backend/tests/test_store.py`, `backend/tests/test_rag.py`, `backend/tests/test_pdf_review.py`

**Interfaces:**
- Produces: `Store.pdf_correction(doc_id: str, page_number: int) -> dict | None`、`Store.pdf_corrections(doc_id: str) -> list[dict]`、`Store.put_pdf_correction(doc_id: str, page_number: int, source_hash: str, raw_text_hash: str, corrected_text: str, rect: list[float] | None, image_path: str | None, expected_revision: str | None) -> dict`、`Store.remove_pdf_correction(doc_id: str, page_number: int) -> dict | None`；写入与置 `queued` 在一个事务。前一方法返回新记录，后一方法返回被删除的旧记录。
- Produces: `apply_pdf_corrections(sections: list[Section], corrections: list[dict], source_hash: str) -> list[Section]`；每条修订须匹配原始页文本哈希和源文件哈希，否则抛明确信息的 `ValueError`。
- Produces: `Engine.set_pdf_correction(doc_id: str, page_number: int, source_hash: str, raw_text_hash: str, corrected_text: str, rect: list[float] | None, image_path: str | None, expected_revision: str | None) -> dict` 和 `Engine.clear_pdf_correction(doc_id: str, page_number: int) -> dict | None`；持有 `mutation_lock`，处理状态冲突报 409 所需的专用异常；成功后唤醒 worker。修订记录使用 `updated_at` 作为版本，首次提交传空值。

- [ ] **Step 1: Write failing tests.** 测试重启 Store 后修订仍在；修订整页在 `split_sections` 前生效且其他正文保留；原页哈希变化报错；保存与撤销进入 `queued`、完成后新检索命中、旧向量 ID 消失；重试保留修订，删除文档清理记录。
- [ ] **Step 2: Verify red.** Run: `.venv/Scripts/python -m pytest backend/tests/test_pdf_review.py backend/tests/test_store.py backend/tests/test_rag.py -q`。Expected: 修订方法缺失或旧索引行为不符。
- [ ] **Step 3: Implement.** 新建 `pdf_page_corrections` 表及唯一键 `(document_id, page_number)`；`process_document` 用原 PDF 解析、校验并应用覆盖层，清理该文档旧向量后切分和写入；只在成功写入所有向量后标 `ready`。删除资料时清理修订和图片；后台失败保留修订并标 `failed`。
- [ ] **Step 4: Verify green.** Run: `.venv/Scripts/python -m pytest backend/tests/test_pdf_review.py backend/tests/test_store.py backend/tests/test_rag.py -q`。Expected: 全通过。
- [ ] **Step 5: Commit.** 只暂存上述文件，提交 `feat: persist PDF page corrections across reindexing`。

### Task 3: 页校对 API 与截图安全

**Files:**
- Create: `backend/app/pdf_review_api.py`
- Modify: `backend/app/main.py`, `backend/requirements.in`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Produces: `pdf_review_router(engine: Engine) -> APIRouter`，在 `create_app` 注册；`GET /api/documents/{id}/pdf-pages/{page}` 返回 `raw_text`, `page_count`, `source_hash`, `raw_text_hash`, `suspected`, `correction`, `revision`, `has_image`。
- Produces: multipart `PUT /api/documents/{id}/pdf-pages/{page}/correction`，字段 `source_hash`, `raw_text_hash`, `corrected_text`, `expected_revision`, `rect`（可选 JSON 四个 0–1 坐标）, `image`（可选）。`GET .../correction-image` 返回已保存图片；`DELETE .../correction` 撤销。原文件端点对 PDF 返回内联 `application/pdf`。

- [ ] **Step 1: Write failing tests.** 上传受控 PDF，读取第 1 页并验证响应；提交修订后状态变 `queued`，旧 `revision` 再提交返回 409；撤销后索引恢复原文。测试页码越界、非 PDF、空白/超长修订、哈希不符、非法矩形、伪造/超 2 MB 截图、图片端点 404、删除时图片清理，以及 PDF 内联响应。
- [ ] **Step 2: Verify red.** Run: `.venv/Scripts/python -m pytest backend/tests/test_api.py -q`。Expected: 新路由和状态行为缺失。
- [ ] **Step 3: Implement.** 图片用 Pillow `verify()` 校验实际内容，在数据目录以服务端生成名写入，数据库提交失败时删除新图，成功后删除替换掉的旧图；只通过文档 ID/页码读取，绝不信任客户端路径。将 Pillow 作为直接依赖加入 `requirements.in`，现有锁文件中的固定版本需保持一致。
- [ ] **Step 4: Verify green.** Run: `.venv/Scripts/python -m pytest backend/tests/test_api.py -q`。Expected: 全通过。
- [ ] **Step 5: Commit.** 只暂存上述文件及确有更新的 `backend/requirements.txt`，提交 `feat: expose safe PDF correction API`。

### Task 4: 资料详情页的校对界面

**Files:**
- Create: `src/pages/DocumentDetail/components/PdfPageReview/index.tsx`, `hooks/usePdfPageReview.ts`, `style/index.module.scss`, `index.test.tsx`
- Modify: `src/pages/DocumentDetail/index.tsx`, `hooks/useDocumentDetail.ts`, `style/index.module.scss`, `src/services/api.ts`, `src/types/index.ts`, `package.json`, `package-lock.json`

**Interfaces:**
- `PdfPageReview` 接收 `documentId: string`, `pageNumber: number`, `onClose: () => void`, `onSaved: () => Promise<void>`；在 `src/types/index.ts` 定义 `PdfPageResponse`，字段与 Task 3 的 GET 响应一致，`correction` 为修订文本或 `null`。API service 新增 `pdfPage(id: string, page: number)`, `savePdfCorrection(id: string, page: number, form: FormData)`, `removePdfCorrection(id: string, page: number)`。
- 前端依赖固定版本 `pdfjs-dist@6.3.289`；交互测试依赖 `@testing-library/react@16.3.3`、`@testing-library/dom@10.4.2`、`jsdom@28.0.0`，均兼容本机 Node 22.14。PDF.js worker 由 Vite 本地打包，不走 CDN。

- [ ] **Step 1: Write failing interaction tests.** 用 jsdom 渲染页面并模拟 PDF.js 页面：可疑 chunk 有提示，普通 PDF chunk 仍有校对入口；原页与编辑副本并列；未确认或空文本不能提交；确认差异后传原始哈希与修订版本；保存中禁止重复提交；服务端错误和撤销有可见反馈；图片输入限制与框选归一化有测试。
- [ ] **Step 2: Verify red.** Run: `npm test -- src/pages/DocumentDetail/components/PdfPageReview/index.test.tsx`。Expected: 组件或行为缺失。
- [ ] **Step 3: Implement.** 安装固定依赖，按目录规则建立组件、hook、样式；PDF.js 只渲染所选页，使用画布上的拖拽框选记录归一化矩形，提供缩放与截图粘贴/上传预览；右侧文本差异与整页覆盖确认。保存后刷新详情，等待已有轮询显示 `ready`；旧会话引用可能仍是历史文本的提示放在校对区。
- [ ] **Step 4: Verify green.** Run: `npm test -- src/pages/DocumentDetail/components/PdfPageReview/index.test.tsx` and `npm run build`。Expected: 交互测试和 TypeScript/Vite 构建通过。
- [ ] **Step 5: Commit.** 只暂存上述前端文件，提交 `feat: add PDF page review in document detail`。

### Task 5: 全链路回归与真实 PDF 验证

**Files:**
- Modify: `docs/project-roadmap.md`, `docs/mvp-progress.md`
- Create: `docs/evaluations/2026-09-29-pdf-formula-review.md`
- Test: `backend/tests/test_pdf_review.py`, `backend/tests/test_api.py`, `backend/tests/test_rag.py`, `src/pages/DocumentDetail/components/PdfPageReview/index.test.tsx`

**Interfaces:** No new product API. Deliver evidence separating code, automated checks, isolated real-PDF result, and user interface acceptance.

- [ ] **Step 1: Run complete automated checks.** Run: `.venv/Scripts/python -m pytest backend/tests -q`, `npm test`, `npm run build`。记录测试数和任何失败，不把既有失败写成通过。
- [ ] **Step 2: Isolated sample verification.** 在独立数据目录导入本机“推免细则”PDF，不复制私人原文进仓库；确认第 9 页被标为可疑，手动提交与原页核对过的 CSP 三段公式、`x_i`、`X_i`、`m_1`，等待 `ready`，检查新 chunk、检索和引用。再撤销一次确认原始抽取与索引恢复。若模型不可用，记录实际验证边界。
- [ ] **Step 3: Browser check.** 本地启动实际版本，检查 PDF 页图、框选、截图、差异确认、保存/撤销状态与手机宽度布局；不在未确认前修改用户现有知识库。
- [ ] **Step 4: Record evidence.** 在评测记录写入代码提交、资料哈希、隔离数据路径、服务版本、测试命令/结果、修订前后片段与未解决项；同步路线图和 MVP 记录，说明后端重启及前端构建要求。
- [ ] **Step 5: Commit.** 只暂存本任务文档，提交 `docs: record PDF formula review verification`。完成前执行 `superpowers:verification-before-completion` 与 `superpowers:finishing-a-development-branch` 的收尾检查。
