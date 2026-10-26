# 桌面版自动化维护

`desktop` 是桌面版默认及发行分支，`master` 保留上游原始版本。定时工作流从默认分支运行。

## 每天同步上游

GitHub Actions → **Desktop upstream sync** 每天运行一次，也可点击 **Run workflow** 手动检查。

1. 获取原作者 `CharlesPikachu/videodl` 的 `master`，比较完整提交号；没有更新就结束。
2. 有更新时创建 `codex/sync-upstream-提交号` 草稿 PR，目标为 `desktop`。
3. 同步进程只做 Git 操作和 AST 静态版本读取，保持 `.github/`、`desktop/`、桌面依赖及维护脚本的既有版本。未引入的上游维护文件会列在 PR 中。
4. 自动启动代码扫描、依赖审查、边界检查及 Windows 功能测试。使用仓库短期令牌，不需要个人 Token。
5. 有冲突时，PR 只记录 `desktop/upstream-pending.json`，边界检查会失败并停止后续功能测试。修复实际合并、更新上游记录并删除该文件后，检查才能继续。
6. 已有待处理的同步 PR 时不覆盖分支；同一上游提交已关闭的 PR 不会每天重建，等待新的上游提交。
7. 阅读变更与扫描结果，将草稿标为可审查，再人工确认合入。若需修改桌面适配层，先通过独立适配 PR 更新 `desktop`，再更新同步分支。

扫描覆盖 Python、JavaScript/TypeScript、GitHub Actions。Dependency review 拦截新引入的高危、严重依赖漏洞；CodeQL 合并规则拦截新引入的高危、严重报告。扫描不替代对下载地址、命令执行、安装脚本和依赖变更的审查。

扫描与测试任务不带个人账号、B站登录或发行写入凭据。同步任务和发行草稿任务分别获得所需写权限。第三方 Action 固定到完整提交号。

GitHub 定时任务不保证精确到分钟；公开仓库长期无活动时可能暂停定时任务，可在 Actions 重新启用。

## 生成新版便携包

1. 通过 PR 更新 `desktop/__init__.py` 的版本号和 `desktop/RELEASE_NOTES.md`，合入 `desktop`。
2. Actions → **Desktop release** → **Run workflow**，分支选择 `desktop`。版本可留空，或填写与源码一致的 `X.Y.Z`。
3. 保持 **create_draft** 开启。云端 Windows 自动运行源码测试、构建 exe、测试 exe，再上传 ZIP、SHA-256 和构建记录。
4. 独立发行任务复核版本、提交号和 ZIP 校验值，创建对应 `desktop-vX.Y.Z` 标签及草稿发行版。已有发行记录不会被覆盖。
5. 在 Releases 检查草稿和附件，实际试用后点击 **Publish release**。

关闭 **create_draft** 时只生成 Actions 附件，不创建标签或发行记录。验证附件保留 7 天，正式 Release 附件长期保留。手动推送 `desktop-vX.Y.Z` 标签仍会运行相同流程；标签提交必须已合入 `desktop`。

## 仓库开关与规则

- 默认分支为 `desktop`。
- Actions 默认权限保留只读；允许 Actions 创建 PR。同步工作流单独申请 `contents`、`pull-requests`、`actions` 写权限。
- 启用依赖图和 Dependabot 漏洞提醒，保留已有密钥扫描和推送拦截。
- `desktop` 必须通过 PR 合入，并通过 Automation guard、Desktop tests、Dependency review 和三个 CodeQL 检查；CodeQL 高危、严重新增报告阻止合并。
- 本项目由个人维护，人工点击合入作为确认步骤，不要求第二个账号审批自己的功能 PR。同步机器人不执行合并或正式发布。
- 新增上游工作流及桌面维护文件在同步中保留当前版本，需要时另开功能 PR 审查迁移。

## 本机手动同步

保存修改并切换到 `desktop` 后运行 `scripts/sync-desktop.ps1`，只准备分支，不执行新增上游代码。审查完成后再运行测试。

`scripts/sync-desktop.ps1 -PublishPR` 可创建草稿 PR 并启动云端检查，需要 GitHub CLI 已登录。已有 PR 会被保留。
