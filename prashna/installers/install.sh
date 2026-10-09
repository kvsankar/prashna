#!/bin/sh
# Install Prashna (macOS and Linux):
#   curl -LsSf https://prashna.sankara.net/install.sh | sh
# Installs uv (Astral's Python package manager) if it is missing, then
# installs the `prashna` command with `uv tool install`.
set -eu

if ! command -v uv >/dev/null 2>&1; then
    echo "Installing uv (from https://astral.sh/uv)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Make the freshly installed uv usable in this shell.
    PATH="${XDG_BIN_HOME:-$HOME/.local/bin}:$HOME/.cargo/bin:$PATH"
    export PATH
fi

uv tool install --upgrade prashna
uv tool update-shell >/dev/null 2>&1 || true

echo
echo "Prashna is installed. Start it with:"
echo
echo "    prashna"
echo
echo "If the command isn't found, open a new terminal first."
