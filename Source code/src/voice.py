"""Giọng nói (ghi âm → chữ, chữ để đọc to) và xuất / chia sẻ đoạn chat."""
import base64
import io
import re
import time
import wave
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

import render
import tools

MAX_SECONDS = 120
VI_CHARS = re.compile(r"[ăâđêôơưàáạảãằắặẳẵầấậẩẫèéẹẻẽềếệểễìíịỉĩòóọỏõồốộổỗờớợởỡùúụủũừứựửữỳýỵỷỹ]", re.I)


# ---------- Ghi âm ----------

class Recorder(QObject):
    """Ghi âm micro mặc định thành WAV 16-bit (tự dừng sau MAX_SECONDS)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active = False

    def start(self):
        from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices
        dev = QMediaDevices.defaultAudioInput()
        if dev.isNull():
            raise RuntimeError("Không tìm thấy micro. Hãy cắm micro / tai nghe rồi thử lại.")
        fmt = QAudioFormat()
        fmt.setSampleRate(16000)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not dev.isFormatSupported(fmt):
            fmt = dev.preferredFormat()
        self.fmt = fmt
        self.buf = bytearray()
        self.src = QAudioSource(dev, fmt, self)
        self.io = self.src.start()
        if self.io is None:
            raise RuntimeError("Không mở được micro (có thể Windows đang chặn quyền dùng micro cho ứng dụng).")
        self.io.readyRead.connect(lambda: self.buf.extend(self.io.readAll().data()))
        self.active = True

    def stop(self) -> bytes | None:
        if not self.active:
            return None
        self.active = False
        self.buf.extend(self.io.readAll().data())
        self.src.stop()
        return to_wav(bytes(self.buf), self.fmt)


def to_wav(pcm: bytes, fmt) -> bytes | None:
    """Đổi dữ liệu thô của micro (Int16 hoặc Float) sang WAV 16-bit mono."""
    from PySide6.QtMultimedia import QAudioFormat
    import numpy as np
    sf = fmt.sampleFormat()
    data = {QAudioFormat.SampleFormat.Int16: np.int16, QAudioFormat.SampleFormat.Int32: np.int32,
            QAudioFormat.SampleFormat.Float: np.float32, QAudioFormat.SampleFormat.UInt8: np.uint8}[sf]
    a = np.frombuffer(pcm, dtype=data)
    ch = max(fmt.channelCount(), 1)
    if ch > 1:
        a = a[: len(a) // ch * ch].reshape(-1, ch).mean(axis=1)
    if sf == QAudioFormat.SampleFormat.Float:
        a = np.clip(a, -1, 1) * 32767
    elif sf == QAudioFormat.SampleFormat.Int32:
        a = a / 65536
    elif sf == QAudioFormat.SampleFormat.UInt8:
        a = (a.astype(np.float32) - 128) * 256
    a = a.astype(np.int16)[-fmt.sampleRate() * MAX_SECONDS:]  # giữ tối đa MAX_SECONDS giây cuối
    if len(a) < fmt.sampleRate() * 0.4:  # dưới 0,4 giây: coi như chưa nói gì
        return None
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(fmt.sampleRate())
        w.writeframes(a.tobytes())
    return out.getvalue()


class TranscribeWorker(QThread):
    done = Signal(str, str)  # (chữ, lỗi)

    def __init__(self, cfg, wav):
        super().__init__()
        self.cfg, self.wav = cfg, wav

    def run(self):
        try:
            self.done.emit(tools.transcribe(self.wav, self.cfg), "")
        except Exception as e:
            self.done.emit("", f"Không chuyển được giọng nói thành chữ: {str(e)[:200]}")


# ---------- Đọc to ----------

def plain_text(md: str) -> str:
    """Bỏ ký hiệu Markdown / code / công thức để giọng đọc đọc tự nhiên."""
    t = re.sub(r"```.*?(```|\Z)", " (đoạn code) ", md, flags=re.S)
    t = re.sub(r"\$\$.*?\$\$|\\\[.*?\\\]", " (công thức) ", t, flags=re.S)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"^\s*\|?\s*:?-{2,}.*$", "", t, flags=re.M)
    t = re.sub(r"[*_`#>|]+", " ", t)
    t = re.sub(r"\\\(|\\\)", "", t)
    return re.sub(r"[ \t]+", " ", t).strip()


def looks_vietnamese(text: str) -> bool:
    return len(VI_CHARS.findall(text)) >= 3


# ---------- Xuất / chia sẻ đoạn chat ----------

def _img_md(path: str) -> str:
    """Ảnh nhúng thẳng (data URI) để file xuất ra gửi đi vẫn xem được."""
    try:
        return f"\n\n![{Path(path).name}]({tools.image_to_data_url(path, 900)})\n\n"
    except Exception:
        return ""


def transcript_markdown(conv: dict) -> str:
    lines = [f"# {conv.get('title') or 'Đoạn chat'}",
             f"_Xuất từ Agenty ngày {time.strftime('%d/%m/%Y %H:%M')}_", ""]
    for item in conv.get("display", []):
        if item["role"] == "user":
            lines.append("### Bạn")
            if item.get("attachments"):
                lines.append("_Đính kèm: " + ", ".join(item["attachments"]) + "_")
            lines.append(item.get("text", ""))
        else:
            lines.append("### Agenty")
            lines.append(item.get("text", ""))
            if item.get("error"):  # BUG-28: giữ lỗi đã hiện trong chat
                lines.append(f"> **Lỗi:** {item['error']}")
            for f in item.get("images", []):  # ảnh tìm trên mạng
                lines.append(_img_md(f))
            for f in item.get("files", []):
                if Path(f).suffix.lower() in tools.IMAGE_EXTS:
                    lines.append(_img_md(f))
                else:
                    lines.append(f"_Tệp đã tạo: {Path(f).name}_")
        lines.append("")
    return "\n\n".join(lines)


def export(title: str, md: str, dest: str) -> str:
    ext = Path(dest).suffix.lower()
    if ext == ".md":
        Path(dest).write_text(md, "utf-8")
    elif ext == ".html":
        Path(dest).write_text(render.page_html(title, md), "utf-8")
    elif ext == ".pdf":
        from PySide6.QtCore import QMarginsF
        from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument
        doc = QTextDocument()
        c = render.palette("light")
        doc.setDefaultStyleSheet(render.stylesheet(c, 11))
        body, _ = render.to_html(md, c)
        doc.setHtml(body)
        w = QPdfWriter(dest)
        w.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        w.setPageMargins(QMarginsF(16, 16, 16, 16), QPageLayout.Unit.Millimeter)
        w.setTitle(title)
        doc.print_(w)
    elif ext == ".docx":
        from office_helpers import convert_file
        tmp = Path(tools.OUTPUT_DIR.parent / "converted" / f"_chia_se_{int(time.time())}.html")
        tmp.parent.mkdir(exist_ok=True)
        tmp.write_text(render.page_html(title, md), "utf-8")
        try:
            Path(convert_file(str(tmp), "docx", out_dir=str(tmp.parent))).replace(dest)
        except Exception:  # máy không có Word / WPS: bản Word đơn giản bằng python-docx
            import docx
            d = docx.Document()
            for line in md.splitlines():
                if line.startswith("# "):
                    d.add_heading(line[2:], 0)
                elif line.startswith("### "):
                    d.add_heading(line[4:], 2)
                elif line.strip() and not line.startswith("!["):
                    d.add_paragraph(line)
            d.save(dest)
    else:
        raise ValueError(f"Không hỗ trợ định dạng {ext}")
    return dest
