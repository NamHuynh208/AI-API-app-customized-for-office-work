"""Lối tắt Desktop + Start Menu (để app hiện trong Windows Search), tạo ở lần mở đầu và khi file .exe bị chuyển chỗ."""
import contextlib
import subprocess
import sys
from pathlib import Path

NAME = "Agenty"
FALLBACK = "Agenty (2)"  # khi máy đã có một app khác cũng tên "Agenty"


def _shell():
    import win32com.client
    return win32com.client.Dispatch("WScript.Shell")


def _link():
    """IShellLink gốc của Windows: hỗ trợ đường dẫn Unicode (WScript.Shell hỏng với thư mục tên tiếng Việt)."""
    import pythoncom
    from win32com.shell import shell as wshell
    pythoncom.CoInitialize()
    return pythoncom.CoCreateInstance(wshell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, wshell.IID_IShellLink)


def write_link(lnk: Path, target: Path, description: str = "") -> Path:
    import pythoncom
    link = _link()
    link.SetPath(str(target))
    link.SetWorkingDirectory(str(target.parent))
    link.SetIconLocation(str(target), 0)
    link.SetDescription(description)
    link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(lnk), 0)
    return lnk


def _target(shell, lnk: Path) -> str:
    import pythoncom
    from win32com.shell import shell as wshell
    with contextlib.suppress(Exception):
        link = _link()
        link.QueryInterface(pythoncom.IID_IPersistFile).Load(str(lnk))
        return link.GetPath(wshell.SLGP_RAWPATH)[0]
    return ""


def _is_mine(shell, lnk: Path, exe: Path) -> bool:
    return lnk.exists() and Path(_target(shell, lnk)).name.lower() == exe.name.lower()


def _store_app_named(name: str) -> bool:
    """App cài từ Microsoft Store (như Agenty chính thức) không có file .lnk — hỏi danh sách app trong Start."""
    with contextlib.suppress(Exception):
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              f"@(Get-StartApps | Where-Object {{ $_.Name -eq '{name}' -and $_.AppID -like '*!*' }}).Count"],
                             capture_output=True, text=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
        return int(out.stdout.strip() or 0) > 0  # AppID có dấu "!" = app dạng Store/MSIX
    return False


def choose_name(shell, folders: list[Path], exe: Path) -> str:
    for folder in folders:  # đã từng tạo rồi thì giữ nguyên tên cũ
        for name in (NAME, FALLBACK):
            if _is_mine(shell, folder / f"{name}.lnk", exe):
                return name
    taken = any((f / f"{NAME}.lnk").exists() for f in folders) or _store_app_named(NAME)
    return FALLBACK if taken else NAME


def _place(shell, folder: Path, exe: Path, name: str) -> Path:
    return write_link(folder / f"{name}.lnk", exe, "Agenty — trợ lý AI")


def ensure(cfg: dict, exe: Path | None = None) -> list[str]:
    """Gọi mỗi lần mở app. Chỉ làm việc khi chạy bằng file .exe và khi chưa có / đường dẫn .exe đã đổi.
    Trả danh sách lối tắt đã tạo (cfg["shortcuts"] được cập nhật, nơi gọi tự lưu cfg)."""
    exe = exe or (Path(sys.executable) if getattr(sys, "frozen", False) else None)
    if exe is None or sys.platform != "win32":
        return []
    done = cfg.get("shortcuts") or {}
    if done.get("exe") == str(exe) and all(Path(p).exists() for p in done.get("links", [])):
        return []
    shell = _shell()
    folders = []
    for special in ("Desktop", "Programs"):  # Programs = Start Menu → Windows Search tìm thấy
        with contextlib.suppress(Exception):
            folders.append(Path(shell.SpecialFolders(special)))
    name = choose_name(shell, folders, exe)
    links = []
    for folder in folders:
        with contextlib.suppress(Exception):
            links.append(str(_place(shell, folder, exe, name)))
    cfg["shortcuts"] = {"exe": str(exe), "links": links, "name": name}
    return links


def remove(cfg: dict) -> None:
    """Xoá các lối tắt app đã tạo (dùng khi Xoá ứng dụng)."""
    for p in (cfg.get("shortcuts") or {}).get("links", []):
        with contextlib.suppress(OSError):
            Path(p).unlink()
