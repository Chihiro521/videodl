param(
    [switch]$PublishPR,
    [string]$Python = '.venv\Scripts\python.exe'
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if ((git branch --show-current) -ne 'desktop') { throw '请先切换到 desktop 分支，再同步上游。' }
if (git status --porcelain --untracked-files=no) { throw '请先保存已跟踪文件的修改。' }
$trustedHelper = Join-Path ([System.IO.Path]::GetTempPath()) ('videodl-sync-' + [guid]::NewGuid().ToString('N') + '.py')
Copy-Item -LiteralPath 'scripts/desktop_automation.py' -Destination $trustedHelper
try {
    $syncArguments = @($trustedHelper, 'sync')
    if ($PublishPR) { $syncArguments += '--publish-pr' }
    & $Python @syncArguments
    if ($LASTEXITCODE -ne 0) { throw '同步未完成，请检查当前分支和工作流记录。' }
}
finally { Remove-Item -LiteralPath $trustedHelper -ErrorAction SilentlyContinue }
