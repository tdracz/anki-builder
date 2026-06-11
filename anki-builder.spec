# PyInstaller spec file
# Build with: pyinstaller anki-builder.spec
#
# Prerequisites:
#   pip install pyinstaller
#   npm run build --prefix frontend   (build frontend first)

from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH)
FRONTEND_DIST = ROOT / "frontend" / "dist"

# Collect everything from packages that use heavy dynamic imports
_datas, _binaries, _hiddenimports = [], [], []
for pkg in ("fastapi", "starlette", "uvicorn", "anyio", "pydantic", "pydantic_core", "h11"):
    d, b, h = collect_all(pkg)
    _datas += d
    _binaries += b
    _hiddenimports += h

a = Analysis(
    [str(ROOT / "start.py")],
    pathex=[str(ROOT)],
    binaries=_binaries,
    datas=_datas + [
        (str(FRONTEND_DIST), "frontend/dist"),
        (str(ROOT / "backend"), "backend"),
    ],
    hiddenimports=_hiddenimports + [
        # HTTP / scraping
        "requests",
        "urllib3",
        "certifi",
        "charset_normalizer",
        "idna",
        "bs4",
        "lxml",
        "lxml.etree",
        "lxml._elementpath",
        # Tenacity
        "tenacity",
        # Python stdlib sometimes missed
        "sqlite3",
        "logging.handlers",
        "email.mime.text",
        "email.mime.multipart",
        # Our backend packages
        "backend",
        "backend.main",
        "backend.pipeline",
        "backend.database",
        "backend.anki_connect",
        "backend.anki_importer",
        "backend.image_fetcher",
        "backend.models",
        "backend.languages",
        "backend.languages.base",
        "backend.languages.english",
    ],
    hookspath=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="anki-builder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=None,
)
