"""Giao diện PySide6 bố cục kiểu Agenty desktop: thanh tiêu đề tự vẽ, cột icon, thanh bên, chủ đề Tối/Sáng."""
import contextlib
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, QStandardPaths, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QCursor, QGuiApplication, QIcon, QPainter, QPainterPath, QPalette, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton,
                               QScrollArea, QSizePolicy, QTextBrowser, QTextEdit, QToolButton, QVBoxLayout, QWidget, QWidgetAction)

import config as C
import icons
import memory
import render
import voice
import shortcuts
import skills
from agent import Callbacks, build_user_message, compact_history, friendly_error, run_agent
from llm import list_models
from tools import IMAGE_EXTS

MODELS = [  # (id, tên hiển thị, mô tả)
    ("gpt-5.6-sol", "GPT 5.6 Sol", "Tác vụ nhẹ"),
    ("gpt-6-luna", "GPT 6 Luna", "Trung bình"),
    ("gpt-6.1-sol", "GPT 6.1 Sol", "Mạnh"),
    ("gpt-6-astra", "GPT 6 Astra", "Rất mạnh"),
]
EFFORTS = [("low", "Thấp"), ("medium", "Vừa"), ("high", "Cao")]
IMAGE_MODELS = ["gpt-image-2.5", "gpt-image-2.5-sunburst", "gpt-image-2.5-flare", "gemini-3.1-flash-image"]
QUICK_ACTIONS = [
    ("image", "Tạo ảnh", "Vẽ ảnh: "),
    ("pencil", "Viết hoặc chỉnh sửa", "Giúp mình viết "),
    ("globe", "Tìm kiếm trên web", "Tìm trên web: "),
    ("file", "Tạo bài thuyết trình", "Tạo bài thuyết trình PowerPoint về "),
]
FILE_TILES = {".pptx": ("#D35230", "P", "Bài thuyết trình PowerPoint"), ".docx": ("#2B579A", "W", "Tài liệu Word"),
              ".xlsx": ("#217346", "X", "Bảng tính Excel"), ".pdf": ("#C4302B", "PDF", "Tài liệu PDF")}
FONT_SIZES = {"small": 14, "medium": 15, "large": 17}
CHAT_WIDTHS = {"normal": 780, "wide": 1040}

THEMES = {
    "dark": dict(INK="#ECECEC", MUTED="#AFAFAF", FAINT="#8F8F8F", BG="#212121", SIDEBAR="#181818", TITLE="#131315",
                 SURFACE="#303030", HOVER="#2F2F2F", ROW_HOVER="#232323", SEL="#2A2A2A", LINE="#3A3A3A",
                 CHIP="#3A3A3A", MENU="#2F2F2F", MENU_LINE="#454545", MENU_HL="#424242", LINK="#7AB7FF",
                 DANGER="#F28B82", ON_INK="#0D0D0D", ACCENT="#4C6EF5", ACCENT_OFF="#323B66", CARD="#2A2A2A",
                 ERR_BG="#3A2524", ERR_LINE="#6B3B38", ERR_TEXT="#FFD2CE", OK="#81C995", SCROLL="#4A4A4A"),
    "light": dict(INK="#0D0D0D", MUTED="#5D5D5D", FAINT="#7A7A7A", BG="#FFFFFF", SIDEBAR="#F9F9F9", TITLE="#EFEFEF",
                  SURFACE="#F4F4F4", HOVER="#ECECEC", ROW_HOVER="#EFEFEF", SEL="#E5E5E5", LINE="#DADADA",
                  CHIP="#E6E6E6", MENU="#FFFFFF", MENU_LINE="#E3E3E3", MENU_HL="#F0F0F0", LINK="#1A6BD8",
                  DANGER="#C5221F", ON_INK="#FFFFFF", ACCENT="#3B5BDB", ACCENT_OFF="#B9C5EE", CARD="#F7F7F7",
                  ERR_BG="#FDECEA", ERR_LINE="#F2B8B5", ERR_TEXT="#7F1D1D", OK="#1E7E34", SCROLL="#C8C8C8"),
}
# Các biến màu dùng chung (được set_theme() ghi đè); chữ chính/nền ≥ 12:1, chữ phụ/nền ≥ 4.5:1 ở cả hai chủ đề.
INK = MUTED = FAINT = BG = SIDEBAR = TITLE = SURFACE = HOVER = ROW_HOVER = SEL = LINE = CHIP = MENU = MENU_LINE = ""
MENU_HL = LINK = DANGER = ON_INK = ACCENT = ACCENT_OFF = CARD = ERR_BG = ERR_LINE = ERR_TEXT = OK = SCROLL = ""
FS = 15


def set_theme(theme: str, font: str):
    global FS
    globals().update(THEMES.get(theme, THEMES["dark"]))
    FS = FONT_SIZES.get(font, 15)


set_theme("dark", "medium")


def build_qss(arrow: str) -> str:
    return f"""
* {{ font-family: "Segoe UI"; font-size: {FS}px; color: {INK}; }}
QMainWindow, #Main, #ChatArea, #ChatColumn, #Home, QDialog, QMessageBox {{ background: {BG}; }}
#Root, #TitleBar, #Rail {{ background: {TITLE}; }}
#Sidebar {{ background: {SIDEBAR}; border-top-left-radius: 12px; border-right: 1px solid {LINE}; }}
#Main {{ border-top-right-radius: 0px; }}
#Brand {{ font-size: {FS + 3}px; font-weight: 600; }}
#Muted {{ color: {MUTED}; }}
#SectionLabel {{ color: {FAINT}; font-size: {FS - 1}px; padding: 12px 10px 4px 10px; }}
#Hello {{ font-size: {FS + 14}px; }}
#DialogTitle {{ font-size: {FS + 6}px; font-weight: 600; }}
#GroupTitle {{ font-size: {FS}px; font-weight: 600; padding-top: 6px; }}
QPushButton {{ background: transparent; border: 1px solid {LINE}; border-radius: 10px; padding: 7px 14px; min-height: 22px; }}
QPushButton:hover {{ background: {HOVER}; }}
QPushButton:focus {{ border: 1px solid {LINK}; }}
QPushButton:disabled {{ color: {FAINT}; border-color: {LINE}; }}
QPushButton#Primary {{ background: {INK}; color: {ON_INK}; border: none; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {MUTED}; }}
QPushButton#Ghost {{ border: none; text-align: left; padding: 8px 10px; border-radius: 10px; }}
QPushButton#Ghost:hover {{ background: {ROW_HOVER}; }}
QPushButton#Quick {{ border: none; text-align: left; padding: 9px 12px; border-radius: 10px; color: {MUTED}; }}
QPushButton#Quick:hover {{ background: {HOVER}; color: {INK}; }}
QPushButton#Small {{ border: none; color: {MUTED}; font-size: {FS - 2}px; padding: 4px 8px; min-height: 18px; }}
QPushButton#Small:hover {{ background: {HOVER}; color: {INK}; }}
QPushButton#Pill {{ border: none; border-radius: 16px; padding: 6px 10px; color: {MUTED}; font-size: {FS - 1}px; min-height: 22px; }}
QPushButton#Pill:hover {{ background: {CHIP}; color: {INK}; }}
QPushButton#Seg {{ border: 1px solid {LINE}; border-radius: 9px; padding: 6px 14px; color: {MUTED}; }}
QPushButton#Seg:checked {{ background: {INK}; color: {ON_INK}; border-color: {INK}; font-weight: 600; }}
QPushButton#Danger {{ color: {DANGER}; border: 1px solid {ERR_LINE}; font-weight: 600; }}
QPushButton#Danger:hover {{ background: {ERR_BG}; }}
QPushButton#Chip {{ background: {CHIP}; border: none; border-radius: 12px; padding: 5px 12px; font-size: {FS - 2}px; }}
QPushButton#MenuRow {{ border: none; border-radius: 8px; padding: 0; background: transparent; }}
QPushButton#MenuRow:hover, QPushButton#MenuRow:focus {{ background: {MENU_HL}; border: none; }}
QPushButton#TitleMenu {{ border: none; border-radius: 6px; padding: 4px 10px; color: {MUTED}; font-size: {FS - 1}px; min-height: 20px; }}
QPushButton#TitleMenu:hover {{ background: {HOVER}; color: {INK}; }}
QToolButton#IconBtn, QToolButton#RailBtn {{ border: none; border-radius: 8px; background: transparent; }}
QToolButton#IconBtn:hover, QToolButton#RailBtn:hover {{ background: {HOVER}; }}
QToolButton#RailBtn:checked {{ background: {CHIP}; }}
QToolButton#WinBtn {{ border: none; background: transparent; }}
QToolButton#WinBtn:hover {{ background: {HOVER}; }}
QToolButton#WinClose {{ border: none; background: transparent; }}
QToolButton#WinClose:hover {{ background: #C42B1C; }}
QToolButton#RoundGhost {{ border: none; border-radius: 18px; background: transparent; }}
QToolButton#RoundGhost:hover {{ background: {CHIP}; }}
QToolButton#Send {{ border: none; border-radius: 18px; background: {ACCENT}; }}
QToolButton#Send:disabled {{ background: {ACCENT_OFF}; }}
QToolButton#Thumb {{ border: 1px solid {LINE}; border-radius: 10px; padding: 2px; background: {SURFACE}; }}
QToolButton#Thumb:hover {{ border-color: {LINK}; }}
QComboBox {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 10px; padding: 7px 12px; min-height: 22px; }}
QComboBox:focus {{ border: 1px solid {LINK}; }}
QLineEdit {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 10px; padding: 7px 12px; min-height: 22px; }}
QLineEdit#Search {{ background: {ROW_HOVER}; border: 1px solid {LINE}; border-radius: 10px; padding: 6px 10px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 28px; border: none; }}
QComboBox::down-arrow {{ image: url({arrow}); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{ background: {MENU}; border: 1px solid {MENU_LINE}; padding: 4px; outline: none; selection-background-color: {MENU_HL}; selection-color: {INK}; }}
#Composer {{ background: {SURFACE}; border-radius: 28px; border: 1px solid {LINE}; }}
QTextEdit#Input {{ background: transparent; border: none; padding: 4px 4px; font-size: {FS + 1}px; }}
#ChatRow {{ border-radius: 10px; background: transparent; }}
#ChatRow:hover {{ background: {ROW_HOVER}; }}
#ChatRow[selected="true"] {{ background: {SEL}; }}
#UserBubble {{ background: {SURFACE}; border-radius: 18px; }}
#FileCard {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 14px; }}
#FileName {{ font-weight: 600; }}
#ErrorBox {{ background: {ERR_BG}; border: 1px solid {ERR_LINE}; border-radius: 12px; color: {ERR_TEXT}; padding: 12px; }}
QCheckBox {{ spacing: 8px; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ width: 10px; background: transparent; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {SCROLL}; border-radius: 4px; min-height: 48px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical, QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ height: 0; background: none; }}
QToolTip {{ background: {MENU}; color: {INK}; border: 1px solid {MENU_LINE}; padding: 6px 8px; font-size: {FS - 2}px; }}
QMenu {{ background: {MENU}; border: 1px solid {MENU_LINE}; padding: 5px; }}
QMenu::item {{ padding: 7px 28px 7px 12px; border-radius: 6px; font-size: {FS - 1}px; }}
QMenu::item:selected {{ background: {MENU_HL}; }}
QMenu::item:disabled {{ color: {FAINT}; }}
QMenu::separator {{ height: 1px; background: {MENU_LINE}; margin: 5px 8px; }}
QMenu#Pop {{ background: {MENU}; border: 1px solid {MENU_LINE}; border-radius: 14px; padding: 6px; }}
"""


