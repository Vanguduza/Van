# Compile source on a disposable Windows runner. Never load an EA or log in.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$workspace = (Get-Location).Path
$owned = Join-Path $env:RUNNER_TEMP ('van-mql-' + [guid]::NewGuid().ToString('N'))
$report = Join-Path $workspace 'mql-native-source-report'
New-Item -ItemType Directory -Path $owned,$report -Force | Out-Null
$receipt = [ordered]@{
    schema = 'van.mql-native-source/1'
    source_head = (& git rev-parse HEAD).Trim()
    source_sha256 = (Get-FileHash 'deploy/van-trading-core/mql5/VanBridgeEA.mq5' -Algorithm SHA256).Hash.ToLowerInvariant()
    phase = 'PREPARING_COMPILER'
    qualification = 'Source compilation only; no terminal account, broker order, deployed EA, financial or handset acceptance.'
    compile_cases = @()
}
function Assert-Publisher([string]$Path) {
    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch '(?i)(?:CN|O)="?MetaQuotes (?:Ltd\.?|Software Corp\.?)"?(?:,|$)') {
        throw 'Official MetaQuotes Authenticode signature is required before execution'
    }
    return [ordered]@{status=[string]$signature.Status; subject=$signature.SignerCertificate.Subject; thumbprint=$signature.SignerCertificate.Thumbprint}
}
function Read-Compile([string]$Compiler,[string]$Include,[string]$Source,[bool]$ExpectSuccess) {
    $binary = [IO.Path]::ChangeExtension($Source, '.ex5')
    $log = [IO.Path]::ChangeExtension($Source, '.log')
    if ((Test-Path -LiteralPath $binary) -or (Test-Path -LiteralPath $log)) { throw 'Compilation requires a fresh source directory' }
    $started = [DateTime]::UtcNow
    $process = Start-Process -FilePath $Compiler -ArgumentList @('/portable',('/compile:"{0}"' -f $Source),('/include:"{0}"' -f $Include),'/log') -PassThru
    if (-not $process.WaitForExit(180000)) { $process.Kill(); throw 'MetaEditor source compilation timed out' }
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    while (-not (Test-Path -LiteralPath $log) -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 200 }
    if (-not (Test-Path -LiteralPath $log)) { throw 'MetaEditor produced no fresh native compiler log' }
    $text = [IO.File]::ReadAllText($log)
    $match = [regex]::Match($text, '(?im)^\s*Result:\s*(\d+) errors?,\s*(\d+) warnings?')
    if (-not $match.Success) { throw 'Native compiler result counts are unreadable' }
    $errors = [int]$match.Groups[1].Value
    $warnings = [int]$match.Groups[2].Value
    $hasBinary = (Test-Path -LiteralPath $binary) -and (Get-Item -LiteralPath $binary).Length -gt 0
    $name = [IO.Path]::GetFileNameWithoutExtension($Source)
    Copy-Item -LiteralPath $log -Destination (Join-Path $report ($name + '.log'))
    $case = [ordered]@{name=$name; expected_success=$ExpectSuccess; process_exit_code=$process.ExitCode; errors=$errors; warnings=$warnings; fresh_binary=$hasBinary; started_at_utc=$started.ToString('o'); finished_at_utc=[DateTime]::UtcNow.ToString('o'); log_sha256=(Get-FileHash $log -Algorithm SHA256).Hash.ToLowerInvariant()}
    if ($hasBinary) {
        $case.binary_sha256 = (Get-FileHash $binary -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($ExpectSuccess) { Copy-Item -LiteralPath $binary -Destination (Join-Path $report 'VanBridgeEA.ex5') }
    }
    $script:receipt.compile_cases += $case
    if ($ExpectSuccess -and ($errors -ne 0 -or -not $hasBinary)) { throw 'VAN EA did not produce a fresh zero-error native binary' }
    if (-not $ExpectSuccess -and ($errors -le 0 -or $hasBinary)) { throw 'The native compiler failed to reject deliberately invalid source' }
}
try {
    $page = Invoke-WebRequest -Uri 'https://www.metatrader5.com/en/download' -TimeoutSec 90
    $links = [regex]::Matches($page.Content, 'https://[^"<>\s]+/mt5setup\.exe(?:\?[^"<>\s]*)?')
    if ($links.Count -eq 0) { throw 'The official download page exposes no MT5 SDK installer' }
    $url = [Net.WebUtility]::HtmlDecode([Net.WebUtility]::HtmlDecode($links[0].Value))
    $uri = [uri]$url
    if ($uri.Scheme -ne 'https' -or $uri.Host -notin @('download.terminal.free','download.mql5.com') -or $uri.AbsolutePath -notmatch '/metaquotes\.(ltd|software\.corp)/mt5/mt5setup\.exe$') { throw 'Official installer location is outside the admitted MetaQuotes download endpoints' }
    $installer = Join-Path $owned 'mt5setup.exe'
    Invoke-WebRequest -Uri $uri -OutFile $installer -TimeoutSec 90
    $receipt.installer_url = $url
    $receipt.installer_sha256 = (Get-FileHash $installer -Algorithm SHA256).Hash.ToLowerInvariant()
    $receipt.installer_signature = Assert-Publisher $installer
    $install = Join-Path $owned 'sdk'
    $setup = Start-Process -FilePath $installer -ArgumentList @('/auto',('/path:"{0}"' -f $install)) -PassThru
    $candidates = @((Join-Path $install 'metaeditor64.exe'),(Join-Path ${env:ProgramFiles} 'MetaTrader 5\metaeditor64.exe'))
    $deadline = [DateTime]::UtcNow.AddMinutes(8)
    $compiler = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        foreach ($candidate in $candidates) {
            if ((Test-Path -LiteralPath $candidate) -and (Test-Path -LiteralPath (Join-Path (Split-Path $candidate) 'MQL5\Include\Trade\Trade.mqh'))) { $compiler=$candidate; break }
        }
        if ($null -ne $compiler -and $setup.HasExited) { break }
        Start-Sleep -Seconds 1
    }
    Get-Process terminal,terminal64 -ErrorAction SilentlyContinue | Stop-Process -Force
    if (-not $setup.HasExited) { $setup.Kill(); $setup.WaitForExit(10000) | Out-Null }
    if ($null -eq $compiler) { throw 'The official SDK installer did not supply MetaEditor and the native standard library' }
    $receipt.compiler_signature = Assert-Publisher $compiler
    $receipt.compiler_sha256 = (Get-FileHash $compiler -Algorithm SHA256).Hash.ToLowerInvariant()
    $receipt.compiler_file_version = (Get-Item $compiler).VersionInfo.FileVersion
    $include = Join-Path (Split-Path $compiler) 'MQL5'
    $sourceDir = Join-Path $owned 'source'
    New-Item -ItemType Directory -Path $sourceDir | Out-Null
    $source = Join-Path $sourceDir 'VanBridgeEA.mq5'
    Copy-Item -LiteralPath 'deploy/van-trading-core/mql5/VanBridgeEA.mq5' -Destination $source
    if ((Get-FileHash $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $receipt.source_sha256) { throw 'Compiler source copy is not byte-identical to the checkout' }
    $negative = Join-Path $sourceDir 'VanCompilerRejectionProbe.mq5'
    [IO.File]::WriteAllText($negative, "#property strict`nvoid OnTick() { this_is_deliberately_invalid_native_source( ; }`n")
    $receipt.phase = 'COMPILING_SOURCE'
    Read-Compile $compiler $include $negative $false
    Read-Compile $compiler $include $source $true
    $receipt.phase = 'SOURCE_COMPILED'
} catch {
    $receipt.failure = $_.Exception.Message
    throw
} finally {
    Get-Process terminal,terminal64,metaeditor,metaeditor64 -ErrorAction SilentlyContinue | Stop-Process -Force
    $receipt.finished_at_utc = [DateTime]::UtcNow.ToString('o')
    $receipt | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $report 'receipt.json') -Encoding utf8
}
