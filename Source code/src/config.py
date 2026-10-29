"""Đường dẫn dữ liệu (thư mục AgentyData cạnh file chạy) và đọc/ghi config.json."""
import json
import os
import sys
from pathlib import Path

APP_NAME = "Agenty"  # tên thư mục dữ liệu cũ trong %APPDATA%
LEGACY_DIR = Path(os.environ.get("APPDATA") or Path.home()) / APP_NAME  # nơi lưu cũ (ổ C)


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _pick_app_dir() -> Path:
    """Lưu cạnh file chạy (không chiếm ổ C / OneDrive); chỉ dùng %APPDATA% khi thư mục đó không ghi được."""
    portable = app_base_dir() / "AgentyData"
    try:
        portable.mkdir(parents=True, exist_ok=True)
        probe = portable / ".ghi_thu"
        probe.write_text("ok")
        probe.unlink()
        return portable
    except OSError:
        return LEGACY_DIR


APP_DIR = _pick_app_dir()


def _migrate_legacy():
    """Chuyển dữ liệu của bản cũ (lưu ở %APPDATA% trên ổ C) sang thư mục mới, rồi xoá bản cũ."""
    import shutil
    # chỉ bản .exe mới chuyển: chạy thử từ mã nguồn không được "hút" dữ liệu thật của người dùng
    if not getattr(sys, "frozen", False) or APP_DIR == LEGACY_DIR or not LEGACY_DIR.is_dir() \
            or any((APP_DIR / "history").glob("*.json")):
        return
    try:
        shutil.copytree(LEGACY_DIR, APP_DIR, dirs_exist_ok=True)
        shutil.rmtree(LEGACY_DIR, ignore_errors=True)
    except OSError:
        pass  # chép lỗi thì giữ nguyên bản cũ, không mất dữ liệu


_migrate_legacy()
OUTPUT_DIR = APP_DIR / "outputs"
IMAGES_DIR = OUTPUT_DIR / "images"
UPLOADS_DIR = APP_DIR / "uploads"
HISTORY_DIR = APP_DIR / "history"
CONFIG_PATH = APP_DIR / "config.json"

for _d in (OUTPUT_DIR, IMAGES_DIR, UPLOADS_DIR, HISTORY_DIR):
    _d.mkdir(parents=True, exist_ok=True)
# Cache của matplotlib nằm trong thư mục app để nút "Xoá ứng dụng" dọn sạch
os.environ.setdefault("MPLCONFIGDIR", str(APP_DIR / "mpl"))

DEFAULTS = {
    "base_url": "https://api.openai.com/v1",
    "api_key": "",
    "default_chat_model": "gpt-6.1-sol",
    "default_image_model": "gpt-image-2.5",
    "effort": "medium",
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    # Thứ tự ưu tiên tăng dần: config nhúng trong .exe, config.json cạnh .exe, bản trong AgentyData (hộp Cài đặt lưu)
    embedded = Path(getattr(sys, "_MEIPASS", app_base_dir())) / "config.json"
    for p in (embedded, app_base_dir() / "config.json", CONFIG_PATH):
        try:
            data = json.loads(p.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):  # file sai cấu trúc thì bỏ qua, không làm hỏng app
            cfg.update(data)
    return cfg


def api_embedded() -> bool:
    """Bản .exe đã nhúng sẵn khoá API (bản cá nhân) → ẩn ô nhập API trong Cài đặt."""
    if not hasattr(sys, "_MEIPASS"):
        return False
    try:
        return bool(json.loads((Path(sys._MEIPASS) / "config.json").read_text("utf-8")).get("api_key"))
    except (OSError, ValueError, AttributeError):
        return False


def write_json(path: Path, data, indent=None) -> None:
    """Ghi nguyên tử: ghi ra file tạm rồi thay thế, mất điện / lỗi giữa chừng không làm hỏng file cũ."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=indent), "utf-8")
    os.replace(tmp, path)


def save_config(cfg: dict) -> None:
    write_json(CONFIG_PATH, cfg, indent=2)