def apply_theme(app: QApplication, theme="dark", font="medium"):
    """Áp chủ đề màu + cỡ chữ cho toàn app (gọi trước khi dựng cửa sổ)."""
    global CURRENT_THEME
    CURRENT_THEME = theme
    set_theme(theme, font)
    app.setStyle("Fusion")
    with contextlib.suppress(AttributeError):  # Qt < 6.8 chưa có setColorScheme
        app.styleHints().setColorScheme(Qt.ColorScheme.Light if theme == "light" else Qt.ColorScheme.Dark)
    pal = QPalette()
    for role, color in ((QPalette.ColorRole.Window, BG), (QPalette.ColorRole.Base, SURFACE),
                        (QPalette.ColorRole.AlternateBase, SIDEBAR), (QPalette.ColorRole.Text, INK),
                        (QPalette.ColorRole.WindowText, INK), (QPalette.ColorRole.ButtonText, INK),
                        (QPalette.ColorRole.Button, SURFACE), (QPalette.ColorRole.Highlight, ACCENT),
                        (QPalette.ColorRole.HighlightedText, "#FFFFFF"), (QPalette.ColorRole.Link, LINK),
                        (QPalette.ColorRole.PlaceholderText, FAINT), (QPalette.ColorRole.ToolTipBase, MENU),
                        (QPalette.ColorRole.ToolTipText, INK)):
        pal.setColor(role, QColor(color))
    app.setPalette(pal)
    arrow = C.APP_DIR / f"arrow_{theme}.svg"
    arrow.write_bytes(icons.svg("chevron-down", MUTED))
    app.setStyleSheet(build_qss(arrow.as_posix()))


# ---------- tiện ích ----------

def find_asset(name: str) -> Path | None:
    """logo.png / icon.ico đặt cạnh .exe hoặc nhúng lúc build."""
    bases = [Path(sys._MEIPASS)] if hasattr(sys, "_MEIPASS") else []
    for base in bases + [C.app_base_dir()]:
        if (base / name).is_file():
            return base / name
    return None


def logo_pixmap(size: int) -> QPixmap | None:
    """Logo tô theo màu chữ của chủ đề (logo gốc là nét trắng trên nền trong suốt)."""
    path = find_asset("logo.png")
    if not path:
        return None
    scale = 3
    src = QPixmap(str(path)).scaled(size * scale, size * scale, Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation)
    p = QPainter(src)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    p.fillRect(src.rect(), QColor(INK))
    p.end()
    src.setDevicePixelRatio(scale)
    return src


def human_size(n: int) -> str:
    for unit in ("byte", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "byte" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024


def downloads_dir() -> str:
    return QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)


def open_file(path: str, parent=None):
    try:
        os.startfile(path)  # mở bằng PowerPoint/Word/Excel/trình xem ảnh trên Windows
    except OSError as e:
        QMessageBox.warning(parent, "Không mở được file", f"Máy chưa có phần mềm mở được file này.\n\n{e}")


def save_copy(parent, path: str, button: QPushButton):
    """Tải (chép) file ra nơi người dùng chọn, mặc định thư mục Downloads."""
    p = Path(path)
    dest, _ = QFileDialog.getSaveFileName(parent, "Tải xuống", str(Path(downloads_dir()) / p.name),
                                          f"{p.suffix.upper()[1:]} (*{p.suffix});;Tất cả (*.*)")
    if not dest:
        return
    try:
        shutil.copy2(p, dest)
    except OSError as e:
        QMessageBox.warning(parent, "Không tải được", f"Không lưu được file.\n\n{e}")
        return
    old = button.text()
    button.setText("Đã tải ✓")
    QTimer.singleShot(2000, lambda: button.setText(old))


def icon_button(name, tip, size=18, box=32, color=None, obj="IconBtn") -> QToolButton:
    b = QToolButton()
    b.setObjectName(obj)
    b.setIcon(icons.icon(name, color or MUTED, size))
    b.setIconSize(QSize(size, size))
    b.setFixedSize(box, box)
    b.setToolTip(tip)
    b.setAccessibleName(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def rounded(pm: QPixmap, radius: int) -> QPixmap:
    out = QPixmap(pm.size())
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, pm.width(), pm.height(), radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, pm)
    p.end()
    return out


CURRENT_THEME = "dark"


class MarkdownView(QTextBrowser):
    """Câu trả lời: Markdown đầy đủ (bảng, code tô màu + nút sao chép, công thức LaTeX), tự cao theo nội dung."""

    def __init__(self, text=""):
        super().__init__()
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setOpenLinks(False)
        self.anchorClicked.connect(self._link)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("QTextBrowser { background: transparent; border: none; }")
        self.viewport().setAutoFillBackground(False)
        self.document().setDocumentMargin(0)
        self.document().setDefaultStyleSheet(render.stylesheet(render.palette(CURRENT_THEME), FS + 1))
        self.codes: list[str] = []
        self.set_markdown(text)

    def set_markdown(self, text: str):
        html_, self.codes = render.to_html(text, render.palette(CURRENT_THEME))
        self.setHtml(html_)
        self._fit()

    def _fit(self):
        self.document().setTextWidth(self.viewport().width())
        self.setFixedHeight(int(self.document().size().height()) + 6)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()

    def wheelEvent(self, e):
        e.ignore()  # để khung chat bên ngoài cuộn

    def _link(self, url):
        if url.scheme() == "copy":
            with contextlib.suppress(ValueError, IndexError):
                QGuiApplication.clipboard().setText(self.codes[int(url.path() or url.host())])
        else:
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(url)


def md_label(text="") -> MarkdownView:
    return MarkdownView(text)


