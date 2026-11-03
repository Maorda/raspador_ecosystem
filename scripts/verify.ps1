$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "== 1/5: Pruebas unitarias =="
python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Fallaron las pruebas unitarias." }

Write-Host "== 2/5: Compilación =="
python -m compileall -q .
if ($LASTEXITCODE -ne 0) { throw "Falló compileall." }

Write-Host "== 3/5: Migración SQLite en base temporal =="
$PreviousDbPath = $env:SCRAPER_ECOSYSTEM_DB_PATH
$TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("scraper_ecosystem_verify_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $TempRoot | Out-Null
try {
    $env:SCRAPER_ECOSYSTEM_DB_PATH = Join-Path $TempRoot "verify.sqlite3"
    python main.py migrate
    if ($LASTEXITCODE -ne 0) { throw "Falló la migración SQLite." }

    Write-Host "== 4/5: Descubrimiento de plugins =="
    $PluginList = python main.py list-plugins
    if ($LASTEXITCODE -ne 0) { throw "Falló el listado de plugins." }
    if ($PluginList -notcontains "remaju") { throw "El plugin remaju no se registró." }

    Write-Host "== 5/5: Guardia de integración REMAJU =="
    $RunOutput = python main.py run --name remaju 2>&1 | Out-String
    $RunExitCode = $LASTEXITCODE
    if ($RunExitCode -eq 0) { throw "REMAJU no debería declarar éxito mientras la integración real no esté implementada." }
    if ($RunOutput -notmatch "REMAJU_INTEGRATION_NOT_IMPLEMENTED") {
        throw "El fallo de REMAJU no coincide con la guardia esperada. Salida: $RunOutput"
    }
    Write-Host "La guardia impide persistir datos ficticios, como se esperaba."
}
finally {
    if ($null -eq $PreviousDbPath) {
        Remove-Item Env:SCRAPER_ECOSYSTEM_DB_PATH -ErrorAction SilentlyContinue
    } else {
        $env:SCRAPER_ECOSYSTEM_DB_PATH = $PreviousDbPath
    }
    Remove-Item -LiteralPath $TempRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Verificación completada. Esto valida la base técnica, no la integración real con REMAJU."
