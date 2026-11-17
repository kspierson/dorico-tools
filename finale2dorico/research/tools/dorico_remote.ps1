# Talk to a running Dorico through its Remote Control API (WebSocket, 127.0.0.1:4560).
#
# Runs on Windows (WSL cannot reach Dorico's localhost port). From WSL:
#   powershell.exe -ExecutionPolicy Bypass -File "$(wslpath -w research/tools/dorico_remote.ps1)" -Connect
#
# -Connect      connect only. The first time, Dorico asks to allow "f2d review"; the session token
#               is then kept in %LOCALAPPDATA%\f2d\dorico-session.txt so later runs need no prompt.
# -Command X    send one command, e.g. -Command "Window.SwitchMode?WindowMode=kPrintMode".
# -ExportCurrent  export + close the project that is open now.
# -Export a,b   open each .dorico (Windows paths), switch to Print mode, export the current layout
#               (full score) as PDF next to the project, close it. Opens/closes projects in the
#               running Dorico, so only run it when the user is not working in Dorico.
#
# Protocol (Dorico 4+, see romanstark/dorico-maestro docs/protocol.md):
#   -> {"message":"connect","clientName":..,"handshakeVersion":"1.0"[,"sessionToken":..]}
#   <- {"message":"sessiontoken","sessionToken":..}   (after the user allows it, first time)
#   -> {"message":"acceptsessiontoken","sessionToken":..}
#   <- {"message":"response","code":"kConnected"}
#   -> {"message":"command","command":"Namespace.Command?Param=Value&..."}  <- response kOK/kError
param(
    [switch]$Connect,
    [switch]$Status,
    [switch]$ExportCurrent,
    [string]$Command,
    [string[]]$Export,
    [int]$WaitForUser = 900,
    [int]$Settle = 10,      # seconds after moving to the end of the score before exporting
    [int]$Port = 4560
)
$ErrorActionPreference = "Stop"
$tokenFile = Join-Path $env:LOCALAPPDATA "f2d\dorico-session.txt"

$ws = New-Object System.Net.WebSockets.ClientWebSocket
$ct = [Threading.CancellationToken]::None
$ws.ConnectAsync([Uri]"ws://127.0.0.1:$Port", $ct).Wait()

function Send($obj) {
    $json = $obj | ConvertTo-Json -Compress -Depth 5
    $bytes = [Text.Encoding]::UTF8.GetBytes($json)
    $seg = New-Object ArraySegment[byte] -ArgumentList @(, $bytes)
    $ws.SendAsync($seg, [Net.WebSockets.WebSocketMessageType]::Text, $true, $ct).Wait()
}

function Receive([int]$timeoutSec = 120) {
    $buf = New-Object byte[] 65536
    $ms = New-Object IO.MemoryStream
    $cts = New-Object Threading.CancellationTokenSource ([TimeSpan]::FromSeconds($timeoutSec))
    do {
        $seg = New-Object ArraySegment[byte] -ArgumentList @(, $buf)
        $r = $ws.ReceiveAsync($seg, $cts.Token).Result
        if ($r.MessageType -eq [Net.WebSockets.WebSocketMessageType]::Close) {
            throw "Dorico closed the connection ($($ws.CloseStatus) $($ws.CloseStatusDescription))"
        }
        $ms.Write($buf, 0, $r.Count)
    } while (-not $r.EndOfMessage)
    return [Text.Encoding]::UTF8.GetString($ms.ToArray())
}

$script:hasScore = $false
function Note($msg) {  # Dorico pushes "status" messages between replies; track whether a score is open
    if ($msg.message -eq "status" -and $null -ne $msg.hasScore) { $script:hasScore = [bool]$msg.hasScore }
}

function Run([string]$cmd, [int]$timeoutSec = 600) {
    Send @{ message = "command"; command = $cmd }
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ($true) {
        $left = [int][Math]::Max(1, ($deadline - (Get-Date)).TotalSeconds)
        $msg = Receive $left | ConvertFrom-Json
        Note $msg
        if ($msg.message -ne "response") { Write-Host ("    ({0} hasScore={1})" -f $msg.message, $msg.hasScore) }
        if ($msg.message -eq "response") {
            Write-Host "  $cmd -> $($msg.code) $($msg.detail)"
            return $msg
        }
    }
}

function WaitForScore([bool]$want, [int]$timeoutSec = 600) {
    # Never cancel a pending receive: .NET aborts the whole WebSocket when a ReceiveAsync is
    # cancelled. Ask for the status and wait (Dorico answers once it is free again).
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ($script:hasScore -ne $want -and (Get-Date) -lt $deadline) {
        Send @{ message = "getstatus" }
        $left = [int][Math]::Max(5, ($deadline - (Get-Date)).TotalSeconds)
        Note (Receive $left | ConvertFrom-Json)
        if ($script:hasScore -ne $want) { Start-Sleep -Seconds 2 }
    }
    return $script:hasScore -eq $want
}

function ExportOpen([string]$label) {
    # Dorico lays out pages only as they are viewed: in Print mode only page 1 exists unless the
    # whole score has been laid out. Moving the page view to the end lays out every page.
    Run "Window.SwitchMode?WindowMode=kWriteMode" | Out-Null
    Run "Window.SwitchLayoutAspectType?LayoutAspectType=kPageViewAspect" | Out-Null
    Run "View.MoveViewportToEnd" 900 | Out-Null
    Start-Sleep -Seconds $Settle
    Run "Window.SwitchMode?WindowMode=kPrintMode" | Out-Null
    Start-Sleep -Seconds 5
    Run "Print.ExportCurrentLayoutAsPDF" 900 | Out-Null
    Start-Sleep -Seconds 3
    # Dorico may count the freshly opened file as changed and then asks "save changes?" on
    # close (a modal dialog blocks everything); saving first avoids it. The review copy is
    # replaced by Dorico's own save of it.
    Run "File.Save" 900 | Out-Null
    Run "File.Close" | Out-Null
}

# --- handshake
$hello = [ordered]@{ message = "connect"; clientName = "f2d review"; handshakeVersion = "1.0" }
if (Test-Path $tokenFile) { $hello.sessionToken = (Get-Content $tokenFile -Raw).Trim() }
Send $hello
Write-Host "Waiting for Dorico (click Allow for 'f2d review' in Dorico if it asks)..."
$reply = Receive $WaitForUser | ConvertFrom-Json
if ($reply.message -eq "sessiontoken") {
    New-Item -ItemType Directory -Force (Split-Path $tokenFile) | Out-Null
    Set-Content $tokenFile $reply.sessionToken
    Send @{ message = "acceptsessiontoken"; sessionToken = $reply.sessionToken }
    $reply = Receive 60 | ConvertFrom-Json
}
if ($reply.code -ne "kConnected") { throw "Dorico did not connect: $($reply | ConvertTo-Json -Compress)" }
Write-Host "Connected."

if ($Status) {
    Send @{ message = "getstatus" }
    $m = Receive 20 | ConvertFrom-Json
    Write-Host ("status: hasScore={0} windowMode={1} notReadOnly={2}" -f $m.hasScore, $m.windowMode, $m.notReadOnly)
}
if ($Command) { Run $Command | Out-Null }
if ($ExportCurrent) { ExportOpen "current project" }
foreach ($p in $Export) {
    $path = $p -replace '\\', '/'
    Write-Host "== $p"
    $script:hasScore = $false
    Run "File.Open?File=$path" 300 | Out-Null
    if (-not (WaitForScore $true 300)) { Write-Host "  project did not open"; continue }
    ExportOpen $p
}
Send @{ message = "disconnect" }
$ws.Dispose()
