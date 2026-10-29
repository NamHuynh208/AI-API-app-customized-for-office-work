"""Markdown → HTML cho khung chat: công thức LaTeX (vẽ bằng matplotlib), code tô màu (pygments), bảng có viền."""
import base64
import html
import io
import re

import markdown as md_lib
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name, guess_lexer

_MATH_CACHE: dict = {}
FENCE = re.compile(r"```[ \t]*([\w+#.-]*)[^\n]*\n(.*?)(?:```|\Z)", re.S)  # code chưa đóng (đang stream) vẫn tô màu
MATH = [
    (re.compile(r"\$\$(.+?)\$\$", re.S), True),
    (re.compile(r"\\\[(.+?)\\\]", re.S), True),
    (re.compile(r"\\\((.+?)\\\)", re.S), False),
    # $...$: không có khoảng trắng sát dấu $ và phải giống công thức, để không nhầm với tiền ("5$ và 10$")
    (re.compile(r"(?<![\\$\w])\$(?=\S)([^$\n]*?[\\^_{}=][^$\n]*?)(?<=\S)\$(?![\w$])"), False),
]


def _clean_tex(tex: str) -> str:
    """matplotlib mathtext không hiểu vài lệnh LaTeX hay gặp: đổi sang dạng tương đương."""
    tex = tex.strip()
    for a, b in ((r"\dfrac", r"\frac"), (r"\tfrac", r"\frac"), (r"\displaystyle", ""), (r"\left.", ""),
                 (r"\right.", ""), (r"\le ", r"\leq "), (r"\ge ", r"\geq "), (r"\,", r"\ "), (r"\!", "")):
        tex = tex.replace(a, b)
    tex = re.sub(r"\\(?:text|textbf|mathrm|operatorname)\{([^{}]*)\}", lambda m: r"\mathrm{" + m.group(1).replace(" ", r"\ ") + "}", tex)
    tex = re.sub(r"\\begin\{(?:aligned|align\*?|gathered|split)\}|\\end\{(?:aligned|align\*?|gathered|split)\}", "", tex)
    return tex.replace("&", "")


def math_img(tex: str, display: bool, color: str) -> str:
    """Ảnh PNG (data URI) của công thức; nhiều dòng (\\\\) thì vẽ từng dòng. Lỗi → None."""
    key = (tex, display, color)
    if key in _MATH_CACHE:
        return _MATH_CACHE[key]
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    imgs = []
    for line in [x for x in _clean_tex(tex).split(r"\\") if x.strip()] or [""]:
        buf = io.BytesIO()
        try:  # tự vẽ thay vì mathtext.math_to_image để nền trong suốt (hợp cả chủ đề tối lẫn sáng)
            fig = Figure(figsize=(0.01, 0.01))
            FigureCanvasAgg(fig)
            fig.text(0, 0, f"${line}$", fontsize=15 if display else 12, color=color)
            fig.savefig(buf, dpi=200, format="png", transparent=True, bbox_inches="tight", pad_inches=0.03)
        except Exception:
            _MATH_CACHE[key] = None
            return None
        imgs.append(buf.getvalue())
    out = []
    from PIL import Image
    for data in imgs:
        w, h = Image.open(io.BytesIO(data)).size
        uri = "data:image/png;base64," + base64.b64encode(data).decode()
        out.append(f'<img src="{uri}" width="{w // 2}" height="{h // 2}" style="vertical-align: middle;">')
    res = ("<br>".join(out)) if display else out[0]
    _MATH_CACHE[key] = res
    return res


def _code_html(code: str, lang: str, idx: int, c: dict) -> str:
    try:
        lexer = get_lexer_by_name(lang) if lang else guess_lexer(code)
    except Exception:
        lexer = TextLexer()
    body = highlight(code.rstrip("\n"), lexer, HtmlFormatter(noclasses=True, nowrap=True, style=c["pygments"]))
    label = html.escape(lang or getattr(lexer, "name", "code").lower())
    return (f'<table width="100%" cellspacing="0" cellpadding="0" style="margin: 6px 0;">'
            f'<tr><td style="background:{c["code_head"]}; padding: 6px 12px; color:{c["muted"]}; font-size:12px;">'
            f'{label}<span style="float:right;">&nbsp;&nbsp;&nbsp;<a href="copy:{idx}" style="color:{c["muted"]};'
            f' text-decoration:none;">⧉ Sao chép</a></span></td></tr>'
            f'<tr><td style="background:{c["code_bg"]}; padding: 10px 12px;">'
            f'<pre style="font-family: Consolas, \'Cascadia Mono\', monospace; font-size: 13px; margin:0;">{body}</pre>'
            f'</td></tr></table>')


# Token giữ chỗ dùng ký tự Unicode vùng riêng (Private Use): văn bản thường không thể trùng (đã lọc khỏi đầu vào)
TOK_A, TOK_B = "\ue000", "\ue001"
SAFE_URL = re.compile(r"^(https?:|mailto:|copy:|#|data:image/(png|jpe?g|gif|webp);base64,)", re.I)
INLINE_CODE = re.compile(r"(`+)(.+?)\1", re.S)


