"""Bộ nhớ dài hạn kiểu Agenty: những điều AI biết về người dùng + tìm lại đoạn chat cũ."""
import json
import re
import time
import uuid

from config import APP_DIR, HISTORY_DIR, write_json

MEMORY_PATH = APP_DIR / "memory.json"


def load() -> list[dict]:
    try:
        data = json.loads(MEMORY_PATH.read_text("utf-8"))
    except (OSError, ValueError):
        return []
    items = data.get("items", []) if isinstance(data, dict) else []
    return [i for i in items if isinstance(i, dict) and isinstance(i.get("text"), str) and i.get("id")]


def _save(items: list[dict]) -> None:
    write_json(MEMORY_PATH, {"items": items}, indent=2)


def remember(text: str) -> dict:
    text = " ".join(str(text).split())[:500]
    items = load()
    if not text:
        return {"error": "Nội dung trống"}
    if any(i["text"].lower() == text.lower() for i in items):
        return {"ok": True, "note": "Đã có trong bộ nhớ"}
    item = {"id": uuid.uuid4().hex[:8], "text": text, "created": time.strftime("%d/%m/%Y")}
    _save(items + [item])
    return {"ok": True, "id": item["id"]}


def forget(key: str) -> dict:
    """Xoá theo id hoặc theo đoạn chữ khớp. Khoá rỗng bị từ chối (xoá hết phải dùng clear)."""
    key = (key or "").strip()
    if not key:
        return {"ok": False, "error": "Thiếu nội dung cần quên."}
    items = load()
    keep = [i for i in items if i["id"] != key and key.lower() not in i["text"].lower()]
    _save(keep)
    return {"ok": True, "removed": len(items) - len(keep)}


def clear() -> None:
    _save([])


def prompt_block() -> str:
    items = load()
    if not items:
        return "(Chưa có gì.)"
    return "\n".join(f"- [{i['id']}] {i['text']}" for i in items)


def search_chats(query: str, exclude_id: str | None = None, limit: int = 5) -> dict:
    """Tìm trong các đoạn chat cũ theo từ khoá; trả tiêu đề, ngày và đoạn trích quanh chỗ khớp."""
    words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 1]
    if not words:
        return {"results": []}
    hits = []
    for p in HISTORY_DIR.glob("*.json"):
        try:
            d = json.loads(p.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict) or d.get("id") == exclude_id:
            continue
        lines = [f"{'Người dùng' if x['role'] == 'user' else 'AI'}: {x.get('text') or ''}" for x in d.get("display", [])]
        blob = (d.get("title", "") + "\n" + "\n".join(lines)).lower()
        score = sum(blob.count(w) for w in words)
        if not score:
            continue
        pos = min((blob.find(w) for w in words if w in blob), default=0)
        full = d.get("title", "") + "\n" + "\n".join(lines)
        hits.append((score, {"title": d.get("title"),
                             "date": time.strftime("%d/%m/%Y", time.localtime(d.get("updated", 0))),
                             "excerpt": full[max(0, pos - 300): pos + 900]}))
    hits.sort(key=lambda h: -h[0])
    return {"results": [h for _, h in hits[:limit]]}
