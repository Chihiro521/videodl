# 维护这个项目

仓库是项目的完整文件和历史；分支是同一个仓库中的不同开发路线；PR 是把一个分支的改动交给另一个分支检查、合并的记录。

## 分支分工

| 名称 | 作用 |
| --- | --- |
| `upstream/master` | 原作者 `CharlesPikachu/videodl` 的跟踪引用 |
| `origin/master` | 你的 Fork 中同步上游的原始版本 |
| `desktop` | 桌面版长期维护和发布分支 |
| `codex/功能名称` | 实现一个功能或一次修复，完成后通过 PR 合入 `desktop` |
| `desktop-v0.1.0` | 指向一次发行的固定标签 |

`upstream` 和 `origin` 是远程仓库的简称，不是额外复制一份本地项目。它们分别指向原作者和你的仓库。

## 平时开发

1. 从 `desktop` 创建一个 `codex/` 开头的功能分支。
2. 修改 `desktop/` 中的界面、队列和适配代码，尽量保持 `videodl/` 的原始代码。
3. 运行测试，在窗口里验证实际行为。
4. 提交、推送功能分支，创建指向 `desktop` 的 PR。
5. 检查通过后合并。发布时从 `desktop` 打标签。

修改任务只包含相关文件。`edit/`、`videodl_outputs/`、本机运行目录和构建产物属于本地内容。

## 桌面代码分工

| 文件 | 负责内容 |
| --- | --- |
| `app.py`、`pages.py`、`theme.py` | 程序入口、页面布局、视觉样式 |
| `extraction.py` | 多链接提取、停止、失败重试 |
| `results.py`、`resultview.py` | 结果数据、筛选、选择、逐行操作 |
| `downloads.py`、`process.py` | 下载队列与后台进程 |
| `adapter.py` | 上游接口适配、条目标识、媒体输出 |
| `media.py`、`parsing.py` | 统一媒体与画质描述、平台解析及元数据补齐 |
| `pool.py`、`session.py`、`jobobject.py` | 常驻隔离进程、内存缓存、Windows 子进程生命周期 |

改界面主要编辑页面和样式；上游接口变化集中调整适配层。

画质描述通过 `public_formats` 去除临时下载地址，再交给界面及本地记录。原始 `VideoInfo`、流对象和地址仅保留在后台进程内。结果与任务通过 `identity_version=2`、`item_key` 和 `format_ids` 关联，旧记录在首次下载时自动补齐。新增来源适配应返回同一套描述，避免向页面加入平台分支。

## 同步上游

先保存本地修改，并切换到 `desktop`，然后运行：

```powershell
.\scripts\sync-desktop.ps1
```

脚本获取 `upstream/master`，检查是否有新提交，创建 `codex/sync-upstream-时间` 分支并合并，再运行桌面测试。遇到冲突时，保留现场供修复；脚本不会自动舍弃任一方修改。

本地验证通过后，可用同一脚本的 `-PublishPR` 参数创建同步 PR。该参数只在本次脚本创建了更新分支且测试成功时生效：

```powershell
.\scripts\sync-desktop.ps1 -PublishPR
```

合并后检查：

- 解析器注册表及 `VideoInfo` 字段是否变化。
- 解析结果、下载结果和文件路径是否仍与适配层契合。
- 封面、独立音轨、媒体音轨提取、合并是否正常。
- 新增解析器所需的模块、资源和工具是否被打包。
- 发行副本的默认凭据清理与文件清单是否覆盖新增内容。

`master` 可以通过 GitHub 的 Sync fork 功能同步原作者。桌面改动维护在 `desktop`，每次桌面发行记录其对应的上游提交。

## 发布新版本

1. 在功能分支修改 `desktop/__init__.py` 的版本号，更新使用说明与发行说明，通过 PR 合入 `desktop`。
2. 对确认的提交打标签并推送，例如 `desktop-v0.1.1`。标签版本须与代码版本一致。
3. `desktop-release.yml` 在 Windows 中安装固定依赖、测试、构建便携包，再使用打包 exe 验证下载流程。
4. 工作流生成 GitHub 草稿发行版，包含 ZIP、校验值和构建信息。
5. 检查附件、平台实测记录和更新说明，然后发布草稿。

每个版本保留旧附件和标签。用户可下载旧版本，设置与下载内容继续存放在各自原目录。
