<p align="center"><img src="Source code/logo.svg" width="96" alt="Agenty"></p>

# Agenty — trợ lý AI cho công việc văn phòng

Ứng dụng chat AI cho Windows, giao diện tiếng Việt, chạy bằng **API OpenAI-compatible của chính bạn** (OpenAI hoặc bất kỳ nhà cung cấp nào có `/v1/chat/completions`). Không cần cài đặt: tải một file `.exe` là chạy.

**Làm được gì**

- Trò chuyện, tìm thông tin trên web có ghi nguồn, nhớ thông tin về bạn qua các đoạn chat (bật / tắt được).
- **Làm PowerPoint đẹp**: 12 kiểu slide, theme màu, icon, ảnh thật và ảnh AI, tự xem trước rồi sửa bố cục.
- **Word / Excel / PDF**: soạn báo cáo, hợp đồng, bảng tính có công thức và biểu đồ thật, trộn thư, xuất PDF, gộp / tách PDF.
- **Đọc file** docx, doc, rtf, xlsx, xls, csv (mọi bảng mã), pptx, ppt, pdf (cả bản scan), txt, html — đọc đúng bảng, đầu / chân trang, Track Changes, biểu đồ.
- Xem và chỉnh file trong máy khi bạn yêu cầu (lưu bản mới, hỏi trước khi ghi đè).
- Tạo ảnh và sửa ảnh bằng AI, nói để nhập, đọc to câu trả lời, công thức toán LaTeX, code tô màu.
- Sửa tin nhắn đã gửi, tạo lại câu trả lời, ghim / lưu trữ / tìm đoạn chat, xuất đoạn chat ra PDF / Word / HTML.

## Tải và chạy

1. Tải **`Agenty.exe`** trong repo này (hoặc mục *Releases*).
2. Đặt file vào một thư mục cố định, ví dụ `D:\Agenty\`, rồi mở. Dữ liệu (cài đặt, đoạn chat, file tạo ra) nằm trong thư mục `AgentyData` cạnh file `.exe`.
3. Lần đầu mở, nhập **Địa chỉ API** (ví dụ `https://api.openai.com/v1`) và **Khoá API** của bạn trong Cài đặt → *Kiểm tra kết nối* → *Lưu*.
4. Chọn model ở nút cạnh ô nhập → *Model khác…* để chọn đúng model nhà cung cấp của bạn có.

> Windows có thể cảnh báo "Windows protected your PC" vì file chưa có chữ ký số: chọn *More info → Run anyway*.

## Mã nguồn

Toàn bộ mã nguồn và hướng dẫn build nằm trong [`Source code/`](Source%20code/README.md).

## Lưu ý bảo mật

- Khoá API chỉ lưu trên máy bạn, trong `AgentyData\config.json` (không mã hoá) — đừng chia sẻ thư mục này.
- Ứng dụng cho AI chạy code Python và đọc / ghi file trên máy với quyền tài khoản Windows của bạn, **không có sandbox**. Chỉ dùng với nhà cung cấp API bạn tin tưởng, và giữ bản sao lưu cho file quan trọng.
