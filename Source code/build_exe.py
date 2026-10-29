"""Đóng gói thành 1 file Agenty.exe:  .venv\\Scripts\\python build_exe.py"""
import importlib.util
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"

HIDDEN = ["docx", "openpyxl", "pptx", "PIL", "matplotlib", "matplotlib.backends.backend_agg", "duckduckgo_search",
          "ddgs", "bs4", "pypdf", "openai", "httpx", "pptx_design_engine", "office_helpers", "skills", "memory", "shortcuts", "render", "voice", "markdown", "pygments",
          "PySide6.QtTextToSpeech", "PySide6.QtMultimedia", "numpy",
          "win32com", "win32com.client", "win32com.shell", "pythoncom", "pywintypes", "lxml", "pandas", "xlrd", "pypdfium2",
          "reportlab", "reportlab.pdfbase.ttfonts", "reportlab.platypus"]
# Code AI viết chạy trong exec() nên PyInstaller không thấy các import đó -> gom đủ submodule
SUBMODULES = ["pptx", "docx", "openpyxl", "PIL", "ddgs", "duckduckgo_search", "reportlab", "pypdf", "pygments",
              "markdown"]
DATA = ["pptx", "docx", "ddgs", "reportlab"]


def present(mod):
    return importlib.util.find_spec(mod.split(".")[0]) is not None or (SRC / f"{mod}.py").exists()


args = [str(SRC / "main.py"), "--onefile", "--noconsole", "--name", "Agenty", "--clean", "--noconfirm",
        "--paths", str(SRC), "--exclude-module", "tkinter"]
if (ROOT / "config.json").exists():  # nhúng sẵn địa chỉ + khoá API
    args += ["--add-data", f"{ROOT / 'config.json'};."]
else:
    print("Không có config.json: bản build sẽ hỏi API khi mở lần đầu")
for m in HIDDEN:
    if present(m):
        args += ["--hidden-import", m]
    else:
        print(f"Bỏ qua (chưa cài): {m}")
for m in SUBMODULES:
    if present(m):
        args += ["--collect-submodules", m]
for m in DATA:
    if present(m):
        args += ["--collect-data", m]
for native in ("primp", "pypdfium2", "pypdfium2_raw"):  # thư viện có file .dll đi kèm
    if present(native):
        args += ["--collect-all", native]
if (ROOT / "icon.ico").exists():
    args += ["--icon", str(ROOT / "icon.ico"), "--add-data", f"{ROOT / 'icon.ico'};."]
if (ROOT / "skills").is_dir():  # skill đóng gói sẵn (slide-design, ui-ux-pro-max, impeccable)
    args += ["--add-data", f"{ROOT / 'skills'};skills"]
if (ROOT / "logo.png").exists():  # logo trên thanh bên và icon cửa sổ
    args += ["--add-data", f"{ROOT / 'logo.png'};."]

PyInstaller.__main__.run(args)
print("\nXong! File chạy nằm ở:", ROOT / "dist" / "Agenty.exe")
