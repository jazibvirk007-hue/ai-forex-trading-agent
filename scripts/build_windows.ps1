$ErrorActionPreference = "Stop"

Write-Host "Building TJ Trading OS Windows executable..."
python -m pip install --upgrade pip
pip install -e ".[live,windows]"
pytest -q
ruff check .
pyinstaller --clean --noconfirm tj_trading_os.spec

Write-Host ""
Write-Host "Build complete:"
Write-Host "  dist\TJ-Trading-OS.exe"
