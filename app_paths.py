import os
import pathlib
import shutil
import sys

APP_NAME = "GameSir Bridge"
APP_VERSION = "v7.0.0"
BUNDLE_VERSION = "7.0.0"
GITHUB_REPO = "analogart/gamesir-g7-se-macos"


def get_resource_dir() -> pathlib.Path:
    """Retorna o diretório onde ficam os assets e templates originais (suporta PyInstaller)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return pathlib.Path(sys._MEIPASS)
    return pathlib.Path(__file__).resolve().parent


def get_data_dir() -> pathlib.Path:
    """Retorna ~/Library/Application Support/GameSir Bridge (criando se necessário)."""
    base = pathlib.Path.home() / "Library" / "Application Support" / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_config_path() -> pathlib.Path:
    """Garante que profiles.json exista em Application Support e retorna seu Path."""
    data_cfg = get_data_dir() / "profiles.json"
    if not data_cfg.exists():
        bundled_cfg = get_resource_dir() / "profiles.json"
        if bundled_cfg.exists():
            shutil.copy2(bundled_cfg, data_cfg)
    return data_cfg


def get_pid_path() -> pathlib.Path:
    return get_data_dir() / ".config_ui.pid"


def find_libusb_path() -> str | None:
    """Localiza libusb-1.0.dylib em bundles standalone, Apple Silicon ou Macs Intel."""
    res_dir = get_resource_dir()
    candidates = [
        res_dir / "libusb-1.0.dylib",
        res_dir.parent / "Frameworks" / "libusb-1.0.dylib",
        pathlib.Path("/opt/homebrew/lib/libusb-1.0.dylib"),  # Apple Silicon
        pathlib.Path("/usr/local/lib/libusb-1.0.dylib"),     # Intel Mac
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return None
