"""Agentic loop: model tự gọi công cụ (tìm web, tải ảnh, chạy Python tạo file) và tự sửa lỗi code."""
import contextlib
import datetime
import json
import uuid
from pathlib import Path

import openai

import memory
import skills
import tools
from config import IMAGES_DIR, OUTPUT_DIR
from icons import SLIDE_ICONS as ICONS
from llm import make_client

MAX_STEPS = 24
MAX_FIX = 3
MAX_WEB_CALLS = 10  # tìm + đọc web mỗi lượt; quá mức thì dừng thay vì vòng lặp tốn thời gian  # số lần tự sửa code sau lần chạy lỗi đầu tiên

TOOL_SPECS = [
    {"type": "function", "function": {
        "name": "web_search",
        "description": "Tìm kiếm thông tin, tin tức, số liệu mới nhất trên Internet.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Từ khoá tìm kiếm"},
            "max_results": {"type": "integer", "default": 6}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "read_webpage",
        "description": "Đọc nội dung chữ sạch của một trang web để lấy chi tiết.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "search_and_download_images",
        "description": "Tìm ảnh thực tế trên mạng, tải về máy, kiểm tra ảnh hợp lệ. Trả local_image_paths để chèn vào PowerPoint/Word hoặc hiển thị.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Từ khoá ảnh, nên dùng tiếng Anh để có ảnh đẹp hơn"},
            "max_images": {"type": "integer", "default": 4}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "generate_ai_image",
        "description": "Vẽ ảnh mới bằng AI từ mô tả. Trả local_image_path. Dùng khi người dùng muốn vẽ tranh, hoặc khi không tìm được ảnh thật phù hợp.",
        "parameters": {"type": "object", "properties": {
            "prompt": {"type": "string", "description": "Mô tả chi tiết bức ảnh (tiếng Anh cho kết quả tốt nhất)"},
            "model": {"type": "string", "description": "Bỏ trống để dùng model mặc định"}}, "required": ["prompt"]}}},
    {"type": "function", "function": {
        "name": "edit_image",
        "description": "Sửa một ảnh có sẵn bằng AI theo mô tả (thêm / xoá vật, đổi nền, đổi màu, đổi phong cách, phục hồi ảnh cũ...). Ảnh gốc giữ nguyên, trả ảnh mới.",
        "parameters": {"type": "object", "properties": {
            "image_path": {"type": "string", "description": "Đường dẫn ảnh (ảnh người dùng đính kèm có ghi đường dẫn trong tin nhắn)"},
            "prompt": {"type": "string", "description": "Mô tả thay đổi, tiếng Anh cho kết quả tốt nhất; nói rõ giữ nguyên phần nào"}},
            "required": ["image_path", "prompt"]}}},
    {"type": "function", "function": {
        "name": "execute_python_file_processor",
        "description": "Chạy code Python để tạo/sửa file PowerPoint, Word, Excel, biểu đồ, xử lý dữ liệu. Lưu file vào OUTPUT_DIR. Nếu lỗi sẽ nhận traceback để sửa.",
        "parameters": {"type": "object", "properties": {"code": {"type": "string", "description": "Code Python đầy đủ"}},
                       "required": ["code"]}}},
    {"type": "function", "function": {
        "name": "list_directory",
        "description": "Liệt kê file/thư mục trong một thư mục trên máy người dùng (tên, loại, dung lượng, ngày sửa).",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Đường dẫn thư mục, ví dụ Desktop, Documents, Downloads hoặc đường dẫn đầy đủ"},
            "pattern": {"type": "string", "description": "Lọc theo mẫu glob, ví dụ *.docx", "default": "*"}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "read_local_file",
        "description": "Đọc nội dung chữ của một file trên máy (txt, md, csv, json, docx, xlsx, pptx, pdf...).",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "show_files_to_user",
        "description": "Hiện thẻ file (có nút Mở / Tải xuống) cho file đã sửa hoặc tìm thấy nằm ngoài OUTPUT_DIR.",
        "parameters": {"type": "object", "properties": {"paths": {"type": "array", "items": {"type": "string"}}},
                       "required": ["paths"]}}},
    {"type": "function", "function": {
        "name": "load_skill",
        "description": "Nạp hướng dẫn chi tiết của một skill (xem danh sách skill trong system prompt) trước khi làm việc thuộc skill đó.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "preview_file",
        "description": "Xem ảnh thật của file .pptx / .docx / .xlsx / .pdf vừa tạo (như khi in ra) để tự kiểm tra và sửa bố cục trước khi giao.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "pages": {"type": "string", "description": "Chỉ với PDF: trang cần xem, ví dụ '7' hoặc '5-8' (mặc định 4 trang đầu)"}},
            "required": ["path"]}}},
]
MEMORY_SPECS = [
    {"type": "function", "function": {
        "name": "remember",
        "description": "Ghi nhớ lâu dài một điều về người dùng (tên, công việc, sở thích, cách muốn được trả lời...).",
        "parameters": {"type": "object", "properties": {"text": {"type": "string", "description": "Một câu ngắn, rõ nghĩa"}},
                       "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "forget_memory",
        "description": "Xoá một điều đã ghi nhớ (theo id trong ngoặc vuông hoặc theo nội dung).",
        "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}}},
]
HISTORY_SPECS = [
    {"type": "function", "function": {
        "name": "search_past_chats",
        "description": "Tìm trong các đoạn chat trước đây với người dùng (khi họ nhắc 'lần trước', 'hôm trước mình có nói'...).",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
]


def tool_specs(cfg: dict) -> list:
    return TOOL_SPECS + (MEMORY_SPECS if cfg.get("memory_enabled", True) else []) + \
        (HISTORY_SPECS if cfg.get("history_enabled", True) else [])


def _memory_section(cfg: dict) -> str:
    if not cfg.get("memory_enabled", True):
        return ""
    return f"""
## Bộ nhớ về người dùng (giữ qua mọi đoạn chat)
{memory.prompt_block()}
- Dùng tự nhiên các điều trên để cá nhân hoá câu trả lời (xưng hô, mức độ chi tiết, sở thích); đừng nhắc lại cả danh sách.
- Khi người dùng chia sẻ điều lâu dài về bản thân (tên, nghề, gia đình, sở thích, cách muốn được trả lời) hoặc bảo "nhớ giúp",
  gọi remember với một câu ngắn. Không lưu điều nhất thời, mật khẩu, số tài khoản, thông tin nhạy cảm trừ khi họ yêu cầu rõ.
- Thông tin cũ sai hoặc người dùng bảo quên → forget_memory. Sau khi ghi nhớ, chỉ cần nói ngắn "(đã ghi nhớ)".
"""


def _skills_section() -> str:
    lines = "\n".join(f"- {s['name']}: {s['description']}" for s in skills.list_skills())
    return f"""
## Skills (hướng dẫn chuyên sâu, nạp bằng load_skill khi việc liên quan)
{lines}
- Làm bài thuyết trình / slide: BẮT BUỘC load_skill("slide-design") trước khi viết code, và làm đủ vòng tự kiểm tra bằng preview_file.
- Cần nguyên tắc chất lượng thiết kế: load_skill("impeccable"). Người dùng có thể nhập thêm skill khác trong Cài đặt.
"""


def system_prompt(cfg: dict | None = None) -> str:
    cfg = cfg or {}
    today = datetime.date.today().strftime("%d/%m/%Y")
    history = "- Có thể tra lại đoạn chat cũ bằng search_past_chats khi người dùng nhắc tới chuyện trước đây.\n" \
        if cfg.get("history_enabled", True) else ""
    return f"""Bạn là Agenty, một trợ lý AI hữu ích. Hôm nay là {today}.
{_memory_section(cfg)}{_skills_section()}{history}

## Cách nói chuyện
- Trả lời bằng ngôn ngữ người dùng đang dùng (mặc định tiếng Việt), xưng "mình" hoặc "tôi", gọi người dùng là "bạn".
- Rõ ràng, đúng trọng tâm; dùng Markdown (tiêu đề, gạch đầu dòng, bảng, khối code) khi giúp dễ đọc.
- Thông tin sức khoẻ, thuốc, pháp luật, tiền bạc: nói rõ ràng, nhắc hỏi bác sĩ/chuyên gia khi cần.
- Khi dùng thông tin trên mạng, ghi nguồn ngắn gọn bằng link ở cuối.

## Công cụ
- Câu hỏi về tin tức, giá cả, thời tiết, sự kiện, số liệu mới → gọi web_search (rồi read_webpage nếu cần chi tiết). Đừng đoán.
- Cần ảnh minh hoạ cho slide/tài liệu → search_and_download_images (từ khoá tiếng Anh). Không có ảnh hợp → generate_ai_image.
- Người dùng muốn vẽ tranh/tạo ảnh → generate_ai_image.
- Người dùng muốn SỬA ảnh có sẵn (thêm/xoá chi tiết, đổi nền, phục hồi ảnh cũ, đổi phong cách) → edit_image với đường dẫn ảnh.
  Việc đơn giản (cắt, xoay, đổi cỡ, chỉnh sáng / tương phản, ghép ảnh, thêm chữ, nén ảnh) → làm bằng Pillow trong
  execute_python_file_processor và lưu ảnh mới vào OUTPUT_DIR (nhanh, giữ nguyên chất lượng).
- Công thức toán: viết LaTeX trong \\( ... \\) hoặc $$ ... $$ (app tự vẽ công thức); code luôn để trong khối ```ngôn_ngữ.
- Tạo/sửa PowerPoint, Word, Excel, biểu đồ → execute_python_file_processor với MỘT đoạn code hoàn chỉnh cho mỗi file.
- Nếu code lỗi, bạn nhận traceback: đọc lỗi, sửa và gọi lại ngay, không hỏi người dùng.
- Sau khi tạo file xong, app tự hiện thẻ file có nút mở/lưu. KHÔNG dán đường dẫn file vào câu trả lời; chỉ tóm tắt ngắn file có gì.
- File người dùng đính kèm có đường dẫn trong tin nhắn; muốn sửa thì mở file đó bằng code và LƯU BẢN MỚI vào OUTPUT_DIR.

## Truy cập file trong máy
Bạn được phép xem và chỉnh file trên máy khi người dùng cần. Thư mục thường dùng: {tools.user_dirs()}
- Tìm file → list_directory; đọc → read_local_file; sửa / sắp xếp / đổi tên → execute_python_file_processor.
- Sửa file có sẵn: mặc định lưu bản mới cạnh file gốc (thêm " (đã sửa)" vào tên) để không mất bản cũ.
- Chỉ ghi đè, xoá, di chuyển hoặc đổi tên file của người dùng khi họ đã đồng ý rõ ràng trong đoạn chat. Hỏi trước, liệt kê đúng file sẽ bị ảnh hưởng.
- Không đụng tới thư mục hệ thống (Windows, Program Files, AppData) và không đọc mật khẩu, khoá bí mật.
- Sau khi sửa file nằm ngoài OUTPUT_DIR, gọi show_files_to_user để người dùng mở / tải được.

## Môi trường Python (đã import sẵn, không cần import lại)
OUTPUT_DIR = {OUTPUT_DIR}  (luôn lưu file kết quả vào đây)
IMAGES_DIR = {IMAGES_DIR}
Có sẵn: os, json, math, datetime, Path, Presentation, Inches, Pt, Emu, RGBColor, MSO_SHAPE, PP_ALIGN, MSO_ANCHOR,
docx, Document, openpyxl, matplotlib, plt, Image (Pillow), pandas as pd, xlrd, PdfReader, PdfWriter (pypdf), reportlab.
KHÔNG có seaborn, requests (tải web trong Python dùng httpx).

### PowerPoint — BẮT BUỘC dùng Deck (16:9, theme đồng bộ, số trang, icon, bóng đổ, tự chống tràn chữ)
deck = Deck(theme="medical_teal", footer="Tên bài")   # theme: navy_gold | emerald_cream | corporate_blue | sunset_terracotta | medical_teal | minimal_dark
Một "ý" (item) viết dạng (icon, "Tiêu đề", "Nội dung") — icon là một trong: {", ".join(ICONS)}. Có thể bỏ icon: ("Tiêu đề", "Nội dung").
deck.hero(title, subtitle="", image=None, note="", style="full")  # bìa; "full" = ảnh tràn slide + lớp phủ chuyển màu, "split" = ảnh bo góc bên phải
deck.agenda("Nội dung chính", items)                 # mục lục đánh số 3–6 mục (str hoặc ("Tiêu đề", "mô tả ngắn"))
deck.section("Tên chương", subtitle="", number=1, image=None)   # slide chia chương, số lớn
deck.split(title, items, image, image_side="right")  # 2–4 thẻ có icon + ảnh thật bo góc
deck.cards(title, items, columns=None)               # 2–6 thẻ có icon, bóng mềm (tự chia 2x2 hoặc 3 cột)
deck.stats(title, [("70%", "Nhãn", "mô tả ngắn"), ...], note="")   # 2–4 con số lớn nổi bật
deck.chart(title, kind, labels, values, insight, unit="")   # kind: bar | barh | line | pie | donut; kèm thẻ nhận xét nền đậm
deck.comparison(title, (icon, "Bên A", [ý...]), (icon, "Bên B", [ý...]))   # so sánh 2 cột / nên-không nên / trước-sau
deck.timeline(title, items)                          # quy trình 3–5 bước
deck.image_grid(title, [ảnh...], captions=[...])     # 2–4 ảnh bo góc kèm chú thích
deck.quote("Câu trích dẫn", author="", image=None)    # trích dẫn trên nền ảnh phủ tối
deck.statement(text, caption="")                     # 1 thông điệp lớn
deck.closing(title="Cảm ơn đã lắng nghe", subtitle="", image=None)
path = deck.save("ten_file.pptx")                    # lưu vào OUTPUT_DIR; in CẢNH BÁO nếu chữ quá dài
Tự vẽ thêm khi cần: slide, (x, y, w, h) = deck.blank_slide(title)  # vùng nội dung tính bằng inch
  add_text(slide, text, x, y, w, h, size=20, color="1F2937", font=FONT|TITLE_FONT, align, anchor, bullets)
  add_box(slide, x, y, w, h, fill, line=None, rounded=True, alpha=None, shadow=False); add_image(slide, path, x, y, w, h, radius=0.05)
  add_icon(slide, "leaf", x, y, size, color, badge="E0F4F1"); THEMES[tên] = dict màu (bg, card, border, title, text, muted, accent, dark, strong, soft, chart).
Cách làm một bộ slide ĐẸP (làm đủ, không bỏ bước):
1. Lên dàn ý trước: mỗi slide MỘT ý chính, tiêu đề là câu khẳng định ngắn (≤ 8 từ), không phải nhãn chung chung.
2. Ảnh: tìm 4–6 ảnh thật bằng search_and_download_images (từ khoá tiếng Anh cụ thể, ví dụ "green tea cup close up warm light").
   Ảnh bìa nên dùng generate_ai_image với mô tả điện ảnh, cùng một phong cách cho cả bài, KHÔNG có chữ trong ảnh
   (ví dụ: "cinematic photo of ..., soft natural light, shallow depth of field, muted {{màu theme}} tones, no text").
3. Cấu trúc gợi ý cho 8–12 slide: hero(full, ảnh) → agenda → split/cards → stats hoặc chart → section (nếu dài) → comparison/timeline → image_grid/quote → closing(ảnh).
   Luân phiên layout: không để 2 slide liền nhau cùng kiểu; xen slide nền đậm (section/statement/quote) để tạo nhịp.
4. Luôn gắn icon phù hợp cho thẻ (cards, split). Con số quan trọng → stats thay vì viết trong đoạn văn.
5. Chữ ngắn gọn: thẻ ≤ 25 từ, ý so sánh ≤ 12 từ. Viết tiếng Việt có dấu đầy đủ.
6. Nếu deck.save() in "CẢNH BÁO", rút gọn đúng các đoạn đó rồi chạy lại một lần.
7. Luôn gọi preview_file(path) sau khi lưu, tự chấm theo skill slide-design và sửa (tối đa 2 vòng).
Theme riêng từ bảng màu: Deck(theme=make_theme(primary="#hex", accent="#hex", bg="#hex", fg="#hex")).
Chọn theme hợp chủ đề (sức khoẻ → medical_teal / emerald_cream, kinh doanh → corporate_blue / navy_gold, ẩm thực - văn hoá → sunset_terracotta, công nghệ → minimal_dark).

### Word
doc = new_document(theme="corporate_blue")   # Heading có màu, giãn dòng 1.25, chữ Segoe UI
add_title(doc, "Tiêu đề", "phụ đề"); doc.add_heading("Mục", level=1); doc.add_heading("Mục nhỏ", level=2); doc.add_paragraph("...")
add_bullets(doc, ["ý 1", "ý 2"], numbered=False); add_table(doc, headers, rows)  # header tô màu
add_picture(doc, path, width_in=6, caption=None); add_chart_to_doc(doc, "bar", labels, values, caption="...")
save_document(doc, "ten_file.docx")

### Excel
wb = new_workbook(); ws = wb.active; ws.title = "Chi tiêu"
pos = write_table(ws, "TIÊU ĐỀ LỚN", headers, rows, money_cols=["Số tiền"], percent_cols=[], total_cols=None, subtitle=None)
# tiêu đề gộp ô, header đậm chữ trắng, viền, #,##0, hàng tổng =SUM(...), tự căn cột. Ô bắt đầu "=" là công thức (SUM, AVERAGE, IF, VLOOKUP...).
# pos = {{"header_row", "first_row", "last_row", "total_row"}} để thêm công thức; gọi autofit_columns(ws) nếu ghi thêm ô.
save_workbook(wb, "ten_file.xlsx")
Biểu đồ Excel thật: add_excel_chart(ws, "col"|"bar"|"line"|"pie", data_cols=["C"], cat_col="A", header_row=pos["header_row"],
  first_row=pos["first_row"], last_row=pos["last_row"], anchor="F3", title="...")
Định dạng có điều kiện, danh sách chọn (DataValidation), cố định dòng... dùng openpyxl trực tiếp.
File có công thức: sau khi lưu gọi recalculate_excel(path) để kết quả hiện sẵn khi mở bằng mọi phần mềm.

### Word nâng cao
add_page_numbers(doc)   # "Trang x / y" ở chân trang
add_toc(doc)            # mục lục tự động theo Heading (đặt ngay sau trang bìa; Word/WPS cập nhật khi mở)
docx_replace(doc, {{"{{{{ho_ten}}}}": "Nguyễn Văn An"}})   # điền mẫu / trộn thư, giữ định dạng — mở mẫu bằng Document(đường_dẫn)
doc.add_page_break()    # sang trang mới (vd. gộp nhiều thư mời vào một file)

### Đọc, xử lý, chuyển đổi file văn phòng
- read_local_file / file đính kèm đọc được: docx, doc, rtf, odt, xlsx, xls, csv (mọi bảng mã), pptx, ppt, pdf, txt, html.
  PDF scan (ảnh) sẽ có ảnh các trang gửi kèm — đọc chữ trong ảnh và chép lại chính xác.
- Bảng lớn / nhiều sheet: pd.read_excel(path, sheet_name=None) hoặc pd.read_csv(path, encoding="utf-8-sig") (CSV tiếng Việt
  bảng mã Windows: encoding="cp1258" rồi unicodedata.normalize("NFC", ...)). Lọc, gộp, tổng hợp, pivot bằng pandas
  rồi ghi kết quả ra Excel đẹp bằng write_table — đừng để file kết quả trông thô.
- Kiểm tra số liệu trước khi kết luận: tính lại bằng Python, nêu rõ số dòng đã xử lý, dòng lỗi / trống.
- Gộp / tách / xoay / trích trang PDF: PdfReader, PdfWriter.
- Chuyển định dạng: convert_file(path, "pdf" | "docx" | "xlsx" | "pptx" | "csv") — dùng Word / Excel / PowerPoint hoặc WPS trên máy.
- Tạo PDF: soạn bằng Word (new_document ...) rồi convert_file(đường_dẫn_docx, "pdf"). Nếu báo lỗi (máy không có Office)
  thì dùng reportlab với font = register_vn_fonts() (bản đậm: font + "-Bold").
- Sửa file của người dùng: mở bản gốc, giữ nguyên định dạng sẵn có, lưu bản mới "... (đã sửa)" trong OUTPUT_DIR.
- Với file Word / Excel / PDF quan trọng: gọi preview_file(path) để kiểm tra (bảng tràn lề, ngắt trang, công thức ra số) rồi mới giao.
"""


PREVIEW_REVIEW = ("[Ảnh xem trước tự động — không phải người dùng gửi] Đây là các slide vừa tạo. Hãy chấm như giám đốc "
                  "thiết kế theo danh sách kiểm tra của skill slide-design (chữ cắt/đè/quá nhỏ, khoảng trống, ảnh, nhịp "
                  "layout, tương phản). Có lỗi rõ ràng thì sửa code và lưu lại cùng tên file; tối đa 2 vòng sửa.")
DOC_REVIEW = ("[Ảnh xem trước tự động — không phải người dùng gửi] Đây là các trang đầu của file vừa tạo, như khi in ra. "
              "Kiểm tra: bảng có tràn lề / bị cắt cột không, tiêu đề và khoảng cách, ngắt trang, công thức có ra số, chữ "
              "tiếng Việt hiển thị đúng. Có lỗi rõ ràng thì sửa và lưu lại cùng tên; tối đa 2 vòng sửa.")
SCAN_LABEL = "[Ảnh các trang của PDF scan, gửi kèm tự động để bạn đọc nội dung — không phải người dùng gửi thêm]"


def _code_status(code: str) -> str:
    if "Deck(" in code or "pptx" in code or "Presentation(" in code:
        return "Đang thiết kế các trang slide PowerPoint..."
    if "new_document" in code or "Document(" in code or "docx" in code:
        return "Đang soạn tài liệu Word..."
    if "workbook" in code.lower() or "openpyxl" in code:
        return "Đang lập bảng tính Excel..."
    if "convert_file" in code:
        return "Đang chuyển định dạng file..."
    if "pd." in code or "PdfReader" in code or "PdfWriter" in code:
        return "Đang xử lý dữ liệu..."
    return "Đang xử lý..."


class Callbacks:
    """Giao diện nhận tiến trình. UI ghi đè các hàm này."""
    def delta(self, text: str): ...
    def status(self, text: str): ...
    def files(self, paths: list[str]): ...
    def images(self, paths: list[str]): ...
    def stopped(self) -> bool: return False


def build_user_message(text: str, attachments: list[str]) -> dict:
    parts, notes = [], []
    for path in attachments:
        p = Path(path)
        if p.suffix.lower() in tools.IMAGE_EXTS:
            parts.append({"type": "image_url", "image_url": {"url": tools.image_to_data_url(path)}})
            notes.append(f"[Ảnh đính kèm: {p.name} — đường dẫn: {p}]")
            continue
        try:
            content = tools.extract_file_text(path)
        except Exception as e:
            content, notes = None, notes + [f"(Lỗi đọc file: {e})"]
        if p.suffix.lower() == ".pdf" and tools.scanned_pages(content):
            with contextlib.suppress(Exception):
                imgs, note = tools.scan_attachments(path, content)
                parts += [{"type": "image_url", "image_url": {"url": tools.image_to_data_url(img, 1600)}} for img in imgs]
                notes.append(note)
        if content is None:
            notes.append(f"[File đính kèm: {p.name} — đường dẫn: {p}] (không đọc tự động được, có thể xử lý bằng Python)")
        else:
            notes.append(f"[File đính kèm: {p.name} — đường dẫn: {p}]\n<noi_dung_file>\n{content}\n</noi_dung_file>")
    full = "\n\n".join(notes + [text or "Hãy xem giúp file này."])
    if not parts:
        return {"role": "user", "content": full}
    return {"role": "user", "content": [{"type": "text", "text": full}] + parts}


KEEP_IMAGE_TURNS = 3      # số tin nhắn có ảnh (của người dùng) được giữ nguyên ảnh trong ngữ cảnh
OLD_TEXT_LIMIT = 24000    # tin nhắn cũ dài hơn mức này bị rút gọn (đầu + cuối)
AUTO_PREFIXES = ("[Ảnh xem trước tự động", "[Ảnh các trang của PDF scan")


def _text_of(m) -> str:
    c = m.get("content")
    return c if isinstance(c, str) else "\n".join(x.get("text", "") for x in (c or []) if x.get("type") == "text")


def compact_history(messages: list[dict]) -> None:
    """Rút gọn lịch sử cũ trước lượt mới để không tốn ngữ cảnh, nhưng không làm mất khả năng hỏi lại."""
    with_images = [i for i, m in enumerate(messages) if m["role"] == "user" and isinstance(m.get("content"), list)
                   and not _text_of(m).startswith(AUTO_PREFIXES)]
    keep = set(with_images[-KEEP_IMAGE_TURNS:])
    for i, m in enumerate(messages):
        if m["role"] == "tool" and len(m.get("content") or "") > 1500:
            m["content"] = m["content"][:1500] + "...(đã rút gọn)"
        if m["role"] == "user" and isinstance(m.get("content"), list) and i not in keep:
            note = "" if _text_of(m).startswith(AUTO_PREFIXES) else \
                "\n[Ảnh của tin nhắn này đã gỡ khỏi ngữ cảnh để tiết kiệm. Cần xem lại thì gọi preview_file(đường_dẫn_ảnh) ở trên.]"
            m["content"] = _text_of(m) + note
        if m["role"] in ("user", "assistant") and isinstance(m.get("content"), str) and len(m["content"]) > OLD_TEXT_LIMIT:
            c = m["content"]
            m["content"] = (c[:OLD_TEXT_LIMIT - 4000] + f"\n...(đã rút gọn {len(c) - OLD_TEXT_LIMIT:,} ký tự ở giữa; "
                            "file gốc vẫn đọc lại được bằng read_local_file)...\n" + c[-4000:])


def _stream_round(client, model, messages, cb, prefix, cfg):
    kwargs = dict(model=model, messages=[{"role": "system", "content": system_prompt(cfg)}] + messages,
                  tools=tool_specs(cfg))
    if cfg.get("effort"):
        kwargs["reasoning_effort"] = cfg["effort"]
    text, calls, emitted = "", {}, False
    try:
        for chunk in client.chat.completions.create(stream=True, **kwargs):
            if cb.stopped():
                break
            if not chunk.choices:
                continue
            d = chunk.choices[0].delta
            if d.content:
                if not emitted and prefix:
                    cb.delta(prefix)
                emitted = True
                text += d.content
                cb.delta(d.content)
            for tc in d.tool_calls or []:
                c = calls.setdefault(tc.index if tc.index is not None else 0, {"id": "", "name": "", "args": ""})
                c["id"] = c["id"] or (tc.id or "")
                if tc.function:
                    c["name"] = c["name"] or (tc.function.name or "")
                    c["args"] += tc.function.arguments or ""
    except (openai.APIConnectionError, openai.APIStatusError) as e:
        # Một số nhà cung cấp không hỗ trợ stream kèm tools: thử lại không stream
        if emitted or calls or isinstance(e, (openai.AuthenticationError, openai.PermissionDeniedError, openai.NotFoundError)):
            raise
        msg = client.chat.completions.create(**kwargs).choices[0].message
        text = msg.content or ""
        if text:
            cb.delta(prefix + text)
        calls = {i: {"id": t.id, "name": t.function.name, "args": t.function.arguments} for i, t in enumerate(msg.tool_calls or [])}
    out = [calls[k] for k in sorted(calls)]
    for c in out:
        c["id"] = c["id"] or f"call_{uuid.uuid4().hex[:12]}"
    return text, out


def _run_tool(name, args, cfg, cb, state):
    if name in ("web_search", "read_webpage"):
        state["web"] = state.get("web", 0) + 1
        if state["web"] > MAX_WEB_CALLS:
            return {"error": f"Đã dùng hết {MAX_WEB_CALLS} lượt tìm / đọc web cho câu hỏi này. Hãy trả lời bằng thông tin đã có, "
                             "nói rõ phần nào chưa xác minh được và nguồn nào bị chặn. Không đoán địa chỉ URL."}
    if name == "web_search":
        cb.status(f"Đang tìm kiếm thông tin trên mạng: “{args.get('query', '')}”...")
        return tools.web_search(args["query"], args.get("max_results", 6))
    if name == "read_webpage":
        cb.status("Đang đọc trang web để lấy thông tin chi tiết...")
        return tools.read_webpage(args["url"])
    if name == "search_and_download_images":
        cb.status("Đang tải hình ảnh minh hoạ phù hợp...")
        res = tools.search_and_download_images(args["query"], args.get("max_images", 4))
        if res["local_image_paths"]:
            cb.images(res["local_image_paths"])
        return res
    if name == "generate_ai_image":
        cb.status("Đang vẽ hình ảnh bằng AI (mất khoảng 30 giây)...")
        res = tools.generate_ai_image(args["prompt"], args.get("model"), cfg)
        if res.get("local_image_path"):
            cb.files([res["local_image_path"]])
        return res
    if name == "edit_image":
        cb.status("Đang sửa ảnh bằng AI (mất khoảng 30 giây)...")
        res = tools.edit_image(str(tools.resolve_path(args["image_path"])), args["prompt"], cfg)
        if res.get("local_image_path"):
            cb.files([res["local_image_path"]])
        return res
    if name == "execute_python_file_processor":
        if state["fails"] > MAX_FIX:
            return {"ok": False, "error": "Đã thử sửa nhiều lần không được. Dừng gọi công cụ này và xin lỗi người dùng ngắn gọn."}
        code = args.get("code", "")
        cb.status(f"Đang tự sửa lỗi và làm lại (lần {state['fails']}/{MAX_FIX})..." if state["fails"] else _code_status(code))
        ok, stdout, err, files = tools.execute_python(code)
        if ok:
            state["fails"] = 0
            if files:
                cb.files(files)
            return {"ok": True, "stdout": stdout, "created_files": files}
        state["fails"] += 1
        with contextlib.suppress(OSError):  # lưu lỗi để chẩn đoán sau (AgentyData/logs/code_errors.log)
            log = OUTPUT_DIR.parent / "logs"
            log.mkdir(exist_ok=True)
            with open(log / "code_errors.log", "a", encoding="utf-8") as f:
                f.write(f"\n===== {datetime.datetime.now():%d/%m/%Y %H:%M:%S}\n{err}\n--- code ---\n{code[:6000]}\n")
        left = MAX_FIX - state["fails"] + 1
        note = (f"Code bị lỗi. Hãy đọc traceback, sửa và gọi lại execute_python_file_processor (còn {left} lần thử)."
                if left > 0 else "Đã hết lượt sửa. Dừng lại và giải thích nhẹ nhàng cho người dùng.")
        return {"ok": False, "stdout": stdout, "traceback": err, "note": note}
    if name == "list_directory":
        cb.status("Đang xem thư mục trên máy...")
        return tools.list_directory(args["path"], args.get("pattern", "*"))
    if name == "read_local_file":
        path = tools.resolve_path(args["path"])
        cb.status(f"Đang đọc file {path.name}...")
        text = tools.extract_file_text(str(path))
        if path.suffix.lower() == ".pdf" and tools.scanned_pages(text):
            imgs, note = tools.scan_attachments(str(path), text)
            state.setdefault("attach", []).append((SCAN_LABEL + " " + note, imgs))
        return {"path": str(path), "content": text} if text is not None else \
            {"path": str(path), "note": "Không đọc tự động được loại file này; có thể xử lý bằng Python."}
    if name == "show_files_to_user":
        paths = [str(tools.resolve_path(p)) for p in args.get("paths", []) if tools.resolve_path(p).is_file()]
        if paths:
            cb.files(paths)
        return {"shown": paths}
    if name == "load_skill":
        cb.status(f"Đang đọc hướng dẫn: {args.get('name')}...")
        return skills.load_skill(args["name"])
    if name == "preview_file":
        path = tools.resolve_path(args["path"])
        slides = path.suffix.lower() in (".pptx", ".ppt")
        cb.status("Đang xem lại các slide để chỉnh cho đẹp..." if slides else f"Đang xem lại {path.name}...")
        try:
            images = tools.preview_images(str(path), tools.parse_pages(args.get("pages")))
        except Exception as e:
            return {"ok": False, "note": f"Máy không xuất được ảnh xem trước ({e}). Bỏ qua bước này."}
        state.setdefault("attach", []).append((PREVIEW_REVIEW if slides else DOC_REVIEW, images))
        return {"ok": True, "note": "Ảnh xem trước nằm ở tin nhắn ngay sau đây."}
    if name in ("remember", "forget_memory") and not cfg.get("memory_enabled", True):
        return {"ok": False, "error": "Người dùng đã tắt Bộ nhớ."}
    if name == "search_past_chats" and not cfg.get("history_enabled", True):
        return {"ok": False, "error": "Người dùng đã tắt tham chiếu lịch sử trò chuyện."}
    if name == "remember":
        cb.status("Đã cập nhật bộ nhớ")
        return memory.remember(args["text"])
    if name == "forget_memory":
        cb.status("Đã cập nhật bộ nhớ")
        return memory.forget(args["key"])
    if name == "search_past_chats":
        cb.status("Đang xem lại các đoạn chat trước...")
        return memory.search_chats(args["query"], cfg.get("_conv_id"))
    return {"error": f"Không có công cụ {name}"}


def run_agent(cfg: dict, model: str, messages: list[dict], cb: Callbacks) -> None:
    """Chạy tới khi model trả lời xong. `messages` được nối thêm các lượt assistant/tool."""
    client = make_client(cfg)
    state = {"fails": 0}
    has_text = False
    for _ in range(MAX_STEPS):
        if cb.stopped():
            return
        text, calls = _stream_round(client, model, messages, cb, "\n\n" if has_text else "", cfg)
        has_text = has_text or bool(text)
        if cb.stopped():  # dừng giữa lúc stream: tool call có thể chưa trọn → không lưu, chỉ giữ phần chữ
            if text:
                messages.append({"role": "assistant", "content": text})
            return
        msg = {"role": "assistant", "content": text or None}
        if calls:
            msg["tool_calls"] = [{"id": c["id"], "type": "function",
                                  "function": {"name": c["name"], "arguments": c["args"] or "{}"}} for c in calls]
        messages.append(msg)
        if not calls:
            return
        for c in calls:
            if cb.stopped():  # mỗi tool_call vẫn phải có phản hồi để lượt sau hợp lệ với API
                messages.append({"role": "tool", "tool_call_id": c["id"],
                                 "content": json.dumps({"error": "Người dùng đã dừng, công cụ không chạy."}, ensure_ascii=False)})
                continue
            try:
                result = _run_tool(c["name"], json.loads(c["args"] or "{}"), cfg, cb, state)
            except json.JSONDecodeError:
                result = {"error": "Tham số JSON không hợp lệ, hãy gọi lại với JSON đúng."}
            except Exception as e:
                result = {"error": f"{type(e).__name__}: {e}"}
            messages.append({"role": "tool", "tool_call_id": c["id"],
                             "content": json.dumps(result, ensure_ascii=False, default=str)})
        for label, images in state.pop("attach", []):
            # Ảnh không gửi được trong tin nhắn tool, nên gửi kèm như một tin nhắn người dùng ngay sau đó
            messages.append({"role": "user", "content": [{"type": "text", "text": label}] + [
                {"type": "image_url", "image_url": {"url": tools.image_to_data_url(p, 1400)}} for p in images]})
        if cb.stopped():
            return
    cb.delta("\n\n_(Đã chạy quá nhiều bước. Nhắn “tiếp tục” để làm nốt.)_")


def friendly_error(e: Exception) -> str:
    if isinstance(e, openai.AuthenticationError):
        return "Khoá API không đúng hoặc đã hết hạn. Vào Cài đặt để kiểm tra lại."
    if isinstance(e, openai.NotFoundError):
        return "Không tìm thấy model hoặc địa chỉ API. Hãy thử chọn model khác ở phía trên, hoặc kiểm tra Cài đặt."
    if isinstance(e, openai.RateLimitError):
        return "Máy chủ AI đang bận hoặc đã hết lượt dùng. Hãy đợi vài phút rồi thử lại nhé."
    if isinstance(e, openai.APIConnectionError):
        return "Không kết nối được tới máy chủ AI. Hãy kiểm tra mạng Internet hoặc địa chỉ API trong Cài đặt."
    if isinstance(e, openai.APIStatusError):
        return f"Máy chủ AI báo lỗi ({e.status_code}). Hãy thử lại sau ít phút.\n\nChi tiết: {str(e)[:300]}"
    return f"Có lỗi xảy ra: {str(e)[:300]}"
