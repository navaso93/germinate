param([switch]$Agent, [switch]$Drive)
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
$pythonPath = if ($pythonCommand) { $pythonCommand.Source } else { Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' }
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Python was not found.' }
$arguments = @((Join-Path $PSScriptRoot 'germinate.py'))
if ($Agent) { $arguments += '--agent' }
if ($Drive) { $arguments += '--drive' }
& $pythonPath @arguments
exit $LASTEXITCODE

