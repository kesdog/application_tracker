param([Parameter(Mandatory=$true)][string]$Target)
$ErrorActionPreference = 'Stop'
foreach ($name in 'WINDOWS_CERTIFICATE_PFX', 'WINDOWS_CERTIFICATE_PASSWORD', 'WINDOWS_TIMESTAMP_URL') {
    if (-not [Environment]::GetEnvironmentVariable($name)) { throw "Missing protected signing setting: $name" }
}
$pfxPath = Join-Path $env:RUNNER_TEMP ('tracker-sign-' + [guid]::NewGuid() + '.pfx')
$cert = $null
try {
    [IO.File]::WriteAllBytes($pfxPath, [Convert]::FromBase64String($env:WINDOWS_CERTIFICATE_PFX))
    $password = ConvertTo-SecureString $env:WINDOWS_CERTIFICATE_PASSWORD -AsPlainText -Force
    $cert = Import-PfxCertificate -FilePath $pfxPath -CertStoreLocation Cert:\CurrentUser\My -Password $password
    $signtool = (Get-ChildItem 'C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe' | Sort-Object FullName -Descending | Select-Object -First 1).FullName
    if (-not $signtool) { throw 'Windows SDK signtool is required' }
    $files = if (Test-Path -LiteralPath $Target -PathType Container) { Get-ChildItem -LiteralPath $Target -Recurse -File | Where-Object { $_.Extension -in '.exe', '.dll', '.pyd' } } else { Get-Item -LiteralPath $Target }
    foreach ($file in $files) {
        & $signtool sign /sha1 $cert.Thumbprint /fd SHA256 /tr $env:WINDOWS_TIMESTAMP_URL /td SHA256 $file.FullName
        if ($LASTEXITCODE -ne 0) { throw "Signing failed: $($file.Name)" }
        & $signtool verify /pa /all $file.FullName
        if ($LASTEXITCODE -ne 0) { throw "Signature verification failed: $($file.Name)" }
    }
} finally {
    if (Test-Path -LiteralPath $pfxPath) { Remove-Item -LiteralPath $pfxPath -Force }
    if ($cert) { Remove-Item -LiteralPath ('Cert:\CurrentUser\My\' + $cert.Thumbprint) -DeleteKey }
}
