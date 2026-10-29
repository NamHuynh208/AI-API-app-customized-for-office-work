# Agenty — mã nguồn

Python 3.12 · PySide6 (Qt 6) · openai SDK · python-pptx / python-docx / openpyxl / pandas / pypdf · PyInstaller.

## Chạy từ mã nguồn

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python src\main.py
```

Lần đầu mở, nhập địa chỉ và khoá API trong Cài đặt (lưu ở `AgentyData/config.json`, đã nằm trong `.gitignore`).
Có thể đặt sẵn `config.json` (chép từ `config.example.json`) cạnh `src/` hoặc cạnh file `.exe` để làm giá trị ban đầu.

## Build file .exe

```bash
.venv\Scripts\python build_exe.py
```

Kết quả: `dist\Agenty.exe` (một file duy nhất). Nếu có `config.json` cạnh `build_exe.py`, nó sẽ được **nhúng vào exe** (kể cả khoá API) —
chỉ làm vậy với bản dùng riêng, đừng phát hành bản đó.

## Kiểm tra nhanh (không gọi API)

```bash
.venv\Scripts\python selftest.py
```

## Cấu trúc

| File | Việc |
|---|---|
| `src/main.py` | Điểm khởi động |
| `src/ui.py` | Giao diện: thanh tiêu đề tự vẽ, thanh bên, khung chat, Cài đặt, bộ nhớ, chia sẻ |
| `src/agent.py` | System prompt, khai báo tool, vòng lặp agent, tự sửa lỗi code, dừng an toàn |
| `src/tools.py` | Tìm web, đọc trang, ảnh (tìm / tạo / sửa), sandbox Python, đọc mọi loại file, xem trước, giọng nói |
| `src/render.py` | Markdown → HTML: bảng, code tô màu, công thức LaTeX |
| `src/pptx_design_engine.py` | `Deck`: theme, 12 layout, icon, hiệu ứng, chống tràn chữ |
| `src/office_helpers.py` | Word, Excel, chuyển đổi định dạng qua Office/WPS, PDF tiếng Việt |
| `src/voice.py` | Ghi âm, đọc to, xuất đoạn chat |
| `src/memory.py`, `src/skills.py` | Bộ nhớ dài hạn, hệ thống skill (thư mục `skills/`) |
| `src/config.py` | Thư mục dữ liệu `AgentyData` cạnh file chạy, đọc / ghi cấu hình |

Một số tính năng cần Microsoft Office hoặc WPS trên máy: đọc `.doc/.ppt/.rtf`, xuất PDF từ Office, tính lại công thức, xem trước file.

## Skill đi kèm

- `skills/slide-design` — hướng dẫn thiết kế slide của dự án.
- `skills/impeccable` — Apache License 2.0 (xem `skills/impeccable/NOTICE.txt`).

Thêm skill khác: Cài đặt → Skills → *Nhập skill từ thư mục…* (thư mục có `SKILL.md`).