class PopMenu(QMenu):
    """Menu nổi bo góc, mỗi dòng có icon, chữ, mô tả và phím tắt (kiểu Agenty / Claude)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Pop")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.hotkeys = {}

    def row(self, text, callback, icon_name=None, right="", right_icon=None, color=None, sub=""):
        color = color or INK
        btn = QPushButton()
        btn.setObjectName("MenuRow")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumSize(270, 40)
        btn.setAccessibleName(text)
        lay = QHBoxLayout(btn)
        lay.setContentsMargins(10, 0, 12, 0)
        lay.setSpacing(10)
        parts = []
        if icon_name:
            ic = QLabel()
            ic.setPixmap(icons.pixmap(icon_name, color, 18))
            parts.append(ic)
        t = QLabel(text)
        t.setStyleSheet(f"color: {color}; background: transparent;")
        parts.append(t)
        if sub:
            s = QLabel(sub)
            s.setStyleSheet(f"color: {MUTED}; font-size: {FS - 2}px; background: transparent;")
            parts.append(s)
        for w in parts:
            lay.addWidget(w)
        lay.addStretch()
        if right_icon:
            r = QLabel()
            r.setPixmap(icons.pixmap(right_icon, LINK, 18))
            parts.append(r)
            lay.addWidget(r)
        elif right:
            r = QLabel(right)
            r.setStyleSheet(f"color: {FAINT}; font-size: {FS - 2}px; background: transparent;")
            parts.append(r)
            lay.addWidget(r)
        for w in parts:
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        act = QWidgetAction(self)
        act.setDefaultWidget(btn)
        self.addAction(act)
        btn.clicked.connect(lambda: (self.close(), callback()))
        return btn

    def keyPressEvent(self, e):
        cb = self.hotkeys.get(e.key())
        if cb:
            self.close()
            cb()
            return
        super().keyPressEvent(e)

    def popup_above(self, anchor: QWidget):
        size = self.sizeHint()
        self.exec(anchor.mapToGlobal(QPoint(anchor.width() - size.width(), -size.height() - 6)))


# ---------- Thẻ file / ảnh ----------

class FileCard(QFrame):
    def __init__(self, path: str):
        super().__init__()
        self.setObjectName("FileCard")
        self.path = path
        p = Path(path)
        color, letter, kind = FILE_TILES.get(p.suffix.lower(), (None, "", "Tệp"))
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 12, 14, 12)
        row.setSpacing(12)
        tile = QLabel(letter)
        tile.setFixedSize(44, 44)
        tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if color:
            tile.setStyleSheet(f"background: {color}; color: white; border-radius: 10px; font-weight: 700; "
                               f"font-size: {17 if len(letter) == 1 else 12}px;")
        else:
            tile.setStyleSheet(f"background: {CHIP}; border-radius: 10px;")
            tile.setPixmap(icons.pixmap("file", INK, 20))
        row.addWidget(tile)
        col = QVBoxLayout()
        col.setSpacing(2)
        name = QLabel(p.name)
        name.setObjectName("FileName")
        name.setWordWrap(True)
        where = "" if p.parent == C.OUTPUT_DIR else f" · {p.parent}"
        meta = QLabel(f"{kind} · {human_size(p.stat().st_size)}{where}" if p.exists() else "File không còn trên máy")
        meta.setObjectName("Muted")
        meta.setWordWrap(True)
        meta.setStyleSheet(f"font-size: {FS - 2}px;")
        col.addWidget(name)
        col.addWidget(meta)
        row.addLayout(col, 1)
        b_open = QPushButton("Mở")
        b_open.setIcon(icons.icon("open", INK, 15))
        b_open.clicked.connect(lambda: open_file(self.path, self))
        b_dl = QPushButton("Tải xuống")
        b_dl.setObjectName("Primary")
        b_dl.setIcon(icons.icon("download", ON_INK, 15))
        b_dl.clicked.connect(lambda: save_copy(self, self.path, b_dl))
        for b in (b_open, b_dl):
            b.setEnabled(p.exists())
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            row.addWidget(b)


class ImageCard(QWidget):
    """Ảnh AI vẽ: hiện to trong khung chat, có nút Tải ảnh riêng."""

    def __init__(self, path: str):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        pic = QToolButton()
        pic.setObjectName("IconBtn")
        pic.setCursor(Qt.CursorShape.PointingHandCursor)
        pic.setToolTip("Bấm để xem ảnh to")
        pm = QPixmap(path)
        if not pm.isNull():
            pm = rounded(pm.scaled(460, 460, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation), 16)
            pic.setIcon(QIcon(pm))
            pic.setIconSize(pm.size())
            pic.setFixedSize(pm.size())
        pic.clicked.connect(lambda: open_file(path, self))
        v.addWidget(pic)
        row = QHBoxLayout()
        dl = QPushButton("Tải ảnh")
        dl.setObjectName("Primary")
        dl.setIcon(icons.icon("download", ON_INK, 15))
        dl.clicked.connect(lambda: save_copy(self, path, dl))
        op = QPushButton("Mở")
        op.setIcon(icons.icon("open", INK, 15))
        op.clicked.connect(lambda: open_file(path, self))
        for b in (dl, op):
            b.setEnabled(Path(path).exists())
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            row.addWidget(b)
        row.addStretch()
        v.addLayout(row)


class ImageStrip(QWidget):
    """Ảnh tìm được trên mạng: bấm để xem, mỗi ảnh có nút tải riêng."""

    def __init__(self, paths):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        cap = QLabel("Ảnh tìm được trên mạng")
        cap.setObjectName("Muted")
        cap.setStyleSheet(f"font-size: {FS - 2}px;")
        v.addWidget(cap)
        row = QHBoxLayout()
        row.setSpacing(10)
        for path in paths:
            if not Path(path).exists():
                continue
            col = QVBoxLayout()
            col.setSpacing(4)
            b = QToolButton()
            b.setObjectName("Thumb")
            b.setIcon(QIcon(QPixmap(path)))
            b.setIconSize(QSize(140, 104))
            b.setToolTip("Bấm để mở ảnh")
            b.setAccessibleName(f"Ảnh {Path(path).name}")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, p=path: open_file(p, self))
            dl = QPushButton("Tải")
            dl.setObjectName("Small")
            dl.setIcon(icons.icon("download", MUTED, 14))
            dl.clicked.connect(lambda _=False, p=path, btn=dl: save_copy(self, p, btn))
            col.addWidget(b)
            col.addWidget(dl, 0, Qt.AlignmentFlag.AlignLeft)
            row.addLayout(col)
        row.addStretch()
        v.addLayout(row)


# ---------- Tin nhắn ----------

class UserMessage(QWidget):
    """Tin nhắn người dùng; di chuột vào hiện nút Sao chép / Sửa, sửa ngay trong bong bóng như Agenty."""

    def __init__(self, text, attachments=(), on_edit=None):
        super().__init__()
        self.text, self.on_edit = text, on_edit
        outer = QVBoxLayout(self)
        outer.setContentsMargins(80, 6, 0, 2)
        outer.setSpacing(2)
        row = QHBoxLayout()
        row.addStretch()
        self.bubble = QFrame()
        self.bubble.setObjectName("UserBubble")
        self.bv = QVBoxLayout(self.bubble)
        self.bv.setContentsMargins(18, 10, 18, 10)
        self.bv.setSpacing(6)
        for name in attachments:
            a = QHBoxLayout()
            ic = QLabel()
            ic.setPixmap(icons.pixmap("clip", MUTED, 14))
            lb = QLabel(name)
            lb.setStyleSheet(f"color: {MUTED}; font-size: {FS - 2}px;")
            a.addWidget(ic)
            a.addWidget(lb)
            a.addStretch()
            self.bv.addLayout(a)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.label.setStyleSheet(f"font-size: {FS + 1}px;")
        # QLabel tự xuống dòng thì co rất hẹp; đặt bề rộng tối thiểu theo độ dài chữ
        self.label.setMinimumWidth(min(self.label.fontMetrics().horizontalAdvance(text) + 8, 560))
        self.label.setVisible(bool(text))
        self.bv.addWidget(self.label)
        self.bubble.setMaximumWidth(640)
        row.addWidget(self.bubble)
        outer.addLayout(row)

        self.actions = QWidget()
        ar = QHBoxLayout(self.actions)
        ar.setContentsMargins(0, 0, 0, 0)
        ar.setSpacing(2)
        ar.addStretch()
        self.copy_btn = icon_button("copy", "Sao chép", 15, 28)
        self.copy_btn.clicked.connect(lambda: _flash_copy(self.copy_btn, self.text))
        ar.addWidget(self.copy_btn)
        if on_edit:
            edit = icon_button("pencil", "Sửa tin nhắn", 15, 28)
            edit.clicked.connect(self.start_edit)
            ar.addWidget(edit)
        self.actions.setFixedHeight(28)
        outer.addWidget(self.actions)
        self.actions.setVisible(False)
        self.editor = None

    def enterEvent(self, e):
        self.actions.setVisible(self.editor is None)

    def leaveEvent(self, e):
        self.actions.setVisible(False)

    def start_edit(self):
        self.actions.setVisible(False)
        self.label.hide()
        self.bubble.setMaximumWidth(16777215)
        self.bubble.setMinimumWidth(min(620, max(360, self.width() - 100)))
        self.editor = QTextEdit()
        self.editor.setObjectName("Input")
        self.editor.setAcceptRichText(False)
        self.editor.setPlainText(self.text)
        self.editor.setMinimumHeight(90)
        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("Huỷ")
        send = QPushButton("Gửi")
        send.setObjectName("Primary")
        cancel.clicked.connect(self.cancel_edit)
        send.clicked.connect(lambda: self.on_edit(self.editor.toPlainText().strip()))
        btns.addWidget(cancel)
        btns.addWidget(send)
        self._edit_btns = btns
        self.bv.addWidget(self.editor)
        self.bv.addLayout(btns)
        self.editor.setFocus()

    def cancel_edit(self):
        self.bv.removeWidget(self.editor)
        self.editor.deleteLater()
        while self._edit_btns.count():
            w = self._edit_btns.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.bv.removeItem(self._edit_btns)
        self._edit_btns.deleteLater()
        self.editor = None
        self.bubble.setMinimumWidth(0)
        self.bubble.setMaximumWidth(640)
        self.label.setVisible(bool(self.text))


def _flash_copy(btn, text):
    QGuiApplication.clipboard().setText(text)
    btn.setIcon(icons.icon("check", MUTED, 15))
    QTimer.singleShot(1800, lambda: btn.setIcon(icons.icon("copy", MUTED, 15)))


class AssistantMessage(QWidget):
    """Câu trả lời: Markdown đầy đủ + hàng nút Sao chép / Đọc to / Tạo lại (chỉ câu trả lời mới nhất)."""

    def __init__(self, text="", on_speak=None):
        super().__init__()
        self.buf = text
        self.on_speak = on_speak
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 6, 0, 10)
        v.setSpacing(10)
        self.steps = QVBoxLayout()
        self.steps.setSpacing(4)
        v.addLayout(self.steps)
        self.text = md_label(text)
        self.text.setVisible(bool(text))
        v.addWidget(self.text)
        self.extras = QVBoxLayout()
        self.extras.setSpacing(10)
        v.addLayout(self.extras)
        self.actions = QWidget()
        ar = QHBoxLayout(self.actions)
        ar.setContentsMargins(0, 0, 0, 0)
        ar.setSpacing(2)
        self.copy_btn = icon_button("copy", "Sao chép", 15, 30)
        self.copy_btn.clicked.connect(lambda: _flash_copy(self.copy_btn, self.buf))
        ar.addWidget(self.copy_btn)
        self.speak_btn = icon_button("volume", "Đọc to", 15, 30)
        self.speak_btn.clicked.connect(lambda: self.on_speak and self.on_speak(self))
        ar.addWidget(self.speak_btn)
        self.regen_btn = icon_button("refresh", "Tạo lại câu trả lời", 15, 30)
        self.regen_btn.hide()
        ar.addWidget(self.regen_btn)
        ar.addStretch()
        v.addWidget(self.actions)
        self.actions.setVisible(bool(text))
        self._timer = QTimer(self, singleShot=True, interval=90)
        self._timer.timeout.connect(lambda: self.text.set_markdown(self.buf))
        self._current_step = None

    def set_regenerate(self, callback):
        """Gắn / bỏ nút Tạo lại (chỉ câu trả lời cuối cùng có)."""
        if getattr(self, "_regen_cb", None):
            self.regen_btn.clicked.disconnect(self._regen_cb)
        self._regen_cb = callback
        if callback:
            self.regen_btn.clicked.connect(callback)
        self.regen_btn.setVisible(bool(callback))

    def set_speaking(self, on: bool):
        self.speak_btn.setIcon(icons.icon("stop" if on else "volume", MUTED, 13 if on else 15))
        self.speak_btn.setToolTip("Dừng đọc" if on else "Đọc to")

    def append(self, delta):
        self.buf += delta
        self.text.setVisible(True)
        if not self._timer.isActive():
            self._timer.start()

    def add_step(self, status):
        if self._current_step:
            self._current_step.setStyleSheet(f"color: {FAINT}; font-size: {FS - 1}px;")
        lb = QLabel(status)
        lb.setWordWrap(True)
        lb.setStyleSheet(f"color: {MUTED};")
        self.steps.addWidget(lb)
        self._current_step = lb

    def add_files(self, paths):
        for p in paths:
            self.extras.addWidget(ImageCard(p) if Path(p).suffix.lower() in IMAGE_EXTS else FileCard(p))

    def add_images(self, paths):
        self.extras.addWidget(ImageStrip(paths))

    def show_error(self, msg):
        lb = QLabel(msg)
        lb.setObjectName("ErrorBox")
        lb.setWordWrap(True)
        lb.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.extras.addWidget(lb)

    def finish(self):
        self._timer.stop()
        self.text.set_markdown(self.buf)
        if self._current_step:
            self._current_step.setStyleSheet(f"color: {FAINT}; font-size: {FS - 1}px;")
        self.actions.setVisible(True)
        self.copy_btn.setVisible(bool(self.buf.strip()))
        self.speak_btn.setVisible(bool(self.buf.strip()))


# ---------- Ô nhập ----------

class InputBox(QTextEdit):
    send = Signal()
    files_dropped = Signal(list)

    def __init__(self, enter_sends=True):
        super().__init__()
        self.enter_sends = enter_sends
        self.setObjectName("Input")
        self.setPlaceholderText("Hỏi Agenty")
        self.setAcceptRichText(False)
        self.document().contentsChanged.connect(self._grow)
        self._grow()

    def _grow(self):
        h = int(self.document().size().height()) + 10
        self.setFixedHeight(max(38, min(h, 240)))

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            shift = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            ctrl = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
            if (self.enter_sends and not shift) or (not self.enter_sends and ctrl):
                self.send.emit()
                return
        super().keyPressEvent(e)

    def canInsertFromMimeData(self, source):
        return source.hasUrls() or source.hasImage() or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        if source.hasUrls() and all(u.isLocalFile() for u in source.urls()):
            self.files_dropped.emit([u.toLocalFile() for u in source.urls()])
        elif source.hasImage():  # dán ảnh chụp màn hình
            path = C.UPLOADS_DIR / f"anh_dan_{uuid.uuid4().hex[:6]}.png"
            source.imageData().save(str(path))
            self.files_dropped.emit([str(path)])
        else:
            super().insertFromMimeData(source)


# ---------- Dòng đoạn chat ở thanh bên ----------

class ChatRow(QFrame):
    def __init__(self, win, meta, selected):
        super().__init__()
        self.win, self.cid, self.pinned, self.full = win, meta["id"], meta["pinned"], meta["title"]
        self.setObjectName("ChatRow")
        self.setProperty("selected", selected)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(self.full)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 4, 0)
        lay.setSpacing(0)
        self.title = QLabel()
        self.title.setStyleSheet("background: transparent;")
        lay.addWidget(self.title, 1)
        self.pin_btn = icon_button("pin", "Bỏ ghim" if self.pinned else "Ghim", 15, 28)
        self.pin_btn.clicked.connect(lambda: win.toggle_pin(self.cid))
        self.more = icon_button("more", "Tuỳ chọn", 18, 28, INK)
        self.more.clicked.connect(lambda: win.chat_menu(self.cid, anchor=self.more))
        lay.addWidget(self.pin_btn)
        lay.addWidget(self.more)
        self._hover(False)

    def _hover(self, on):
        self.more.setVisible(on)
        self.pin_btn.setVisible(on or self.pinned)
        self._elide()

    def _elide(self):
        room = self.width() - 20 - (60 if self.more.isVisible() else 34 if self.pinned else 0)
        self.title.setText(self.title.fontMetrics().elidedText(self.full, Qt.TextElideMode.ElideRight, max(room, 40)))

    def enterEvent(self, e):
        self._hover(True)

    def leaveEvent(self, e):
        self._hover(False)

    def resizeEvent(self, e):
        self._elide()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            self.win.chat_menu(self.cid, pos=e.globalPosition().toPoint())
        elif e.button() == Qt.MouseButton.LeftButton:
            self.win.open_chat(self.cid)


# ---------- Thanh tiêu đề tự vẽ ----------

class TitleBar(QFrame):
    HEIGHT = 40

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("TitleBar")
        self.setFixedHeight(self.HEIGHT)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 0, 0)
        lay.setSpacing(2)
        toggle = icon_button("sidebar", "Ẩn / hiện thanh bên (Ctrl+Shift+S)", 17, 30)
        toggle.clicked.connect(win.toggle_sidebar)
        lay.addWidget(toggle)
        lay.addSpacing(6)
        for name, menu in win.title_menus:
            b = QPushButton(name)
            b.setObjectName("TitleMenu")
            b.clicked.connect(lambda _=False, m=menu, btn=b: m.exec(btn.mapToGlobal(QPoint(0, btn.height() + 2))))
            lay.addWidget(b)
        lay.addStretch()
        self.btn_min = icon_button("minimize", "Thu nhỏ", 14, 46, MUTED, "WinBtn")
        self.btn_max = icon_button("maximize", "Phóng to", 13, 46, MUTED, "WinBtn")
        self.btn_close = icon_button("x", "Đóng", 15, 46, MUTED, "WinClose")
        for b in (self.btn_min, self.btn_max, self.btn_close):
            b.setFixedSize(46, self.HEIGHT)
            lay.addWidget(b)
        self.btn_min.clicked.connect(win.showMinimized)
        self.btn_max.clicked.connect(win.toggle_maximize)
        self.btn_close.clicked.connect(win.close)

    def set_maximized(self, on):
        self.btn_max.setIcon(icons.icon("restore" if on else "maximize", MUTED, 13))
        self.btn_max.setToolTip("Thu về" if on else "Phóng to")

    def is_drag_area(self, pos: QPoint) -> bool:
        child = self.childAt(pos)
        return child is None or isinstance(child, QLabel)


# ---------- Luồng chạy nền ----------

class AgentWorker(QThread, Callbacks):
    sig_delta = Signal(str)
    sig_status = Signal(str)
    sig_files = Signal(list)
    sig_images = Signal(list)
    sig_error = Signal(str)

    def __init__(self, cfg, model, messages, pending=None):
        QThread.__init__(self)
        self.cfg, self.model, self.messages = cfg, model, messages
        self.pending = pending  # (chữ, file đính kèm) của tin nhắn mới — đọc file ở luồng này
        self._stop = False

    def delta(self, t): self.sig_delta.emit(t)
    def status(self, t): self.sig_status.emit(t)
    def files(self, p): self.sig_files.emit(p)
    def images(self, p): self.sig_images.emit(p)
    def stopped(self): return self._stop
    def stop(self): self._stop = True

    def run(self):
        if self.pending is not None:
            self.status("Đang đọc file đính kèm…" if self.pending[1] else "Đang suy nghĩ…")
            try:
                self.messages.append(build_user_message(*self.pending))
            except Exception as e:
                self.sig_error.emit(f"Không đọc được file đính kèm: {str(e)[:300]}")
                return
        try:
            run_agent(self.cfg, self.model, self.messages, self)
        except Exception as e:
            self.sig_error.emit(friendly_error(e))


class _Call(QThread):
    """Chạy một hàm chặn (mạng...) ở luồng nền rồi báo kết quả về giao diện."""
    done = Signal(object, object)  # (kết quả, lỗi)

    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args

    def run(self):
        try:
            self.done.emit(self.fn(*self.args), None)
        except Exception as e:
            self.done.emit(None, e)


_BG = set()  # giữ luồng nền sống tới khi xong, kể cả khi hộp thoại đã đóng


def wait_background(timeout_ms=12000):
    """Gọi khi thoát app: QThread bị huỷ lúc còn chạy sẽ làm tiến trình crash."""
    for t in list(_BG):
        t.wait(timeout_ms)


import atexit  # noqa: E402
atexit.register(wait_background)


def run_bg(fn, *args, on_done=None) -> _Call:
    t = _Call(fn, *args)
    _BG.add(t)
    t.finished.connect(lambda: _BG.discard(t))
    if on_done:
        t.done.connect(on_done)
    t.start()
    return t


# ---------- Hộp Bộ nhớ ----------

class MemoryDialog(QDialog):
    """Xem / xoá những điều AI đã ghi nhớ về người dùng (giống mục Bộ nhớ của Agenty)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bộ nhớ")
        self.setMinimumSize(560, 460)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        head = QLabel("Những điều Agenty nhớ về bạn")
        head.setObjectName("DialogTitle")
        v.addWidget(head)
        hint = QLabel("Muốn thêm, chỉ cần nói trong đoạn chat, ví dụ “Hãy nhớ là mình thích câu trả lời ngắn gọn”.")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        v.addWidget(hint)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        holder = QWidget()
        self.rows = QVBoxLayout(holder)
        self.rows.setSpacing(6)
        scroll.setWidget(holder)
        v.addWidget(scroll, 1)
        btns = QHBoxLayout()
        clear = QPushButton("Xoá toàn bộ bộ nhớ")
        clear.setObjectName("Danger")
        clear.clicked.connect(self._clear)
        close = QPushButton("Xong")
        close.setObjectName("Primary")
        close.clicked.connect(self.accept)
        btns.addWidget(clear)
        btns.addStretch()
        btns.addWidget(close)
        v.addLayout(btns)
        self._fill()

    def _fill(self):
        while self.rows.count():
            w = self.rows.takeAt(0).widget()
            if w:
                w.deleteLater()
        items = memory.load()
        if not items:
            empty = QLabel("Chưa ghi nhớ điều gì.")
            empty.setObjectName("Muted")
            self.rows.addWidget(empty)
        for it in items:
            row = QFrame()
            row.setObjectName("FileCard")
            h = QHBoxLayout(row)
            h.setContentsMargins(12, 8, 6, 8)
            lb = QLabel(it["text"])
            lb.setWordWrap(True)
            h.addWidget(lb, 1)
            date = QLabel(it.get("created", ""))
            date.setObjectName("Muted")
            h.addWidget(date)
            rm = icon_button("trash", "Xoá điều này", 16, 30)
            rm.clicked.connect(lambda _=False, key=it["id"]: (memory.forget(key), self._fill()))
            h.addWidget(rm)
            self.rows.addWidget(row)
        self.rows.addStretch()

    def _clear(self):
        box = QMessageBox(QMessageBox.Icon.Warning, "Xoá bộ nhớ?", "Xoá tất cả những điều đã ghi nhớ về bạn?", parent=self)
        yes = box.addButton("Xoá hết", QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(box.addButton("Huỷ", QMessageBox.ButtonRole.RejectRole))
        box.exec()
        if box.clickedButton() is yes:
            memory.clear()
            self._fill()


# ---------- Hộp Cài đặt ----------

class SettingsDialog(QDialog):
    """Cài đặt giao diện và trò chuyện. Địa chỉ/khoá API được ẩn hoàn toàn (đã nhúng sẵn)."""

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cài đặt")
        self.setMinimumWidth(600)
        self.cfg = dict(cfg)
        self.delete_requested = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 18)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)
        v = QVBoxLayout(inner)
        v.setContentsMargins(28, 24, 28, 8)
        v.setSpacing(10)
        if self.screen():  # vừa màn hình nhỏ; phần thừa thì cuộn
            self.resize(640, min(860, int(self.screen().availableGeometry().height() * 0.88)))
        head = QLabel("Cài đặt")
        head.setObjectName("DialogTitle")
        v.addWidget(head)

        v.addWidget(self._group("Giao diện"))
        self.theme = self._segmented(v, "Chủ đề", [("dark", "Tối"), ("light", "Sáng")], cfg.get("theme", "dark"))
        self.font = self._segmented(v, "Cỡ chữ", [("small", "Nhỏ"), ("medium", "Vừa"), ("large", "Lớn")],
                                    cfg.get("font_size", "medium"))
        self.width_ = self._segmented(v, "Khung trò chuyện", [("normal", "Vừa"), ("wide", "Rộng")],
                                      cfg.get("chat_width", "normal"))

        self.api_fields = not C.api_embedded()
        if self.api_fields:
            v.addWidget(self._group("Kết nối API (OpenAI-compatible)"))
            self.base = QLineEdit(cfg.get("base_url", ""))
            self.base.setPlaceholderText("https://api.openai.com/v1")
            self.key = QLineEdit(cfg.get("api_key", ""))
            self.key.setEchoMode(QLineEdit.EchoMode.Password)
            self.key.setPlaceholderText("Dán khoá API của bạn")
            show = QCheckBox("Hiện")
            show.toggled.connect(lambda on: self.key.setEchoMode(QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
            self.voice = QLineEdit(cfg.get("voice_model", "gemini-3.8-flash-high"))
            for label, widget, extra in (("Địa chỉ API", self.base, None), ("Khoá API", self.key, show),
                                         ("Model nghe giọng nói", self.voice, None)):
                row = QHBoxLayout()
                lb = QLabel(label)
                lb.setMinimumWidth(150)
                row.addWidget(lb)
                row.addWidget(widget, 1)
                if extra:
                    row.addWidget(extra)
                v.addLayout(row)
            hint = QLabel("Khoá chỉ lưu trên máy này (thư mục dữ liệu cạnh file chạy). Model nghe giọng nói cần nhận được "
                          "âm thanh (input_audio).")
            hint.setObjectName("Muted")
            hint.setWordWrap(True)
            v.addWidget(hint)

        v.addWidget(self._group("Trò chuyện"))
        self.enter = QCheckBox("Nhấn Enter để gửi (Shift+Enter xuống dòng). Tắt thì dùng Ctrl+Enter để gửi.")
        self.enter.setChecked(cfg.get("enter_sends", True))
        v.addWidget(self.enter)
        img_row = QHBoxLayout()
        img_row.addWidget(QLabel("Model tạo ảnh"))
        self.image = QComboBox()
        self.image.setEditable(True)  # nhà cung cấp khác có thể dùng tên model ảnh khác
        self.image.addItems(IMAGE_MODELS)
        self.image.setCurrentText(cfg.get("default_image_model", IMAGE_MODELS[0]))
        img_row.addWidget(self.image, 1)
        v.addLayout(img_row)

        v.addWidget(self._group("Cá nhân hoá"))
        self.mem = QCheckBox("Bộ nhớ — cho phép ghi nhớ thông tin về bạn qua các đoạn chat")
        self.mem.setChecked(cfg.get("memory_enabled", True))
        self.hist = QCheckBox("Tham chiếu lịch sử trò chuyện — cho phép xem lại các đoạn chat cũ khi cần")
        self.hist.setChecked(cfg.get("history_enabled", True))
        v.addWidget(self.mem)
        v.addWidget(self.hist)
        mem_btn = QPushButton(f"Quản lý bộ nhớ ({len(memory.load())})")
        mem_btn.clicked.connect(lambda: (MemoryDialog(self).exec(), mem_btn.setText(f"Quản lý bộ nhớ ({len(memory.load())})")))
        v.addWidget(mem_btn, 0, Qt.AlignmentFlag.AlignLeft)

        v.addWidget(self._group("Skills"))
        self.skill_label = QLabel()
        self.skill_label.setObjectName("Muted")
        self.skill_label.setWordWrap(True)
        self._refresh_skills()
        v.addWidget(self.skill_label)
        sk_row = QHBoxLayout()
        imp = QPushButton("Nhập skill từ thư mục…")
        imp.clicked.connect(self._import_skill)
        opn = QPushButton("Mở thư mục skill")
        opn.clicked.connect(lambda: open_file(str(skills.USER_SKILLS), self))
        sk_row.addWidget(imp)
        sk_row.addWidget(opn)
        sk_row.addStretch()
        v.addLayout(sk_row)

        v.addWidget(self._group("Dữ liệu"))
        data_row = QHBoxLayout()
        folder = QPushButton("Mở thư mục file đã tạo")
        folder.setIcon(icons.icon("folder", INK, 16))
        folder.clicked.connect(lambda: open_file(str(C.OUTPUT_DIR), self))
        test = QPushButton("Kiểm tra kết nối")
        test.clicked.connect(self.test_connection)
        data_row.addWidget(folder)
        data_row.addWidget(test)
        data_row.addStretch()
        v.addLayout(data_row)
        self.test_result = QLabel("")
        self.test_result.setWordWrap(True)
        v.addWidget(self.test_result)
        delete = QPushButton("Xoá ứng dụng và toàn bộ dữ liệu")
        delete.setObjectName("Danger")
        delete.setIcon(icons.icon("trash", DANGER, 16))
        delete.clicked.connect(self._ask_delete)
        v.addWidget(delete, 0, Qt.AlignmentFlag.AlignLeft)

        v.addStretch()
        btns = QHBoxLayout()
        btns.setContentsMargins(28, 0, 28, 0)
        btns.addStretch()
        cancel = QPushButton("Huỷ")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Lưu")
        save.setObjectName("Primary")
        save.setDefault(True)
        save.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(save)
        outer.addLayout(btns)

    def _group(self, text):
        lb = QLabel(text)
        lb.setObjectName("GroupTitle")
        return lb

    def _segmented(self, parent_layout, label, options, current):
        row = QHBoxLayout()
        lb = QLabel(label)
        lb.setMinimumWidth(150)
        row.addWidget(lb)
        group = QButtonGroup(self)
        for key, text in options:
            b = QPushButton(text)
            b.setObjectName("Seg")
            b.setCheckable(True)
            b.setChecked(key == current)
            b.setProperty("key", key)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            group.addButton(b)
            row.addWidget(b)
        row.addStretch()
        parent_layout.addLayout(row)
        return group

    def values(self):
        pick = lambda g: g.checkedButton().property("key")
        return {**self.cfg, "theme": pick(self.theme), "font_size": pick(self.font), "chat_width": pick(self.width_),
                "enter_sends": self.enter.isChecked(), "default_image_model": self.image.currentText(),
                "memory_enabled": self.mem.isChecked(), "history_enabled": self.hist.isChecked(),
                **({"base_url": self.base.text().strip(), "api_key": self.key.text().strip(),
                    "voice_model": self.voice.text().strip() or "gemini-3.8-flash-high"} if self.api_fields else {})}

    def _refresh_skills(self):
        names = [s["name"] for s in skills.list_skills()]
        self.skill_label.setText("Đang có: " + (", ".join(names) or "chưa có skill nào") +
                                 ". AI tự nạp skill phù hợp, ví dụ slide-design mỗi khi làm bài thuyết trình.")

    def _import_skill(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục skill (có file SKILL.md)")
        if not folder:
            return
        try:
            name = skills.import_skill(folder)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Không nhập được skill", str(e))
            return
        self._refresh_skills()
        QMessageBox.information(self, "Đã nhập skill", f"Đã thêm skill “{name}”.")

    def test_connection(self):
        self.test_result.setStyleSheet(f"color: {MUTED};")
        self.test_result.setText("Đang kiểm tra kết nối…")
        cfg = self.values()  # thử bằng địa chỉ / khoá đang gõ, chưa cần bấm Lưu
        run_bg(lambda: list_models(cfg), on_done=self._show_test_result)

    def _show_test_result(self, models, err):
        if err is None:
            self.test_result.setStyleSheet(f"color: {OK}; font-weight: 600;")
            self.test_result.setText(f"Kết nối tốt — máy chủ có {len(models)} model.")
        else:
            self.test_result.setStyleSheet(f"color: {DANGER}; font-weight: 600;")
            self.test_result.setText(friendly_error(err).split("\n")[0])

    def _ask_delete(self):
        self.delete_requested = True
        self.reject()


# ---------- Cửa sổ chính ----------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Agenty")
        self.resize(1320, 860)
        self.setMinimumSize(900, 600)
        self.setAcceptDrops(True)
        icon_file = find_asset("icon.ico") or find_asset("logo.png")
        if icon_file:
            self.setWindowIcon(QIcon(str(icon_file)))
        self.cfg = C.load_config()
        if self.cfg.get("default_chat_model") not in {m for m, _, _ in MODELS}:
            self.cfg["default_chat_model"] = C.DEFAULTS["default_chat_model"]
        self.conv = None
        self.attachments: list[str] = []
        self.worker = None
        self.cur = None
        self.cur_disp = None
        self.show_archived = False
        self._tts = None
        self._speaking = None
        self._index_path = C.APP_DIR / "history_index.json"
        self._index_dirty = False
        self._meta_cache = self._load_index()
        self._list_limit = self.LIST_LIMIT
        self._recorder = None
        self._stt = None

        self._build_actions()
        root = QWidget()
        root.setObjectName("Root")
        rv = QVBoxLayout(root)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        self.titlebar = TitleBar(self)
        rv.addWidget(self.titlebar)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_rail())
        self.sidebar = self._build_sidebar()
        body.addWidget(self.sidebar)
        body.addWidget(self._build_main(), 1)
        rv.addLayout(body, 1)
        self.setCentralWidget(root)
        self._frameless()

        self.update_pill()
        self.refresh_chat_list()
        self.show_empty_state()
        QTimer.singleShot(1500, self._ensure_shortcuts)
        self.server_models: list[str] = []
        if not self.cfg.get("api_key"):
            QTimer.singleShot(500, lambda: self.open_settings(first_run=True))
        else:
            self._load_server_models()

    # --- khung cửa sổ tự vẽ (giữ kéo / snap / đổi kích thước gốc của Windows) ---
    def _ensure_shortcuts(self):
        """Lần mở đầu (hoặc khi .exe đổi chỗ): lối tắt Desktop + Start Menu để tìm được bằng Windows Search."""
        with contextlib.suppress(Exception):
            if shortcuts.ensure(self.cfg):
                C.save_config(self.cfg)

    def _frameless(self):
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        if sys.platform != "win32":
            return
        with contextlib.suppress(Exception):
            hwnd = int(self.winId())
            u32, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
            # Thêm lại viền co giãn + nút hệ thống để Windows lo snap, kéo đổi cỡ, hiệu ứng thu nhỏ/phóng to
            style = u32.GetWindowLongW(hwnd, -16) | 0x00040000 | 0x00C00000 | 0x00010000 | 0x00020000
            u32.SetWindowLongW(hwnd, -16, style)

            class MARGINS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_int), ("r", ctypes.c_int), ("t", ctypes.c_int), ("b", ctypes.c_int)]
            dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(MARGINS(1, 1, 1, 1)))  # bóng đổ quanh cửa sổ
            for attr, val in ((20, 1 if self.cfg.get("theme", "dark") == "dark" else 0), (33, 2)):  # tối + bo góc Win11
                v = ctypes.c_int(val)
                dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), 4)
            u32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)  # SWP_FRAMECHANGED | NOMOVE | NOSIZE | NOZORDER

    def nativeEvent(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0083 and msg.wParam:  # WM_NCCALCSIZE: bỏ viền gốc, cả cửa sổ là vùng vẽ
                return True, 0
            if msg.message == 0x0084:  # WM_NCHITTEST
                pos = self.mapFromGlobal(QCursor.pos())
                x, y, w, h, b = pos.x(), pos.y(), self.width(), self.height(), 6
                if not self.isMaximized():
                    left, right, top, bottom = x < b, x >= w - b, y < b, y >= h - b
                    corner = {(1, 0, 1, 0): 13, (0, 1, 1, 0): 14, (1, 0, 0, 1): 16, (0, 1, 0, 1): 17}
                    code = corner.get((left, right, top, bottom)) or \
                        (10 if left else 11 if right else 12 if top else 15 if bottom else 0)
                    if code:
                        return True, code
                if y < TitleBar.HEIGHT and self.titlebar.is_drag_area(self.titlebar.mapFrom(self, pos)):
                    return True, 2  # HTCAPTION: kéo, snap, nhấp đúp phóng to
        return super().nativeEvent(event_type, message)

    def changeEvent(self, e):
        if e.type() == e.Type.WindowStateChange:
            self.titlebar.set_maximized(self.isMaximized())
            # Khi phóng to, Windows đẩy cửa sổ tràn ra ngoài màn hình đúng bằng độ dày viền: chừa lại phần đó
            m = 0
            if self.isMaximized() and self.screen():
                m = max(0, self.screen().availableGeometry().x() - self.geometry().x(), 7)
            self.centralWidget().setContentsMargins(m, m, m, m)
        super().changeEvent(e)

    def toggle_maximize(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    # --- menu & phím tắt ---
    def _build_actions(self):
        def act(text, cb, shortcut=None):
            a = QAction(text, self)
            if shortcut:
                a.setShortcut(shortcut)
            a.triggered.connect(cb)
            self.addAction(a)  # phím tắt hoạt động cả khi menu đang đóng
            return a

        def menu(*items):
            m = QMenu(self)
            for it in items:
                m.addSeparator() if it is None else m.addAction(it)
            return m

        def edit(method):
            w = QApplication.focusWidget()
            if w and hasattr(w, method):
                getattr(w, method)()

        cur = lambda fn: (lambda: self.conv and fn(self.conv["id"]))
        self.title_menus = [
            ("Tệp", menu(act("Trò chuyện mới", self.new_chat, "Ctrl+Shift+O"),
                         act("Đính kèm file / ảnh…", self.pick_files, "Ctrl+U"),
                         act("Chia sẻ / xuất đoạn chat…", lambda: self.conv and self.share_chat(self.conv["id"]), "Ctrl+Shift+E"),
                         act("Nói để nhập", lambda: self.toggle_mic(), "Ctrl+M"), None,
                         act("Mở thư mục file đã tạo", lambda: open_file(str(C.OUTPUT_DIR), self)),
                         act("Cài đặt…", self.open_settings, "Ctrl+,"), None,
                         act("Thoát", self.close, "Ctrl+Q"))),
            ("Chỉnh sửa", menu(act("Hoàn tác", lambda: edit("undo")), act("Làm lại", lambda: edit("redo")), None,
                               act("Cắt", lambda: edit("cut")), act("Sao chép", lambda: edit("copy")),
                               act("Dán", lambda: edit("paste")), act("Chọn tất cả", lambda: edit("selectAll")), None,
                               act("Đặt lại tên đoạn chat", cur(self.rename_chat), "Ctrl+Alt+R"),
                               act("Ghim / bỏ ghim", cur(self.toggle_pin), "Ctrl+Alt+P"),
                               act("Lưu trữ / bỏ lưu trữ", cur(self.toggle_archive), "Ctrl+Shift+A"),
                               act("Xoá đoạn chat", cur(self.delete_chat), "Ctrl+Shift+Delete"))),
            ("Xem", menu(act("Ẩn / hiện thanh bên", self.toggle_sidebar, "Ctrl+Shift+S"),
                         act("Tìm đoạn chat", self.focus_search, "Ctrl+K"),
                         act("Đoạn chat đã lưu trữ", self.toggle_archived_view), None,
                         act("Phóng to / thu về", self.toggle_maximize, "F11"))),
            ("Trợ giúp", menu(act("Phím tắt", self.show_shortcuts, "Ctrl+/"),
                              act("Giới thiệu", lambda: QMessageBox.about(
                                  self, "Giới thiệu", "Agenty — client riêng chạy bằng API OpenAI-compatible.")))),
        ]

    def show_shortcuts(self):
        QMessageBox.information(self, "Phím tắt", "\n".join([
            "Ctrl+Shift+O   Trò chuyện mới", "Ctrl+K   Tìm đoạn chat", "Ctrl+Shift+S   Ẩn / hiện thanh bên",
            "Ctrl+U   Đính kèm file", "Ctrl+Alt+R   Đặt lại tên", "Ctrl+Alt+P   Ghim", "Ctrl+Shift+A   Lưu trữ",
            "Ctrl+,   Cài đặt", "Enter   Gửi  ·  Shift+Enter   Xuống dòng"]))

    # --- dựng giao diện ---
    def _build_rail(self):
        rail = QFrame()
        rail.setObjectName("Rail")
        rail.setFixedWidth(56)
        v = QVBoxLayout(rail)
        v.setContentsMargins(8, 6, 8, 12)
        v.setSpacing(6)
        home = QToolButton()
        home.setObjectName("RailBtn")
        home.setFixedSize(40, 40)
        logo = logo_pixmap(22)
        home.setIcon(QIcon(logo) if logo else icons.icon("home", INK, 20))
        home.setIconSize(QSize(22, 22))
        home.setToolTip("Trò chuyện mới")
        home.setCursor(Qt.CursorShape.PointingHandCursor)
        home.clicked.connect(self.new_chat)
        v.addWidget(home)
        for name, tip, cb in (("search", "Tìm đoạn chat (Ctrl+K)", self.focus_search),
                              ("folder", "Thư viện file đã tạo", lambda: open_file(str(C.OUTPUT_DIR), self)),
                              ("archive", "Đoạn chat đã lưu trữ", self.toggle_archived_view)):
            b = icon_button(name, tip, 19, 40, MUTED, "RailBtn")
            b.clicked.connect(cb)
            v.addWidget(b)
        v.addStretch()
        s = icon_button("settings", "Cài đặt (Ctrl+,)", 19, 40, MUTED, "RailBtn")
        s.clicked.connect(self.open_settings)
        v.addWidget(s)
        return rail

    def _build_sidebar(self):
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(272)
        v = QVBoxLayout(side)
        v.setContentsMargins(10, 12, 8, 10)
        v.setSpacing(2)

        head = QHBoxLayout()
        head.setContentsMargins(8, 0, 0, 0)
        brand = QLabel("Agenty")
        brand.setObjectName("Brand")
        head.addWidget(brand)
        head.addStretch()
        search_btn = icon_button("search", "Tìm đoạn chat (Ctrl+K)")
        search_btn.clicked.connect(self.focus_search)
        head.addWidget(search_btn)
        v.addLayout(head)
        v.addSpacing(8)

        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("Tìm đoạn chat")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh_chat_list)
        self.search.hide()
        v.addWidget(self.search)

        new = QPushButton("  Trò chuyện mới")
        new.setObjectName("Ghost")
        new.setIcon(icons.icon("new-chat", INK, 17))
        new.setToolTip("Trò chuyện mới (Ctrl+Shift+O)")
        new.setCursor(Qt.CursorShape.PointingHandCursor)
        new.clicked.connect(self.new_chat)
        v.addWidget(new)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        self.list_lay = QVBoxLayout(holder)
        self.list_lay.setContentsMargins(0, 2, 4, 6)
        self.list_lay.setSpacing(1)
        self.list_lay.addStretch()
        scroll.setWidget(holder)
        v.addWidget(scroll, 1)

        self.archive_btn = QPushButton("  Đã lưu trữ")
        self.archive_btn.setObjectName("Ghost")
        self.archive_btn.setIcon(icons.icon("archive", MUTED, 17))
        self.archive_btn.clicked.connect(self.toggle_archived_view)
        v.addWidget(self.archive_btn)
        return side

    def _build_main(self):
        main = QFrame()
        main.setObjectName("Main")
        v = QVBoxLayout(main)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        top = QHBoxLayout()
        top.setContentsMargins(12, 8, 12, 4)
        top.addStretch()
        top_new = icon_button("new-chat", "Trò chuyện mới (Ctrl+Shift+O)", 19, 34)
        top_new.clicked.connect(self.new_chat)
        top.addWidget(top_new)
        topw = QWidget()
        topw.setFixedHeight(48)
        topw.setLayout(top)
        v.addWidget(topw)

        width = CHAT_WIDTHS.get(self.cfg.get("chat_width"), 780)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("ChatArea")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        holder = QWidget()
        holder.setObjectName("ChatArea")
        hh = QHBoxLayout(holder)
        hh.setContentsMargins(24, 8, 24, 8)
        self.column = QWidget()
        self.column.setObjectName("ChatColumn")
        self.column.setMaximumWidth(width)
        self.msgs = QVBoxLayout(self.column)
        self.msgs.setContentsMargins(0, 0, 0, 0)
        self.msgs.setSpacing(8)
        self.msgs.addStretch()
        hh.addStretch()
        hh.addWidget(self.column, 100)
        hh.addStretch()
        self.scroll.setWidget(holder)
        v.addWidget(self.scroll, 1)

        # màn hình trống: lời chào + ô nhập ở giữa + lối tắt
        self.home = QWidget()
        self.home.setObjectName("Home")
        hv = QVBoxLayout(self.home)
        hv.addStretch(3)
        hello = QLabel("Sẵn sàng khi bạn sẵn sàng.")
        hello.setObjectName("Hello")
        hello.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hv.addWidget(hello)
        hv.addSpacing(26)
        self.home_slot = QVBoxLayout()
        hv.addLayout(self.home_slot)
        hv.addSpacing(16)
        quick_row = QHBoxLayout()
        quick = QWidget()
        quick.setMaximumWidth(width)
        ql = QVBoxLayout(quick)
        ql.setContentsMargins(8, 0, 8, 0)
        ql.setSpacing(2)
        for icon_name, label, prefix in QUICK_ACTIONS:
            b = QPushButton("  " + label)
            b.setObjectName("Quick")
            b.setIcon(icons.icon(icon_name, MUTED, 17))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, p=prefix: self.prefill(p))
            ql.addWidget(b, 0, Qt.AlignmentFlag.AlignLeft)
        quick_row.addStretch()
        quick_row.addWidget(quick, 100)
        quick_row.addStretch()
        hv.addLayout(quick_row)
        hv.addStretch(4)
        v.addWidget(self.home, 1)

        self.bottom_slot = QVBoxLayout()
        self.bottom_slot.setContentsMargins(0, 4, 0, 8)
        v.addLayout(self.bottom_slot)
        self._build_composer(width)
        return main

    def _build_composer(self, width):
        self.composer_wrap = QWidget()
        wl = QHBoxLayout(self.composer_wrap)
        wl.setContentsMargins(24, 0, 24, 0)
        inner = QWidget()
        inner.setMaximumWidth(width)
        il = QVBoxLayout(inner)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(6)
        comp = QFrame()
        comp.setObjectName("Composer")
        cv = QVBoxLayout(comp)
        cv.setContentsMargins(10, 9, 10, 9)
        cv.setSpacing(6)
        self.chips = QHBoxLayout()
        self.chips.setSpacing(8)
        self.chips.addStretch()
        cv.addLayout(self.chips)
        row = QHBoxLayout()
        row.setSpacing(6)
        plus = icon_button("plus", "Đính kèm file / ảnh (Ctrl+U) — hoặc kéo thả vào cửa sổ", 20, 36, INK, "RoundGhost")
        plus.clicked.connect(self.pick_files)
        row.addWidget(plus, 0, Qt.AlignmentFlag.AlignBottom)
        self.input = InputBox(self.cfg.get("enter_sends", True))
        self.input.send.connect(self.send)
        self.input.files_dropped.connect(self.add_attachments)
        self.input.textChanged.connect(self.update_send_state)
        row.addWidget(self.input, 1)
        self.mic_btn = icon_button("mic", "Nói để nhập (Ctrl+M)", 19, 36, MUTED, "RoundGhost")
        self.mic_btn.clicked.connect(self.toggle_mic)
        row.addWidget(self.mic_btn, 0, Qt.AlignmentFlag.AlignBottom)
        self.pill = QPushButton()
        self.pill.setObjectName("Pill")
        self.pill.setIcon(icons.icon("chevron-down", MUTED, 14))
        self.pill.setLayoutDirection(Qt.LayoutDirection.RightToLeft)  # đặt mũi tên bên phải chữ
        self.pill.setToolTip("Chọn model và mức suy nghĩ")
        self.pill.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pill.clicked.connect(self.show_model_menu)
        row.addWidget(self.pill, 0, Qt.AlignmentFlag.AlignBottom)
        self.send_btn = icon_button("arrow-up", "Gửi", 19, 36, "#FFFFFF", "Send")
        self.send_btn.clicked.connect(lambda: self.stop() if self.worker else self.send())
        row.addWidget(self.send_btn, 0, Qt.AlignmentFlag.AlignBottom)
        cv.addLayout(row)
        il.addWidget(comp)
        self.note = QLabel("Agenty có thể mắc lỗi. Hãy kiểm tra các thông tin quan trọng.")
        self.note.setObjectName("Muted")
        self.note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.note.setStyleSheet(f"font-size: {FS - 3}px;")
        il.addWidget(self.note)
        wl.addStretch()
        wl.addWidget(inner, 100)
        wl.addStretch()
        self.update_send_state()

    def _set_home(self, on: bool):
        self.home.setVisible(on)
        self.scroll.setVisible(not on)
        self.note.setVisible(not on)
        (self.home_slot if on else self.bottom_slot).addWidget(self.composer_wrap)

    def prefill(self, text):
        self.input.setPlainText(text)
        cur = self.input.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        self.input.setTextCursor(cur)
        self.input.setFocus()

    def toggle_sidebar(self):
        self.sidebar.setVisible(not self.sidebar.isVisible())

    def focus_search(self):
        if not self.sidebar.isVisible():
            self.toggle_sidebar()
        self.search.setVisible(True)
        self.search.setFocus()
        self.search.selectAll()

    # --- model & effort ---
    def model_name(self, mid):
        return next((name for m, name, _ in MODELS if m == mid), mid)

    def update_pill(self):
        eff = dict(EFFORTS).get(self.cfg.get("effort"), "Vừa")
        self.pill.setText(f"{self.model_name(self.cfg['default_chat_model'])}  {eff}")

    def _load_server_models(self):
        run_bg(lambda cfg=dict(self.cfg): list_models(cfg),
               on_done=lambda models, err: setattr(self, "server_models", models or []))

    def show_model_menu(self):
        m = PopMenu(self)
        cur = self.cfg["default_chat_model"]
        known = {mid for mid, _, _ in MODELS}
        rows = MODELS + [(x, x, "Tự chọn") for x in self.cfg.get("custom_models", []) if x not in known]
        for i, (mid, name, desc) in enumerate(rows, 1):
            cb = lambda mid=mid: self.set_cfg(default_chat_model=mid)
            m.row(name, cb, sub=desc, right_icon="check" if mid == cur else None,
                  right="" if mid == cur else (str(i) if i < 10 else ""))
            if i < 10:
                m.hotkeys[getattr(Qt.Key, f"Key_{i}")] = cb
        m.row("Model khác…", self.choose_custom_model, "plus")
        m.addSeparator()
        m.row("Mức suy nghĩ", self.show_effort_menu, right=f"{dict(EFFORTS).get(self.cfg.get('effort'), 'Vừa')}  ›")
        m.popup_above(self.pill)

    def choose_custom_model(self):
        """Gõ hoặc chọn tên model từ danh sách /models của máy chủ."""
        dlg = QInputDialog(self)
        dlg.setWindowTitle("Model khác")
        dlg.setLabelText("Tên model (chọn từ máy chủ hoặc tự gõ):")
        dlg.setComboBoxEditable(True)
        dlg.setComboBoxItems([x for x in self.server_models if "image" not in x] or [self.cfg["default_chat_model"]])
        dlg.setTextValue(self.cfg["default_chat_model"])
        dlg.setOkButtonText("Dùng model này")
        dlg.setCancelButtonText("Huỷ")
        if dlg.exec() and dlg.textValue().strip():
            mid = dlg.textValue().strip()
            custom = [x for x in self.cfg.get("custom_models", []) if x != mid][-7:] + [mid]
            self.set_cfg(default_chat_model=mid, custom_models=custom)

    def show_effort_menu(self):
        m = PopMenu(self)
        for i, (key, label) in enumerate(EFFORTS, 1):
            cb = lambda key=key: self.set_cfg(effort=key)
            m.row(label, cb, right_icon="check" if key == self.cfg.get("effort") else None,
                  right="" if key == self.cfg.get("effort") else str(i))
            m.hotkeys[getattr(Qt.Key, f"Key_{i}")] = cb
        m.popup_above(self.pill)

    def set_cfg(self, **kv):
        self.cfg.update(kv)
        C.save_config(self.cfg)  # lần mở sau dùng lại model / mức suy nghĩ đã chọn
        self.update_pill()

    # --- khung chat ---
    def clear_messages(self):
        while self.msgs.count() > 1:
            w = self.msgs.takeAt(0).widget()
            if w:
                w.deleteLater()

    def add_widget(self, w):
        self.msgs.insertWidget(self.msgs.count() - 1, w)
        self.scroll_to_bottom()

    def scroll_to_bottom(self):
        QTimer.singleShot(30, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))

    def show_empty_state(self):
        self.clear_messages()
        self._set_home(True)
        self.input.setFocus()

    def render_display(self, item, idx=None):
        if item["role"] == "user":
            on_edit = (lambda t, i=idx: self.edit_message(i, t)) if idx is not None else None
            self.add_widget(UserMessage(item.get("text", ""), item.get("attachments", []), on_edit))
        else:
            m = AssistantMessage(item.get("text", ""), on_speak=self.toggle_speak)
            if item.get("images"):
                m.add_images(item["images"])
            m.add_files(item.get("files", []))
            if item.get("error"):
                m.show_error(item["error"])
            m.finish()
            self.add_widget(m)

    def rerender_chat(self):
        self.stop_speaking()
        self.clear_messages()
        for i, item in enumerate(self.conv.get("display", [])):
            self.render_display(item, i)
        self._refresh_regen()
        self.scroll_to_bottom()

    def _refresh_regen(self):
        """Chỉ câu trả lời mới nhất có nút Tạo lại (và chỉ khi không đang trả lời)."""
        widgets = [self.msgs.itemAt(i).widget() for i in range(self.msgs.count() - 1)]
        answers = [w for w in widgets if isinstance(w, AssistantMessage)]
        for w in answers:
            w.set_regenerate(None)
        if answers and widgets and widgets[-1] is answers[-1] and not self.worker:
            answers[-1].set_regenerate(self.regenerate)

    def _real_user_indices(self) -> list[int]:
        """Vị trí các tin nhắn người dùng thật trong messages (bỏ tin ảnh xem trước tự động)."""
        out = []
        for i, m in enumerate(self.conv["messages"]):
            if m["role"] != "user":
                continue
            c = m["content"]
            t = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c if x.get("type") == "text")
            if not t.startswith(("[Ảnh xem trước tự động", "[Ảnh các trang của PDF scan")):
                out.append(i)
        return out

    def edit_message(self, disp_idx, new_text):
        """Sửa tin nhắn đã gửi: bỏ mọi thứ từ tin đó trở đi rồi gửi lại (giữ file đính kèm cũ)."""
        if self.worker or not new_text or not self.conv:
            return
        display = self.conv["display"]
        users = [i for i, x in enumerate(display) if x["role"] == "user"]
        real = self._real_user_indices()
        k = users.index(disp_idx) if disp_idx in users else -1
        if k < 0 or k >= len(real):
            return
        item = display[disp_idx]
        self.conv["messages"] = self.conv["messages"][:real[k]]
        self.conv["display"] = display[:disp_idx]
        self.attachments = [p for p in item.get("uploads", []) if Path(p).exists()]
        self.rerender_chat()
        self.send(new_text)

    def regenerate(self):
        """Tạo lại câu trả lời cuối cùng với cùng câu hỏi (dùng model / mức suy nghĩ đang chọn)."""
        if self.worker or not self.conv or not self.conv["display"] or self.conv["display"][-1]["role"] != "assistant":
            return
        real = self._real_user_indices()
        if not real:
            return
        self.conv["messages"] = self.conv["messages"][:real[-1] + 1]
        self.conv["display"] = self.conv["display"][:-1]
        self.rerender_chat()
        self._start_agent()

    # --- đính kèm ---
    def pick_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Chọn file hoặc ảnh", QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation),
            "Tất cả file hỗ trợ (*.png *.jpg *.jpeg *.webp *.gif *.bmp *.pdf *.docx *.xlsx *.pptx *.txt *.csv *.md);;Tất cả (*.*)")
        self.add_attachments(files)

    def add_attachments(self, files):
        for f in files:
            src = Path(f)
            if not src.is_file():
                continue
            dest = C.UPLOADS_DIR / f"{uuid.uuid4().hex[:6]}_{src.name}"
            try:
                shutil.copy2(src, dest)
            except OSError as e:
                QMessageBox.warning(self, "Không đính kèm được", str(e))
                continue
            self.attachments.append(str(dest))
        self.refresh_chips()

    def refresh_chips(self):
        while self.chips.count() > 1:
            w = self.chips.takeAt(0).widget()
            if w:
                w.deleteLater()
        for i, p in enumerate(self.attachments):
            b = QPushButton(Path(p).name.split("_", 1)[-1])
            b.setObjectName("Chip")
            b.setIcon(icons.icon("x", MUTED, 12))
            b.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            b.setToolTip("Bỏ file này")
            b.clicked.connect(lambda _=False, idx=i: self._remove_attachment(idx))
            self.chips.insertWidget(self.chips.count() - 1, b)
        self.update_send_state()

    def _remove_attachment(self, idx):
        path = Path(self.attachments.pop(idx))
        if path.parent == C.UPLOADS_DIR:  # bản sao app tạo lúc đính kèm, chưa gửi nên không ai tham chiếu
            with contextlib.suppress(OSError):
                path.unlink()
        self.refresh_chips()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.add_attachments([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])

    # --- gửi / nhận ---
    def update_send_state(self):
        if self.worker:
            self.send_btn.setIcon(icons.icon("stop", "#FFFFFF", 15))
            self.send_btn.setToolTip("Dừng trả lời")
            self.send_btn.setEnabled(True)
        else:
            self.send_btn.setIcon(icons.icon("arrow-up", "#FFFFFF", 19))
            self.send_btn.setToolTip("Gửi")
            self.send_btn.setEnabled(bool(self.input.toPlainText().strip() or self.attachments))

    def send(self, text=None):
        if self.worker:
            return
        text = (text if isinstance(text, str) else self.input.toPlainText()).strip()
        if not text and not self.attachments:
            return
        if self.conv is None:
            self.clear_messages()
            first = text or Path(self.attachments[0]).name.split("_", 1)[-1]
            self.conv = {"id": uuid.uuid4().hex, "title": first[:60], "messages": [], "display": [],
                         "pinned": False, "archived": False}
        self._set_home(False)
        compact_history(self.conv["messages"])
        pending = (text, list(self.attachments))
        names = [Path(p).name.split("_", 1)[-1] for p in self.attachments]
        idx = len(self.conv["display"])
        self.conv["display"].append({"role": "user", "text": text, "attachments": names, "uploads": list(self.attachments)})
        self.add_widget(UserMessage(text, names, lambda t, i=idx: self.edit_message(i, t)))
        self.input.clear()
        self.attachments = []
        self.refresh_chips()
        self._start_agent(pending)

    def _start_agent(self, pending=None):
        self.stop_speaking()
        self.cur = AssistantMessage(on_speak=self.toggle_speak)
        self.cur.add_step("Đang suy nghĩ…")
        self.cur_disp = {"role": "assistant", "text": "", "files": [], "images": []}
        self.add_widget(self.cur)

        self.worker = AgentWorker(dict(self.cfg, _conv_id=self.conv["id"]), self.cfg["default_chat_model"],
                                  self.conv["messages"], pending)
        self.worker.sig_delta.connect(self._on_delta)
        self.worker.sig_status.connect(self._on_status)
        self.worker.sig_files.connect(self._on_files)
        self.worker.sig_images.connect(self._on_images)
        self.worker.sig_error.connect(self._on_error)
        self.worker.finished.connect(self._on_done)
        self.worker.start()
        self.update_send_state()
        self._refresh_regen()

    def _near_bottom(self):
        sb = self.scroll.verticalScrollBar()
        return sb.maximum() - sb.value() < 160

    def _on_delta(self, d):
        follow = self._near_bottom()
        self.cur.append(d)
        if follow:
            self.scroll_to_bottom()

    def _on_status(self, s):
        self.cur.add_step(s)
        self.scroll_to_bottom()

    def _on_files(self, paths):
        self.cur.add_files(paths)
        self.cur_disp["files"] += paths
        self.scroll_to_bottom()

    def _on_images(self, paths):
        self.cur.add_images(paths)
        self.cur_disp["images"] += paths

    def _on_error(self, msg):
        self.cur.show_error(msg)
        self.cur_disp["error"] = msg

    def _on_done(self):
        if self.worker.stopped():
            self.cur.append("\n\n_(Đã dừng.)_")
        self.cur.finish()
        self.cur_disp["text"] = self.cur.buf
        self.conv["display"].append(self.cur_disp)
        self.save_conv()
        self.worker.deleteLater()
        self.worker = None
        self.update_send_state()
        self._refresh_regen()
        self.input.setFocus()
        self.scroll_to_bottom()

    # --- đọc to (giọng Windows) ---
    def toggle_speak(self, msg):
        from PySide6.QtCore import QLocale
        from PySide6.QtTextToSpeech import QTextToSpeech
        if self._speaking is msg:
            self.stop_speaking()
            return
        self.stop_speaking()
        if self._tts is None:
            engines = QTextToSpeech.availableEngines()
            self._tts = QTextToSpeech("winrt" if "winrt" in engines else (engines[0] if engines else ""))
            self._tts.stateChanged.connect(self._tts_state)
        text = voice.plain_text(msg.buf)
        vi = [loc for loc in self._tts.availableLocales() if loc.language() == QLocale.Language.Vietnamese]
        if voice.looks_vietnamese(text) and not vi:
            box = QMessageBox(QMessageBox.Icon.Information, "Chưa có giọng đọc tiếng Việt",
                              "Windows trên máy này chưa cài giọng đọc tiếng Việt.\n\nVào Cài đặt Windows → Thời gian & ngôn ngữ"
                              " → Giọng nói → Quản lý giọng nói → Thêm giọng → chọn Tiếng Việt, rồi mở lại app.", parent=self)
            go = box.addButton("Mở cài đặt giọng nói", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Để sau", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is go:
                with contextlib.suppress(OSError):
                    os.startfile("ms-settings:speech")
            return
        if vi:
            self._tts.setLocale(vi[0])
        self._speaking = msg
        msg.set_speaking(True)
        self._tts.say(text)

    def _tts_state(self, state):
        from PySide6.QtTextToSpeech import QTextToSpeech
        if state in (QTextToSpeech.State.Ready, QTextToSpeech.State.Error) and self._speaking:
            with contextlib.suppress(RuntimeError):
                self._speaking.set_speaking(False)
            self._speaking = None

    def stop_speaking(self):
        if self._tts is not None and self._speaking is not None:
            self._tts.stop()
            with contextlib.suppress(RuntimeError):
                self._speaking.set_speaking(False)
        self._speaking = None

    # --- nói để nhập (ghi âm → AI chép thành chữ) ---
    def toggle_mic(self):
        if self._recorder and self._recorder.active:
            wav = self._recorder.stop()
            self._set_mic(False)
            if not wav:
                return
            self.input.setPlaceholderText("Đang chuyển giọng nói thành chữ…")
            self._stt = voice.TranscribeWorker(dict(self.cfg), wav)
            self._stt.done.connect(self._on_transcript)
            self._stt.start()
            return
        try:
            self._recorder = self._recorder or voice.Recorder(self)
            self._recorder.start()
        except RuntimeError as e:
            QMessageBox.warning(self, "Không dùng được micro", str(e))
            return
        self._set_mic(True)

    def _set_mic(self, on):
        self.mic_btn.setIcon(icons.icon("stop" if on else "mic", DANGER if on else MUTED, 14 if on else 19))
        self.mic_btn.setToolTip("Bấm để dừng và chuyển thành chữ" if on else "Nói để nhập (Ctrl+M)")
        self.input.setPlaceholderText("Đang nghe… bấm nút ■ để dừng" if on else "Hỏi Agenty")

    def _on_transcript(self, text, err):
        self.input.setPlaceholderText("Hỏi Agenty")
        if err:
            QMessageBox.warning(self, "Không nhận được giọng nói", err)
            return
        if not text.strip():
            self.input.setPlaceholderText("Không nghe thấy tiếng nói — bấm micro và nói gần hơn nhé")
            QTimer.singleShot(4000, lambda: self.input.setPlaceholderText("Hỏi Agenty"))
            return
        cur = self.input.toPlainText().strip()
        self.prefill((cur + " " if cur else "") + text)

    # --- chia sẻ / xuất đoạn chat ---
    def share_chat(self, cid, anchor=None):
        m = PopMenu(self)
        m.row("Xuất PDF", lambda: self.export_chat(cid, ".pdf"), "file")
        m.row("Xuất Word (.docx)", lambda: self.export_chat(cid, ".docx"), "file")
        m.row("Xuất trang web (.html)", lambda: self.export_chat(cid, ".html"), "globe")
        m.row("Xuất Markdown (.md)", lambda: self.export_chat(cid, ".md"), "file")
        m.addSeparator()
        m.row("Sao chép toàn bộ đoạn chat", lambda: self.export_chat(cid, "copy"), "copy")
        m.exec(anchor.mapToGlobal(QPoint(0, anchor.height() + 4)) if anchor else QCursor.pos())

    def export_chat(self, cid, kind):
        d = self._read(cid)
        if d is None:
            return
        md = voice.transcript_markdown(d)
        if kind == "copy":
            QGuiApplication.clipboard().setText(md)
            return
        safe = "".join(ch for ch in (d.get("title") or "doan_chat") if ch not in '\\/:*?"<>|').strip()[:60] or "doan_chat"
        dest, _ = QFileDialog.getSaveFileName(self, "Chia sẻ đoạn chat", str(Path(downloads_dir()) / f"{safe}{kind}"),
                                              f"{kind[1:].upper()} (*{kind})")
        if not dest:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            voice.export(d.get("title") or "Đoạn chat", md, dest)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Không xuất được", str(e))
            return
        QApplication.restoreOverrideCursor()
        box = QMessageBox(QMessageBox.Icon.Information, "Đã xuất đoạn chat", f"Đã lưu:\n{dest}", parent=self)
        open_btn = box.addButton("Mở file", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Xong", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            open_file(dest, self)

    def stop(self):
        if self.worker:
            self.worker.stop()

    # --- lịch sử & quản lý đoạn chat ---
    def _path(self, cid):
        return C.HISTORY_DIR / f"{cid}.json"

    def _read(self, cid):
        try:
            d = json.loads(self._path(cid).read_text("utf-8"))
        except (OSError, ValueError):
            return None
        return d if isinstance(d, dict) and isinstance(d.get("display", []), list) else None

    def _write(self, cid, data) -> bool:
        try:
            C.write_json(self._path(cid), data)
            return True
        except OSError as e:
            if not getattr(self, "_warned_disk", False):
                self._warned_disk = True
                QTimer.singleShot(0, lambda: QMessageBox.warning(
                    self, "Không lưu được đoạn chat",
                    f"Không ghi được lịch sử vào ổ đĩa ({e}).\nĐoạn chat vẫn còn trong cửa sổ này; "
                    "hãy kiểm tra dung lượng ổ hoặc quyền ghi thư mục AgentyData."))
            return False

    def _update(self, cid, **kv):
        d = self._read(cid)
        if d is None:
            return
        d.update(kv)
        self._write(cid, d)
        if self.conv and self.conv["id"] == cid:
            self.conv.update(kv)
        self.refresh_chat_list()

    def save_conv(self):
        self.conv["updated"] = time.time()
        self.conv["model"] = self.cfg["default_chat_model"]
        self._write(self.conv["id"], self.conv)
        self.refresh_chat_list()

    def refresh_chat_list(self):
        while self.list_lay.count() > 1:
            w = self.list_lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        q = self.search.text().strip().lower()
        metas, n_archived = [], 0
        files = []
        for p in C.HISTORY_DIR.glob("*.json"):
            with contextlib.suppress(OSError):
                files.append((p.stat().st_mtime, p))
        uncached = sorted((f for f in files if (self._meta_cache.get(f[1].name) or (None,))[0] != f[0]), reverse=True)
        lazy = set()
        if len(uncached) > self.SYNC_READ and not q:
            # Nhiều file chưa có trong chỉ mục (lần đầu / vừa chuyển dữ liệu): đọc ngay các chat mới nhất,
            # phần còn lại lập chỉ mục ở luồng nền rồi vẽ lại danh sách
            lazy = {p for _, p in uncached[self.SYNC_READ:]}
            self._index_in_background(sorted(lazy))
        for _, p in files:
            if p in lazy:
                continue
            entry = self._chat_meta(p)
            if entry is None:
                continue
            meta, blob = entry
            n_archived += meta["archived"]
            if meta["archived"] != self.show_archived:
                continue
            if q and q not in blob:
                continue
            metas.append(meta)
        total = len(metas)
        if not lazy:
            self._save_index()
        metas.sort(key=lambda m: (not m["pinned"], -float(m["updated"] or 0)))
        metas = metas[:self._list_limit]
        if self.show_archived:
            sections = [("Đã lưu trữ", metas)]
        else:
            sections = [("Đã ghim", [m for m in metas if m["pinned"]]), ("Gần đây", [m for m in metas if not m["pinned"]])]
        cur = self.conv["id"] if self.conv else None
        pos = 0
        for label, items in sections:
            if not items:
                continue
            lab = QLabel(label)
            lab.setObjectName("SectionLabel")
            self.list_lay.insertWidget(pos, lab)
            pos += 1
            for meta in items:
                self.list_lay.insertWidget(pos, ChatRow(self, meta, meta["id"] == cur))
                pos += 1
        if total > len(metas):
            more = QPushButton(f"  Hiện thêm ({total - len(metas)})")
            more.setObjectName("Ghost")
            more.clicked.connect(self._show_more)
            self.list_lay.insertWidget(pos, more)
            pos += 1
        if pos == 0:
            empty = QLabel("Không tìm thấy đoạn chat" if q else ("Chưa có đoạn chat lưu trữ" if self.show_archived
                                                                 else "Chưa có đoạn chat nào"))
            empty.setObjectName("SectionLabel")
            self.list_lay.insertWidget(0, empty)
        self.archive_btn.setText("  Quay lại đoạn chat" if self.show_archived else f"  Đã lưu trữ ({n_archived})")

    LIST_LIMIT = 150
    SYNC_READ = 60

    def _index_in_background(self, paths):
        if getattr(self, "_indexer", None) is not None:
            return

        def read_all(paths=paths):  # chạy ở luồng nền: chỉ đọc file, không đụng giao diện
            out = {}
            for p in paths:
                with contextlib.suppress(OSError):
                    out[p] = (p.stat().st_mtime, p.read_text("utf-8"))
            return out

        def merged(result, err):
            self._indexer = None
            for p, (mtime, raw) in (result or {}).items():
                with contextlib.suppress(OSError, ValueError, TypeError, AttributeError):
                    self._meta_cache.pop(p.name, None)
                    self._chat_meta_from_text(p, mtime, raw)
            self._index_dirty = True
            self.refresh_chat_list()

        self._indexer = run_bg(read_all, on_done=merged)

    def _show_more(self):
        self._list_limit += self.LIST_LIMIT
        self.refresh_chat_list()

    def _chat_meta(self, p: Path):
        """(metadata, chữ để tìm) của một file lịch sử, đệm theo thời điểm sửa file."""
        try:
            mtime = p.stat().st_mtime
        except OSError:
            return None
        hit = self._meta_cache.get(p.name)
        if hit and hit[0] == mtime:
            return hit[1]
        try:
            raw = p.read_text("utf-8")
        except OSError:
            return None
        return self._chat_meta_from_text(p, mtime, raw)

    def _chat_meta_from_text(self, p: Path, mtime, raw: str):
        self._index_dirty = True
        try:
            d = json.loads(raw)
            if not isinstance(d, dict) or not d.get("id"):
                raise ValueError("sai cấu trúc")
            meta = {"id": str(d["id"]), "title": str(d.get("title") or "Đoạn chat"), "updated": d.get("updated", 0),
                    "pinned": bool(d.get("pinned", False)), "archived": bool(d.get("archived", False))}
            blob = (meta["title"] + "\n" + "\n".join(str(x.get("text") or "") for x in d.get("display", [])
                                                       if isinstance(x, dict))).lower()[:20000]
        except (OSError, ValueError, TypeError, AttributeError):
            self._meta_cache[p.name] = (mtime, None)
            return None
        self._meta_cache[p.name] = (mtime, (meta, blob))
        return meta, blob

    def _load_index(self) -> dict:
        """Chỉ mục lịch sử: mở 1 file thay vì 1.000 file (mỗi lần mở file mới bị diệt virus quét ~10 ms)."""
        try:
            raw = json.loads(self._index_path.read_text("utf-8"))
            return {k: (v[0], tuple(v[1]) if v[1] else None) for k, v in raw.items()} if isinstance(raw, dict) else {}
        except (OSError, ValueError, TypeError, IndexError, KeyError):
            return {}

    def _save_index(self):
        if not self._index_dirty:
            return
        alive = {p.name for p in C.HISTORY_DIR.glob("*.json")}
        self._meta_cache = {k: v for k, v in self._meta_cache.items() if k in alive}
        with contextlib.suppress(OSError):
            C.write_json(self._index_path, self._meta_cache)
            self._index_dirty = False

    def toggle_archived_view(self):
        if not self.sidebar.isVisible():
            self.toggle_sidebar()
        self.show_archived = not self.show_archived
        self.refresh_chat_list()

    def chat_menu(self, cid, anchor=None, pos=None):
        d = self._read(cid)
        if d is None:
            return
        m = PopMenu(self)
        m.row("Đặt lại tên", lambda: self.rename_chat(cid), "pencil", "Ctrl+Alt+R")
        m.row("Bỏ ghim" if d.get("pinned") else "Ghim", lambda: self.toggle_pin(cid), "pin", "Ctrl+Alt+P")
        m.row("Chia sẻ / xuất file", lambda: self.share_chat(cid, anchor), "share", "Ctrl+Shift+E")
        m.addSeparator()
        m.row("Bỏ lưu trữ" if d.get("archived") else "Lưu trữ", lambda: self.toggle_archive(cid), "archive", "Ctrl+Shift+A")
        m.row("Xoá", lambda: self.delete_chat(cid), "trash", color=DANGER)
        m.exec(pos or anchor.mapToGlobal(QPoint(0, anchor.height() + 4)))

    def rename_chat(self, cid):
        d = self._read(cid)
        if d is None:
            return
        dlg = QInputDialog(self)
        dlg.setWindowTitle("Đặt lại tên")
        dlg.setLabelText("Tên đoạn chat")
        dlg.setTextValue(d.get("title", ""))
        dlg.setOkButtonText("Lưu")
        dlg.setCancelButtonText("Huỷ")
        if dlg.exec() and dlg.textValue().strip():
            self._update(cid, title=dlg.textValue().strip()[:80])

    def toggle_pin(self, cid):
        d = self._read(cid)
        if d is not None:
            self._update(cid, pinned=not d.get("pinned", False))

    def toggle_archive(self, cid):
        d = self._read(cid)
        if d is None:
            return
        self._update(cid, archived=not d.get("archived", False), pinned=False)
        if self.conv and self.conv["id"] == cid and self.conv["archived"] and not self.worker:
            self.new_chat()

    def delete_chat(self, cid):
        if self.worker and self.conv and self.conv["id"] == cid:
            return
        d = self._read(cid) or {}
        box = QMessageBox(QMessageBox.Icon.Warning, "Xoá đoạn chat?",
                          f"Xoá “{d.get('title', 'Đoạn chat')}”? Không thể khôi phục.", parent=self)
        yes = box.addButton("Xoá", QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(box.addButton("Huỷ", QMessageBox.ButtonRole.RejectRole))
        box.exec()
        if box.clickedButton() is not yes:
            return
        self._path(cid).unlink(missing_ok=True)
        if self.conv and self.conv["id"] == cid:
            self.new_chat()
        self.refresh_chat_list()

    def open_chat(self, cid):
        if self.worker:
            return
        d = self._read(cid)
        if d is None:
            return
        self.conv = d
        self.conv.setdefault("pinned", False)
        self.conv.setdefault("archived", False)
        self._set_home(False)
        self.rerender_chat()
        self.refresh_chat_list()

    def new_chat(self):
        if self.worker:
            return
        self.conv = None
        self.attachments = []
        self.refresh_chips()
        self.refresh_chat_list()
        self.show_empty_state()

    # --- cài đặt / xoá ứng dụng ---
    def open_settings(self, first_run=False):
        dlg = SettingsDialog(self.cfg, self)
        if first_run:
            dlg.setWindowTitle("Chào mừng! Hãy nhập địa chỉ và khoá API để bắt đầu")
        ok = dlg.exec()
        if dlg.delete_requested:
            self.delete_app()
            return
        if not ok:
            return
        new = dlg.values()
        looks = any(new.get(k) != self.cfg.get(k) for k in ("theme", "font_size", "chat_width"))
        self.cfg = new
        C.save_config(self.cfg)
        self.input.enter_sends = self.cfg.get("enter_sends", True)
        if self.cfg.get("api_key"):
            self._load_server_models()
        if looks:
            if self.worker:
                QMessageBox.information(self, "Cài đặt", "Giao diện mới sẽ áp dụng sau khi trả lời xong và mở lại app.")
                return
            self.rebuild()

    def rebuild(self):
        """Dựng lại cửa sổ với chủ đề / cỡ chữ mới, giữ nguyên đoạn chat đang mở."""
        app = QApplication.instance()
        apply_theme(app, self.cfg.get("theme", "dark"), self.cfg.get("font_size", "medium"))
        w = MainWindow()
        w.setGeometry(self.geometry())
        if self.isMaximized():
            w.showMaximized()
        else:
            w.show()
        if self.conv:
            w.open_chat(self.conv["id"])
        w.input.setPlainText(self.input.toPlainText())
        w.attachments = list(self.attachments)
        w.refresh_chips()
        self.attachments = []  # đã chuyển sang cửa sổ mới
        app.main_window = w  # giữ tham chiếu để cửa sổ mới không bị thu gom
        self.close()

    def delete_app(self):
        frozen = getattr(sys, "frozen", False)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Xoá ứng dụng?")
        box.setText("Xoá toàn bộ dữ liệu của ứng dụng?")
        box.setInformativeText("Sẽ xoá vĩnh viễn: cài đặt, tất cả đoạn chat, mọi file PowerPoint, "
                               "Word, Excel và ảnh trong ứng dụng.\n\nFile đã tải xuống vẫn được giữ lại.\n"
                               "Ứng dụng sẽ tự đóng sau khi xoá.")
        exe_box = QCheckBox("Xoá luôn file chương trình (.exe)")
        if frozen:
            exe_box.setChecked(True)
            box.setCheckBox(exe_box)
        yes = box.addButton("Xoá hết", QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(box.addButton("Không xoá", QMessageBox.ButtonRole.RejectRole))
        box.exec()
        if box.clickedButton() is not yes:
            return
        if self.worker:
            self.worker.stop()
            self.worker.wait(3000)
        shortcuts.remove(self.cfg)
        shutil.rmtree(C.APP_DIR, ignore_errors=True)
        # Dọn nốt sau khi app thoát (file đang mở bị khoá, và .exe không tự xoá được khi đang chạy)
        cmd = f'ping 127.0.0.1 -n 3 >nul & rmdir /s /q "{C.APP_DIR}"'
        if frozen and exe_box.isChecked():
            cmd += f' & del /f /q "{sys.executable}"'
        subprocess.Popen(f'cmd /c "{cmd}"', creationflags=subprocess.CREATE_NO_WINDOW)
        QApplication.quit()

    def closeEvent(self, e):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            finished = self.worker.wait(10000)  # stream dừng ngay; code Python đang chạy thì phải đợi xong
            QApplication.restoreOverrideCursor()
            if not finished:  # không phá luồng đang ghi file: ẩn cửa sổ, tự đóng khi tác vụ xong
                e.ignore()
                self.hide()
                self.worker.finished.connect(self.close)
                return
        self.stop_speaking()
        super().closeEvent(e)

