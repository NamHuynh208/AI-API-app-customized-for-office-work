"""Skills kiểu Claude: mỗi skill là một thư mục có SKILL.md (frontmatter name/description) + tài liệu kèm theo.

Nguồn: skill đóng gói sẵn trong app (thư mục skills/) và skill người dùng nhập thêm (AgentyData/skills).
"""
import re
import shutil
import sys
from pathlib import Path

from config import APP_DIR, app_base_dir

USER_SKILLS = APP_DIR / "skills"
USER_SKILLS.mkdir(parents=True, exist_ok=True)


def _bundled_dir() -> Path:
    base = Path(sys._MEIPASS) if hasattr(sys, "_MEIPASS") else app_base_dir()
    return base / "skills"


def _parse(skill_md: Path) -> dict | None:
    try:
        text = skill_md.read_text("utf-8", errors="replace")
    except OSError:
        return None
    meta = {}
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            k, _, v = line.partition(":")
            if v:
                meta[k.strip()] = v.strip().strip('"')
    name = meta.get("name") or skill_md.parent.name
    return {"name": name, "description": meta.get("description", "")[:400], "dir": skill_md.parent}


def list_skills() -> list[dict]:
    """Skill người dùng nhập sau cùng sẽ đè skill đóng gói cùng tên."""
    found = {}
    for root in (_bundled_dir(), USER_SKILLS):
        for md in sorted(root.glob("*/SKILL.md")) if root.is_dir() else []:
            info = _parse(md)
            if info:
                found[info["name"]] = info
    return list(found.values())


def load_skill(name: str, limit: int = 24000) -> dict:
    skill = next((s for s in list_skills() if s["name"] == name), None)
    if not skill:
        return {"error": f"Không có skill '{name}'. Có: {', '.join(s['name'] for s in list_skills())}"}
    text = (skill["dir"] / "SKILL.md").read_text("utf-8", errors="replace")
    files = sorted(str(p.relative_to(skill["dir"])) for p in skill["dir"].rglob("*")
                   if p.is_file() and p.name != "SKILL.md")[:80]
    return {"name": name, "folder": str(skill["dir"]), "content": text[:limit],
            "other_files": files,
            "note": "Đọc file kèm theo bằng read_local_file(folder + '/' + tên file). Skill viết cho Claude Code có thể "
                    "nhắc tới lệnh/script không chạy được ở đây — chỉ lấy nguyên tắc và dữ liệu."}


def import_skill(folder: str) -> str:
    """Chép một thư mục skill (có SKILL.md) vào AgentyData/skills. Trả tên skill."""
    src = Path(folder)
    info = _parse(src / "SKILL.md")
    if not info:
        raise ValueError("Thư mục này không có file SKILL.md")
    dest = USER_SKILLS / re.sub(r"[^\w.-]+", "-", info["name"])
    shutil.copytree(src, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.exe", ".git"))
    return info["name"]


def remove_skill(name: str) -> bool:
    """Chỉ xoá được skill người dùng tự nhập (skill đóng gói nằm trong .exe)."""
    for md in USER_SKILLS.glob("*/SKILL.md"):
        info = _parse(md)
        if info and info["name"] == name:
            shutil.rmtree(md.parent, ignore_errors=True)
            return True
    return False
