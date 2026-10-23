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
$receipt.source_blob_oid = (& git rev-parse 'HEAD:deploy/van-trading-core/mql5/VanBridgeEA.mq5').Trim()
$receipt.checkout_blob_oid = (& git hash-object --no-filters 'deploy/van-trading-core/mql5/VanBridgeEA.mq5').Trim()
function Assert-Publisher([string]$Path) {
    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch '(?i)(?:CN|O)="?MetaQuotes (?:Ltd\.?|Software Corp\.?)"?(?:,|$)') {
        throw 'Official MetaQuotes Authenticode signature is required before execution'
    }
    return [ordered]@{status=[string]$signature.Status; subject=$signature.SignerCertificate.Subject; thumbprint=$signature.SignerCertificate.Thumbprint}
}
function Read-SetupDiagnostics {
    $snapshot = [ordered]@{observed_at_utc=[DateTime]::UtcNow.ToString('o'); candidates=@(); processes=@()}
    foreach ($candidate in $script:compilerCandidates) {
        $snapshot.candidates += @{path=$candidate; exists=(Test-Path -LiteralPath $candidate)}
    }
    $snapshot.processes = @(Get-Process mt5setup,terminal,terminal64,metaeditor,metaeditor64 -ErrorAction SilentlyContinue |
        Select-Object ProcessName,MainWindowTitle,Path)
    # This disposable runner has no owner accounts or credentials. Inspect only
    # the installer window, not process environments or unrelated applications.
    try {
        Add-Type -AssemblyName UIAutomationClient
        $setupProcesses = @(Get-Process mt5setup -ErrorAction SilentlyContinue)
        foreach ($process in $setupProcesses) {
            if ($process.MainWindowHandle -eq 0) { continue }
            $window = [System.Windows.Automation.AutomationElement]::FromHandle($process.MainWindowHandle)
            $elements = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
            $snapshot.installer_controls = @($elements | ForEach-Object { $_.Current.Name } | Where-Object { $_ } | Select-Object -First 80)
        }
    } catch { $snapshot.window_diagnostic = $_.Exception.Message }
    $script:receipt.setup_diagnostic = $snapshot
    $snapshot | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $report 'setup-diagnostic.json') -Encoding utf8
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
    if ($receipt.source_blob_oid -ne $receipt.checkout_blob_oid) {
        throw 'Native compilation requires exact Git source bytes; Windows checkout line-ending conversion is not admitted'
    }
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
    if ($receipt.installer_sha256 -ne 'c8c0a73f86c58974df62fb48f8256a099d6698518cf2defc2b3f169773729e22') {
        throw 'Official SDK bootstrap changed from the prior native Windows readback; source toolchain review required'
    }
    $receipt.installer_bytes = (Get-Item $installer).Length
    $receipt.installer_signature = Assert-Publisher $installer
    $install = Join-Path $owned 'sdk'
    $setup = Start-Process -FilePath $installer -ArgumentList @('/auto',('/path:"{0}"' -f $install)) -PassThru
    $script:compilerCandidates = @((Join-Path $install 'metaeditor64.exe'),(Join-Path ${env:ProgramFiles} 'MetaTrader 5\metaeditor64.exe'))
    $deadline = [DateTime]::UtcNow.AddMinutes(8)
    $diagnoseAt = [DateTime]::UtcNow.AddSeconds(45)
    $diagnosed = $false
    $compiler = $null
    $include = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        # Standard installations separate the signed executable from their
        # per-terminal MQL5 data directory. Do not require a portable layout.
        $roots = @($install,(Join-Path ${env:ProgramFiles} 'MetaTrader 5'))
        foreach ($base in @(${env:ProgramFiles},${env:ProgramFiles(x86)},(Join-Path $env:LOCALAPPDATA 'Programs'))) {
            if (Test-Path -LiteralPath $base) {
                $roots += @(Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue |
                    Where-Object { $_.Name -match '(?i)MetaTrader|MetaQuotes' } | ForEach-Object { $_.FullName })
            }
        }
        $script:compilerCandidates = @($roots | Sort-Object -Unique | ForEach-Object { Join-Path $_ 'metaeditor64.exe' })
        foreach ($candidate in $script:compilerCandidates) {
            if (Test-Path -LiteralPath $candidate) { $compiler=$candidate; break }
        }
        $includeRoots = @($roots | ForEach-Object { Join-Path $_ 'MQL5' })
        foreach ($base in @((Join-Path $env:APPDATA 'MetaQuotes\Terminal'),(Join-Path $env:LOCALAPPDATA 'MetaQuotes\Terminal'))) {
            if (Test-Path -LiteralPath $base) {
                $includeRoots += @(Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue |
                    ForEach-Object { Join-Path $_.FullName 'MQL5' })
            }
        }
        foreach ($candidate in $includeRoots) {
            if (Test-Path -LiteralPath (Join-Path $candidate 'Include\Trade\Trade.mqh')) { $include=$candidate; break }
        }
        if ($null -ne $compiler -and $null -ne $include -and $setup.HasExited) { break }
        if (-not $diagnosed -and [DateTime]::UtcNow -gt $diagnoseAt) {
            try { Read-SetupDiagnostics } catch { $receipt.setup_diagnostic_failure=$_.Exception.Message }
            $diagnosed=$true
        }
        Start-Sleep -Seconds 1
    }
    try { Read-SetupDiagnostics } catch { $receipt.setup_diagnostic_failure=$_.Exception.Message }
    Get-Process terminal,terminal64 -ErrorAction SilentlyContinue | Stop-Process -Force
    if (-not $setup.HasExited) { $setup.Kill(); $setup.WaitForExit(10000) | Out-Null }
    if ($null -eq $compiler -or $null -eq $include) { throw 'The official SDK installer did not supply MetaEditor and the native standard library' }
    $receipt.compiler_signature = Assert-Publisher $compiler
    $receipt.compiler_sha256 = (Get-FileHash $compiler -Algorithm SHA256).Hash.ToLowerInvariant()
    $receipt.compiler_file_version = (Get-Item $compiler).VersionInfo.FileVersion
    $receipt.standard_library_trade_sha256 = (Get-FileHash (Join-Path $include 'Include\Trade\Trade.mqh') -Algorithm SHA256).Hash.ToLowerInvariant()
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
