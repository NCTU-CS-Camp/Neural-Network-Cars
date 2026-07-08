#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
  echo "This script must run on Linux x86_64 (use the GitHub Actions workflow)."
  exit 1
fi

uv sync --locked --group dev

if [[ "${SKIP_TESTS:-0}" != "1" ]]; then
  uv run pytest -q
fi

rm -rf build dist
uv run pyinstaller --noconfirm --clean NeuralNetworkCars.spec

PACKAGE_DIR="$PROJECT_ROOT/dist/NeuralNetworkCars-Ubuntu-x86_64"
mkdir -p "$PACKAGE_DIR"
cp "$PROJECT_ROOT/dist/NeuralNetworkCars" "$PACKAGE_DIR/"
cp "$PROJECT_ROOT/packaging/linux/README.txt" "$PACKAGE_DIR/"
chmod +x "$PACKAGE_DIR/NeuralNetworkCars"

ARCHIVE="$PROJECT_ROOT/dist/NeuralNetworkCars-Ubuntu-x86_64.tar.gz"
tar -C "$PACKAGE_DIR" -czf "$ARCHIVE" .

echo "Built: dist/NeuralNetworkCars"
echo "Built: dist/NeuralNetworkCars-Ubuntu-x86_64.tar.gz"
