param([int]$Index = 0, [string]$DataRoot = '', [string]$RuntimeRoot = '')

[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$ErrorActionPreference = 'Continue'
$hadFailures = $false
if (-not $RuntimeRoot) { $RuntimeRoot = Split-Path -Parent $PSScriptRoot }
if (-not $DataRoot) {
    $pointer = Join-Path $RuntimeRoot 'tools\storage.local.json'
    if (Test-Path -LiteralPath $pointer) {
        $DataRoot = (Get-Content -LiteralPath $pointer -Raw -Encoding UTF8 | ConvertFrom-Json).data_root
        if (-not (Test-Path -LiteralPath (Join-Path $DataRoot '_推文归档\tweets.sqlite'))) { throw '资料库磁盘不可用，请在软件中重新选择资料库。' }
    } else { $DataRoot = $RuntimeRoot }
}
$ROOT = $DataRoot
$GD = Join-Path $RuntimeRoot 'gallery-dl.cmd'
$PY = Join-Path $RuntimeRoot 'python\python.exe'
$COOKIES = Join-Path $RuntimeRoot 'cookies.txt'
if (-not (Test-Path -LiteralPath $COOKIES)) { Write-Host '请先运行刷新登录态.cmd，或在设置中导入登录文件。'; exit 1 }
$accounts = Get-Content (Join-Path $ROOT 'tools\accounts.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$capturePath = Join-Path $ROOT 'tools\archive.local.json'
$postTypes = @('original','quote','retweet','reference')
$includeReplies = $false
if (Test-Path -LiteralPath $capturePath) {
    $capture = Get-Content -LiteralPath $capturePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($capture.post_types) { $postTypes = @($capture.post_types) }
    $includeReplies = [bool]$capture.include_replies
}
$clauses = @()
foreach ($postType in $postTypes) {
    switch ($postType) {
        'original' { $clauses += '(not retweet_id and not quote_id and not quoted_id)' }
        'quote' { $clauses += '(not retweet_id and not quote_id and quoted_id)' }
        'retweet' { $clauses += '(retweet_id)' }
        'reference' { $clauses += '(not retweet_id and quote_id)' }
    }
}
if ($clauses.Count -eq 0) { throw '归档内容类型无效，请在软件设置中重新保存。' }
$typeFilter = '(' + ($clauses -join ' or ') + ')'
if (-not $includeReplies) { $typeFilter += ' and not reply_id' }
$replyValue = if ($includeReplies) { 'true' } else { 'false' }

if ($Index -eq 0) {
    Write-Host ''
    Write-Host '可补新的账号：' -ForegroundColor Cyan
    for ($i = 0; $i -lt $accounts.Count; $i++) {
        Write-Host ('  [{0}] {1}  {2}' -f ($i + 1), $accounts[$i].name, $accounts[$i].handle)
    }
    Write-Host '  [0] 全部'
    $pick = Read-Host '输入编号'
    $tmp = 0
    if (-not [int]::TryParse($pick, [ref]$tmp)) { Write-Host '编号无效'; exit 1 }
    $Index = $tmp
}

if ($Index -lt 0 -or $Index -gt $accounts.Count) { Write-Host '编号超出范围'; exit 1 }

$targets = if ($Index -eq 0) { @($accounts) } else { @($accounts[$Index - 1]) }

foreach ($acc in $targets) {
    $timeline = 'https://x.com/' + $acc.handle.TrimStart('@') + '/timeline'
    $folder = Join-Path $ROOT $acc.folder
    $archive = Join-Path $folder 'archive.sqlite'
    $archiveVideo = Join-Path $folder 'archive_video.sqlite'
    New-Item -ItemType Directory -Force $folder | Out-Null

    Write-Host ''
    Write-Host ('==== {0}  {1} ====' -f $acc.name, $acc.handle) -ForegroundColor Green

    Write-Host '[正文] 同步账号正文（含已启用的纯文字） ...'
    $accountIndex = [array]::IndexOf(@($accounts), $acc) + 1
    & $PY (Join-Path $RuntimeRoot 'tools\tweet_archive.py') --root $ROOT --runtime-root $RuntimeRoot --index $accountIndex --sync-text-only --no-translate
    if ($LASTEXITCODE -ne 0) { $hadFailures = $true; Write-Host '部分正文未取得；已保存内容保留，继续尝试下载媒体。' -ForegroundColor Yellow }


    Write-Host '[0/4] 检查登录态 ...'
    $check = (& $GD -C $COOKIES -s --range 1 $timeline 2>&1 | Out-String)
    if ($check -match 'AuthRequired') {
        Write-Host '  登录态已失效，请先双击「刷新登录态.cmd」' -ForegroundColor Red
        exit 1
    }
    Write-Host '  OK'

    Write-Host '[1/4] 下载新图片（包含原创、引用和转推）...'
    & $GD -C $COOKIES -o extractor.twitter.videos=false -o extractor.twitter.quoted=true -o extractor.twitter.retweets=true -o "extractor.twitter.replies=$replyValue" -D $folder --download-archive $archive --filter $typeFilter $timeline
    if ($LASTEXITCODE -ne 0) { $hadFailures = $true; Write-Host '图片下载未全部完成；已下载的文件保留。' -ForegroundColor Yellow }

    Write-Host '[2/4] 下载新视频 / GIF ...'
    & $GD -C $COOKIES -o extractor.twitter.videos=true -o extractor.twitter.quoted=true -o extractor.twitter.retweets=true -o "extractor.twitter.replies=$replyValue" -o downloader.rate=8M -D (Join-Path $folder '视频GIF') --filter "($typeFilter) and extension in ('mp4','gif','m4v','webm')" --download-archive $archiveVideo $timeline
    if ($LASTEXITCODE -ne 0) { $hadFailures = $true; Write-Host '视频下载未全部完成；已下载的文件保留。' -ForegroundColor Yellow }

    Write-Host '[3/4] 按年月归档 ...'
    & $PY (Join-Path $RuntimeRoot 'tools\archive_months.py') $folder
    if ($LASTEXITCODE -ne 0) { $hadFailures = $true }

    Write-Host '[4/4] 重新生成总缩略图 ...'
    & $PY (Join-Path $RuntimeRoot '_setup\gen_sheet.py') $folder $acc.handle $acc.name
    if ($LASTEXITCODE -ne 0) { $hadFailures = $true }

    Write-Host ('完成：' + $folder) -ForegroundColor Green
}
Write-Host ''
Write-Host '[推文归档] 获取本地媒体对应的推文、区分原创/引用/转推，并补充缺少的中文译文 ...' -ForegroundColor Cyan
& $PY (Join-Path $RuntimeRoot 'tools\tweet_archive.py') --root $ROOT --runtime-root $RuntimeRoot --index $Index --media-only
if ($LASTEXITCODE -ne 0) {
    Write-Host '推文抓取或翻译未全部完成，已成功保存的内容保留；请查看上方提示。' -ForegroundColor Yellow
    exit 1
}
Write-Host '推文归档已保存；双击「推文归档.html」阅读。' -ForegroundColor Green
if ($hadFailures) { Write-Host '部分步骤未完成，请查看任务日志后重试补新。' -ForegroundColor Yellow; exit 1 }
exit 0
