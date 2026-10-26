# VideoDL Desktop 0.4.1

本版将桌面运行依赖 cryptography 升级到 50.0.2，处理 GHSA-537c-gmf6-5ccf、GHSA-g6cj-pr64-35w5、GHSA-jwv3-5hgf-82ww 等告警。桌面依赖覆盖单独维护，上游源码及原始依赖声明保持原样。

- 上游每天检查更新，有源码变化时创建同步草稿 PR，忽略自动生成的测试报告和示例视频。
- PR 自动执行 Python、JavaScript/TypeScript、Actions 的 CodeQL、依赖审查、同步边界检查和 Windows 功能测试。
- 自动同步保留桌面维护文件，合并冲突会阻止后续执行；已有同步 PR 保留人工修改。
- 支持从 Actions 手动生成便携包和发行草稿。构建与发行权限分开，发行前复核源码版本、提交号及 ZIP 校验值。

下载 `VideoDL-Desktop-0.4.1-windows-x64.zip`，完整解压后双击 `VideoDL Desktop.exe`，保留同目录下的 `_internal` 文件夹。

Python、FFmpeg、ffprobe 和 Node.js 随包提供。自动化维护说明见源码中的 `desktop/AUTOMATION.md`。
