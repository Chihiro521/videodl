# VideoDL Desktop 0.5.5

- FFmpeg 和 ffprobe 更新为包含 HEVC PPS 解析修复的 LGPL shared 构建 `N-128790-g9bee1e603c`，对应 CVE-2026-125183。
- curl-cffi 更新为 0.17.0，实际内嵌 libcurl 8.23.0 和 Brotli 1.2.1，对应 CVE-2026-92392、CVE-2026-111497。
- 桌面端固定使用官方 Node.js 24.22.3。源码运行与便携包的 YouTube 辅助进程使用同一选择规则，便携包排除依赖包中的旧 Node.exe。
- FFmpeg、Node.js、yt-dlp 的官方来源和 SHA-256 固定在工具配置中，构建记录包含实际 Node.js 版本。
- 修正工具准备步骤在保留旧缓存时可能选中旧 FFmpeg 目录的问题。

33tool 旧接口适配和 #8、#9 的第三方协议告警继续列为待处理事项。ParseVideo 仍受服务端匿名调用次数限制。

下载 `VideoDL-Desktop-0.5.5-windows-x64.zip`，完整解压后运行 `VideoDL Desktop.exe`，保留 `_internal` 文件夹。新版沿用已有设置、B 站登录和下载记录。
