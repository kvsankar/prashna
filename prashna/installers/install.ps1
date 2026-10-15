# Install Prashna (Windows):
#   powershell -ExecutionPolicy ByPass -c "irm https://sankara.net/prashna/install.ps1 | iex"
# Installs uv (Astral's Python package manager) if it is missing, then
# installs the `prashna` command with `uv tool install`.
$ErrorActionPreference = "Stop"
# "Stop" does not cover a program's exit status, so each program call below
# that must succeed checks $LASTEXITCODE itself.

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv (from https://astral.sh/uv)..."
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not install uv (its installer exited with status $LASTEXITCODE). Install it from https://docs.astral.sh/uv/ and run this script again."
    }
    # Make the freshly installed uv usable in this session.
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "Could not install uv. Install it from https://docs.astral.sh/uv/ and run this script again."
    }
}

uv tool install --upgrade prashna
if ($LASTEXITCODE -ne 0) {
    throw "Could not install Prashna (uv tool install exited with status $LASTEXITCODE). Check the messages above, then run this script again."
}
# As in install.sh, a failed update-shell is not an error: the message below
# says to open a new terminal.
uv tool update-shell | Out-Null

Write-Host ""
Write-Host "Prashna is installed. Start it with:"
Write-Host ""
Write-Host "    prashna"
Write-Host ""
Write-Host "If the command isn't found, open a new terminal first."
