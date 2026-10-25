param(
    [switch]$PublishPR,
    [string]$Python = '.venv\Scripts\python.exe'
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if ((git branch --show-current) -ne 'desktop') { throw '请先切换到 desktop 分支，再同步上游。' }
if (git status --porcelain --untracked-files=no) { throw '请先保存已跟踪文件的修改。' }
git fetch upstream master
if ($LASTEXITCODE -ne 0) { throw '获取上游失败。' }
git merge-base --is-ancestor upstream/master HEAD
if ($LASTEXITCODE -eq 0) { Write-Output '已经包含当前上游的全部提交。'; exit 0 }
$syncBranch = 'codex/sync-upstream-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
git switch -c $syncBranch
if ($LASTEXITCODE -ne 0) { throw '创建同步分支失败。' }
git merge --no-edit upstream/master
if ($LASTEXITCODE -ne 0) { throw '合并存在冲突，现场已保留。修复后再测试和提交。' }
$upstreamRevision = git rev-parse upstream/master
$coreVersion = & $Python -c 'from videodl import __version__; print(__version__)'
if ($LASTEXITCODE -ne 0) { throw '无法读取上游版本，请检查 Python 环境。' }
$upstreamInfo = [ordered]@{core_version=$coreVersion;upstream_revision=$upstreamRevision;repository='CharlesPikachu/videodl'}
$upstreamInfo | ConvertTo-Json | Set-Content -LiteralPath 'desktop/upstream.json' -Encoding utf8NoBOM
& $Python -m pytest desktop/tests -q
if ($LASTEXITCODE -ne 0) { throw '桌面适配测试未通过，请在当前同步分支修复。' }
git add -- desktop/upstream.json
git commit -m 'desktop: record adapted upstream revision'
if ($LASTEXITCODE -ne 0) { throw '记录上游版本失败。' }
if ($PublishPR) {
    git push -u origin $syncBranch
    if ($LASTEXITCODE -ne 0) { throw '推送同步分支失败。' }
    $bodyPath = Join-Path ([System.IO.Path]::GetTempPath()) ('videodl-sync-' + [guid]::NewGuid().ToString('N') + '.md')
    [System.IO.File]::WriteAllText($bodyPath, "同步原作者 master 分支到桌面版，并运行上游接口、媒体输出和队列恢复测试。`n`n验证：python -m pytest desktop/tests -q", [System.Text.UTF8Encoding]::new($false))
    try { gh pr create --repo Chihiro521/videodl --base desktop --head $syncBranch --title 'desktop: 同步上游更新' --body-file $bodyPath }
    finally { [System.IO.File]::Delete($bodyPath) }
    if ($LASTEXITCODE -ne 0) { throw '创建 PR 失败，已推送分支保留。' }
}
