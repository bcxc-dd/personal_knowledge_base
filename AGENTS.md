# Project Rules

## 项目方向与会话接续

开始工作前阅读 `docs/project-roadmap.md` 与 `docs/mvp-progress.md`，随后检查当前分支、提交及工作区。路线图是项目方向与当前阶段的入口；用户最新明确指示优先，实际完成状态以代码和验证证据为准。

- 真实个人使用价值、功能效果与基本体验优先，简历和面试作为附加收益。
- 按路线图完成整体闭环；注册、多租户、复杂权限暂不纳入主线。
- 没有具体问题和验证证据前，不主动引入 BM25、HyDE 等检索增强。
- 区分已实现、自动测试通过、真实资料验证通过、用户使用验证通过；不把历史计划或单题通过当成整体完成。
- 关键交付后同步路线图状态与执行记录，注明证据、未解决项、下一步及构建/重启要求。涉及运行行为时核对实际服务版本。

## React Router

1. `src/app.tsx` 只用于路由配置，不写页面业务逻辑。
2. 路由配置使用 config 进行配置。

## 页面目录规则

1. 所有页面放在 `src/pages` 下。
2. 一个页面对应一个文件夹：`src/pages/<PageName>/`。
3. 页面目录固定包含：
   - `index.tsx`：页面入口组件
   - `hooks/`：页面级 hooks（如 `useHome.ts`）
   - `style/`：页面级样式（如 `index.module.scss`）
   - `components/`：页面内组件

## 页面内组件目录规则

1. 每个组件必须是独立文件夹：`src/pages/<PageName>/components/<ComponentName>/`。
2. 每个组件目录固定包含：
   - `index.tsx`：组件入口
   - `hooks/`：组件内部 hooks（如 `useHeader.ts`）
   - `style/`：组件内部样式（如 `index.module.scss`）
