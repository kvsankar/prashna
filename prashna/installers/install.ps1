# Install Prashna (Windows):
#   powershell -ExecutionPolicy ByPass -c "irm https://prashna.sankara.net/install.ps1 | iex"
# Installs uv (Astral's Python package manager) if it is missing, then
# installs the `prashna` command with `uv tool install`.
$ErrorActionPreference = "Stop"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv (from https://astral.sh/uv)..."
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    # Make the freshly installed uv usable in this session.
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

uv tool install --upgrade prashna
uv tool update-shell | Out-Null

Write-Host ""
Write-Host "Prashna is installed. Start it with:"
Write-Host ""
Write-Host "    prashna"
Write-Host ""
Write-Host "If the command isn't found, open a new terminal first."