def _escape_raw_html(text: str) -> str:
    """Nội dung chat không được thành HTML / script thật: escape '<' ngoài code (Markdown tự escape trong `code`)."""
    out, pos = [], 0
    for m in INLINE_CODE.finditer(text):
        out.append(text[pos:m.start()].replace("<", "&lt;"))
        out.append(m.group(0))
        pos = m.end()
    out.append(text[pos:].replace("<", "&lt;"))
    return "".join(out)


def _safe_urls(html_: str) -> str:
    """Bỏ link / ảnh có scheme nguy hiểm (javascript:, vbscript:, file:...)."""
    return re.sub(r'\b(href|src)="([^"]*)"',
                  lambda m: m.group(0) if SAFE_URL.match(html.unescape(m.group(2)).strip()) else f'{m.group(1)}="#"', html_)


def to_html(text: str, c: dict) -> tuple[str, list[str]]:
    """Trả (html, danh_sách_code) — code dùng cho nút "Sao chép" của từng khối."""
    codes, blocks, maths = [], [], []
    text = (text or "").replace(TOK_A, "").replace(TOK_B, "")

    def keep_code(m):
        codes.append(m.group(2))
        blocks.append(_code_html(m.group(2), m.group(1).lower(), len(codes) - 1, c))
        return f"\n\n{TOK_A}C{len(blocks) - 1}{TOK_B}\n\n"

    text = FENCE.sub(keep_code, text)
    for rx, display in MATH:
        def keep_math(m, display=display):
            img = math_img(m.group(1), display, c["ink"])
            maths.append(img if img else f"<code>{html.escape(m.group(0))}</code>")
            token = f"{TOK_A}M{len(maths) - 1}{TOK_B}"
            return f"\n\n{token}\n\n" if display else token
        text = rx.sub(keep_math, text)
    out = md_lib.markdown(_escape_raw_html(text), extensions=["tables", "sane_lists"], output_format="html")
    out = _safe_urls(out)  # chỉ lọc link của nội dung; ảnh công thức / code (đã an toàn) chèn sau
    pick = lambda items, i: items[int(i)] if int(i) < len(items) else ""
    out = re.sub(rf"<p>\s*{TOK_A}C(\d+){TOK_B}\s*</p>", lambda m: pick(blocks, m.group(1)), out)
    out = re.sub(rf"{TOK_A}C(\d+){TOK_B}", lambda m: pick(blocks, m.group(1)), out)
    out = re.sub(rf"<p>\s*({TOK_A}M\d+{TOK_B})\s*</p>", r'<p align="center">\1</p>', out)
    out = re.sub(rf"{TOK_A}M(\d+){TOK_B}", lambda m: pick(maths, m.group(1)), out)
    out = out.replace("<table>", f'<table cellspacing="0" cellpadding="8" style="border-collapse: collapse; '
                                  f'margin: 8px 0; border: 1px solid {c["line"]};">')
    return out, codes


def stylesheet(c: dict, fs: int) -> str:
    return f"""
body {{ color: {c['ink']}; font-family: 'Segoe UI'; font-size: {fs}px; }}
p {{ margin-top: 0px; margin-bottom: 10px; line-height: 150%; }}
li {{ margin-bottom: 4px; line-height: 150%; }}
h1 {{ font-size: {fs + 8}px; font-weight: 600; margin-top: 14px; margin-bottom: 8px; }}
h2 {{ font-size: {fs + 5}px; font-weight: 600; margin-top: 12px; margin-bottom: 6px; }}
h3 {{ font-size: {fs + 2}px; font-weight: 600; margin-top: 10px; margin-bottom: 4px; }}
a {{ color: {c['link']}; text-decoration: none; }}
code {{ font-family: Consolas, monospace; font-size: {fs - 2}px; background-color: {c['chip']}; }}
th {{ background-color: {c['th']}; font-weight: 600; border: 1px solid {c['line']}; padding: 8px 12px; text-align: left; }}
td {{ border: 1px solid {c['line']}; padding: 8px 12px; }}
blockquote {{ color: {c['muted']}; margin-left: 12px; padding-left: 12px; border-left: 3px solid {c['line']}; }}
hr {{ color: {c['line']}; }}
"""


def palette(theme: str) -> dict:
    if theme == "light":
        return dict(ink="#0D0D0D", muted="#5D5D5D", link="#1A6BD8", line="#DADADA", chip="#EFEFEF", th="#F4F4F4",
                    code_bg="#F7F7F8", code_head="#ECECEC", pygments="default")
    return dict(ink="#ECECEC", muted="#AFAFAF", link="#7AB7FF", line="#424242", chip="#2F2F2F", th="#2A2A2A",
                code_bg="#171717", code_head="#2F2F2F", pygments="monokai")


def page_html(title: str, body_md: str, theme: str = "light") -> str:
    """Trang HTML độc lập (dùng khi xuất / chia sẻ đoạn chat)."""
    c = palette(theme)
    body, _ = to_html(body_md, c)
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
            f"<style>{stylesheet(c, 15)} body {{ max-width: 820px; margin: 32px auto; padding: 0 16px; }}</style>"
            f"</head><body>{body}</body></html>")
