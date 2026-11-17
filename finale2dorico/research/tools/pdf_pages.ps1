# Render PDF pages to PNG with Windows' built-in PDF renderer (Windows.Data.Pdf; no installs).
#
#   powershell.exe -ExecutionPolicy Bypass -File pdf_pages.ps1 -Pdf "D:\x.pdf" -Pages 1,2 -OutDir "C:\tmp" [-Width 1600]
#
# Prints the page count, then one output path per page. Used to compare converted scores with
# the published PDFs of the same pieces.
param(
    [Parameter(Mandatory)][string]$Pdf,
    [string]$Pages = "1",   # "1,2,5" or "1-4"
    [Parameter(Mandatory)][string]$OutDir,
    [int]$Width = 1600
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Data.Pdf.PdfDocument, Windows.Data.Pdf, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]

$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
$asTaskAction = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction' } | Select-Object -First 1
function Await($op, [Type]$type) {
    $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(); $t.Result
}
function AwaitAction($op) { $t = $asTaskAction.Invoke($null, @($op)); $t.Wait() }

$src = (Resolve-Path -LiteralPath $Pdf).ProviderPath
if ($src.StartsWith("\\")) {  # the WinRT file API can't open \\wsl.localhost paths: use a local copy
    $tmp = Join-Path $env:TEMP ("f2d-" + [IO.Path]::GetFileName($src))
    Copy-Item -LiteralPath $src -Destination $tmp -Force
    $src = $tmp
}
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($src)) ([Windows.Storage.StorageFile])
$doc = Await ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($file)) ([Windows.Data.Pdf.PdfDocument])
Write-Output "pages $($doc.PageCount)"
New-Item -ItemType Directory -Force $OutDir | Out-Null
$base = [IO.Path]::GetFileNameWithoutExtension($Pdf) -replace '[^\w.-]+', '_'
$list = foreach ($part in $Pages -split ',') {
    if ($part -match '^(\d+)-(\d+)$') { [int]$Matches[1]..[int]$Matches[2] } else { [int]$part }
}
foreach ($n in $list) {
    if ($n -lt 1 -or $n -gt $doc.PageCount) { continue }
    $page = $doc.GetPage($n - 1)
    $opts = New-Object Windows.Data.Pdf.PdfPageRenderOptions
    $opts.DestinationWidth = $Width
    $stream = New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
    AwaitAction ($page.RenderToStreamAsync($stream, $opts))
    $out = Join-Path $OutDir ("{0}_p{1}.png" -f $base, $n)
    $net = [System.IO.WindowsRuntimeStreamExtensions]::AsStreamForRead($stream.GetInputStreamAt(0))
    $fs = [IO.File]::Create($out); $net.CopyTo($fs); $fs.Close()
    Write-Output $out
}
