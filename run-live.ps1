$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
$pythonPath = if ($pythonCommand) {
    $pythonCommand.Source
} else {
    Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Python was not found. Install Python 3 or run this project through Codex.'
}

& $pythonPath (Join-Path $PSScriptRoot 'germinate.py')
exit $LASTEXITCODE

