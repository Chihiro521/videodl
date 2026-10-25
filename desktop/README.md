# VideoDL Desktop

Windows 桌面版，用于批量保存视频封面、独立音频和视频。界面基于 PySide6，下载内核来自 [CharlesPikachu/videodl](https://github.com/CharlesPikachu/videodl)。

![桌面下载工作台](assets/screenshot.png)

## 下载与使用

1. 在 [GitHub Releases](https://github.com/Chihiro521/videodl/releases) 选择 `desktop-v` 开头的发行版，下载 `VideoDL-Desktop-版本-windows-x64.zip`。
2. 完整解压 ZIP，然后双击文件夹里的 `VideoDL Desktop.exe`。保留同目录下的 `_internal` 文件夹。
3. 在“链接下载”粘贴一个或多个链接，每行一个，也支持直接粘贴分享文本。点击“提取链接”或按 `Ctrl+Enter`，每条链接的可用内容会陆续出现在下方列表。
4. 视频、音频和封面分别列成独立行。可以搜索标题、按类型筛选，点击行末下载按钮单独下载，或勾选后点击“下载选中”；“全部下载”处理当前筛选范围中的未完成内容。
5. 保存路径始终显示在窗口底部，可随时更改。下载状态会直接显示在结果行中，完成后的文件夹按钮可打开文件所在位置。
6. “下载队列”保留详细进度、暂停、取消、重试和历史记录。首页也可开启“提取后自动下载”，自动下载的内容在“设置”中选择。

发行包内提供 Python 运行环境、FFmpeg、ffprobe 和 Node.js 运行时，适用于 Windows 10/11 x64。部分上游解析器还依赖浏览器或其他外部工具，其可用范围以具体解析结果为准。

## 音频、画质与队列

- 音频优先使用解析器提供的独立音轨；没有独立音轨时先取得媒体，再使用 `-c:a copy` 提取，保留原始编码。AAC 一般保存为 `.m4a`，其他编码使用匹配的容器。
- 视频使用上游解析器选出的流。当前上游没有统一的画质枚举接口，界面显示真实返回的格式。
- 提取默认同时处理 2 个链接，可在设置中调整为 1–3 个。失败链接会集中列出，可重试；停止提取会保留已取得的结果。
- 同一条目的视频、音频、封面可一起选择，合并到同一下载任务，避免重复下载媒体。某项失败时，已成功的行仍显示完成。
- 多分P会逐个列出，下载时按条目标识重新匹配；如果内容发生变化，界面会提示重新提取。
- 默认同时处理 1 个下载任务，可调整为 1–3 个。“暂停队列”暂停启动后续任务，正在处理的任务继续运行。
- 取消会停止任务的后台进程及媒体工具。重新启动程序后，可点击“重试未完成”重新解析和下载。重试从头下载，同名文件自动增加编号。
- 输出按标题存放在所选文件夹中。临时下载使用所选磁盘，正常结束时自动清理。
- “清空提取结果”和“从列表移除此项”只移除结果记录，下载任务和文件保留。“清理记录”只清理已经结束的任务记录。

## 本地记录

设置、结果列表和队列保存在 `%LOCALAPPDATA%\VideoDL Desktop`，包含用户输入的来源链接、内容标题、文件路径和任务状态。解析器返回的临时下载地址与原始响应均不写入这些记录。旧版设置和下载记录可以继续使用。

## 更新

“关于与更新”检查 `Chihiro521/videodl` 中以 `desktop-v` 开头的正式发行版，并展示原作者的最新提交。下载新版、解压到新目录后运行，设置和历史记录会继续使用同一份本地数据。

上游源码更新通过同步 PR、兼容测试和适配后，再发布桌面版。桌面程序检查发行版，不直接修改正在运行的源码。

## 从源码运行

```powershell
git clone --branch desktop https://github.com/Chihiro521/videodl.git
cd videodl
uv venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -r desktop/requirements.lock
```

安装依赖后双击仓库根目录的 `启动桌面版.vbs`。开发时也可运行：

```powershell
.\.venv\Scripts\python.exe -m desktop
```

源码运行的媒体处理依赖系统里的 FFmpeg 和 ffprobe，发行包中则提供对应工具。

## 构建、测试与发布

```powershell
uv pip install --python .venv/Scripts/python.exe -r desktop/requirements.lock pyinstaller==6.22.3 pytest==9.1.1
.\.venv\Scripts\python.exe -m pytest desktop/tests -q
.\.venv\Scripts\python.exe -m desktop.build
```

输出位于 `dist/desktop/`，包含便携文件夹、ZIP 和 `SHA256SUMS.txt`。构建需要 Git、网络和全新输出目录。FFmpeg 使用 `media-tools.json` 中固定的下载地址与 SHA-256；Python 依赖固定在 `requirements.lock`。

构建只收录所需的源码和资源，生成独立的发行用上游副本，清除源码内置的 Cookie、服务 token 和密钥默认值；相关解析器的可用性仍需单独验证。构建不会修改工作区的上游源码。发行包不包含 `.wvd` 身份文件、本机配置、日志和历史下载。`public-build-audit.json` 记录处理的字段名，`build-info.json` 记录构建版本，`THIRD-PARTY-NOTICES.txt` 保留依赖说明与来源。

推送 `desktop-v0.2.0` 等版本标签会触发 Windows 测试和打包，并创建 GitHub 草稿发行版。验证草稿附件后发布。具体分支操作见 [MAINTAINING.md](MAINTAINING.md)。

## 验证范围

自动测试使用本地 HTTP 服务提供的真实小型媒体，覆盖批量提取、类型筛选、勾选下载、自动下载偏好、结果恢复、条目重新匹配、三种输出、原始音频数据一致性、同名文件、部分失败、队列恢复和取消。打包版本在精简 PATH 下验证窗口启动、后台下载以及“提取→选择→下载”的完整 GUI 流程。

平台解析能力继承自上游；各平台网站变化、登录状态和外部接口可用性都会影响结果。具体平台实测结果记录在每个发行版说明中。
