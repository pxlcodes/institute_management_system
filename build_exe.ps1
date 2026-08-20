[CmdletBinding()]
param(
    [string]$PythonPath = "python",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$buildEnvironment = Join-Path $projectRoot ".build-venv"
$buildPython = Join-Path $buildEnvironment "Scripts\python.exe"
$distribution = Join-Path $projectRoot "dist\ELH Management System"
$releaseDirectory = Join-Path $projectRoot "release"
$releaseArchive = Join-Path $releaseDirectory "ELH-Management-System-Windows-x64.zip"

Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath $buildPython)) {
        Write-Host "Creating isolated build environment..." -ForegroundColor Cyan
        & $PythonPath -m venv $buildEnvironment
        if ($LASTEXITCODE -ne 0) { throw "Could not create the build environment." }
    }

    Write-Host "Installing application and packaging dependencies..." -ForegroundColor Cyan
    & $buildPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Could not update pip." }
    & $buildPython -m pip install -r requirements.txt -r requirements-hardware.txt -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw "Could not install build dependencies." }

    if (-not $SkipTests) {
        Write-Host "Running automated tests..." -ForegroundColor Cyan
        $env:PYTHONDONTWRITEBYTECODE = "1"
        & $buildPython -m unittest discover -s tests -v
        if ($LASTEXITCODE -ne 0) { throw "Tests failed; the EXE was not built." }
    }

    Write-Host "Building the Windows application..." -ForegroundColor Cyan
    & $buildPython -m PyInstaller --clean --noconfirm packaging\elh_management.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

    if (-not (Test-Path -LiteralPath (Join-Path $distribution "ELH Management System.exe"))) {
        throw "The expected executable was not created."
    }

    Write-Host "Running packaged EXE self-test..." -ForegroundColor Cyan
    $packagedExecutable = Join-Path $distribution "ELH Management System.exe"
    & $packagedExecutable --self-test
    if ($LASTEXITCODE -ne 0) { throw "The packaged EXE self-test failed." }

    Copy-Item -LiteralPath ".env.example" -Destination (Join-Path $distribution "environment.example") -Force
    Copy-Item -LiteralPath "README.md" -Destination (Join-Path $distribution "README.md") -Force
    $templateDirectory = Join-Path $distribution "templates"
    New-Item -ItemType Directory -Path $templateDirectory -Force | Out-Null
    Copy-Item -Path "templates\*.docx" -Destination $templateDirectory -Force
    foreach ($folder in ("backups", "logs", "output\pdf", "output\certificates")) {
        New-Item -ItemType Directory -Path (Join-Path $distribution $folder) -Force | Out-Null
    }

    $buildInformation = @"
ELH Management System 1.0.0
Built: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz")
Architecture: Windows x64

FIRST START
1. Copy environment.example to .env in this folder.
2. Configure MySQL, hardware, production mode, and unique bootstrap passwords.
3. Start ELH Management System.exe.
4. Sign in, change required passwords, create and verify a database backup.

Do not copy the developer's .env into a release archive.
"@
    Set-Content -LiteralPath (Join-Path $distribution "BUILD_INFO.txt") -Value $buildInformation -Encoding UTF8

    New-Item -ItemType Directory -Path $releaseDirectory -Force | Out-Null
    if (Test-Path -LiteralPath $releaseArchive) {
        Remove-Item -LiteralPath $releaseArchive -Force
    }
    Compress-Archive -Path (Join-Path $distribution "*") -DestinationPath $releaseArchive -CompressionLevel Optimal
    $archiveHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $releaseArchive).Hash
    Set-Content -LiteralPath "$releaseArchive.sha256" -Value "$archiveHash  $(Split-Path -Leaf $releaseArchive)" -Encoding ASCII

    $executable = $packagedExecutable
    Write-Host "" 
    Write-Host "Production build completed." -ForegroundColor Green
    Write-Host "Executable: $executable"
    Write-Host "Deployment ZIP: $releaseArchive"
    Write-Host "SHA-256: $releaseArchive.sha256"
}
finally {
    Pop-Location
}
