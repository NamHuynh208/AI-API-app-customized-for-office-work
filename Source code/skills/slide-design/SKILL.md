---
name: slide-design
description: BẮT BUỘC nạp trước khi làm bất kỳ bài thuyết trình PowerPoint nào. Quy trình và tiêu chuẩn để slide đẹp như của một studio thiết kế — câu chuyện, bố cục, màu, chữ, ảnh, số liệu và vòng tự kiểm tra bằng ảnh xem trước.
---

# Thiết kế slide đẹp

Mục tiêu: người xem nhìn 3 giây là hiểu slide nói gì, và cả bộ trông như một studio làm — không phải template mặc định.

## 1. Câu chuyện trước, slide sau
- Viết dàn ý thành một mạch: **vấn đề → vì sao quan trọng → nội dung chính (3–5 ý) → bằng chứng / số liệu → hành động / kết luận**.
- Mỗi slide MỘT ý. Tiêu đề là **câu khẳng định** nói ra ý đó ("Trà xanh dẫn đầu về chất chống oxy hoá"), không phải nhãn chung chung ("Thành phần").
- 8–12 slide cho bài thông thường. Ít chữ hơn bạn nghĩ: thẻ ≤ 25 từ, gạch đầu dòng ≤ 12 từ, tối đa 4 ý mỗi slide.

## 2. Nhịp bố cục
- Mở bằng `hero(style="full")` có ảnh mạnh; đóng bằng `closing(image=...)`.
- Không để 2 slide liền nhau cùng layout. Cứ 3–4 slide nội dung sáng thì chèn 1 slide nền đậm (`section`, `statement`, `quote`) để tạo nhịp.
- Có con số → `stats` (2–4 số) hoặc `chart`. Đừng giấu con số trong đoạn văn.
- Có trình tự → `timeline`. Có hai mặt → `comparison`. Có nhiều hình đẹp → `image_grid`.
- Tránh dùng `cards` liên tục — tối đa 2 lần một bộ. Lưới thẻ giống hệt nhau là dấu hiệu của slide làm vội.

Khung gợi ý (10 slide): hero → agenda → split (bối cảnh, có ảnh) → stats → cards (lợi ích) → section → comparison hoặc timeline → chart → quote hoặc image_grid → closing.

## 3. Màu
- Quy tắc 60-30-10: 60% nền, 30% màu chính (tiêu đề, slide đậm), 10% màu nhấn (vạch, số, icon). Màu nhấn dùng tiết kiệm mới nổi.
- Chọn theme có sẵn hợp chủ đề, HOẶC tự tạo theme từ màu thương hiệu: `Deck(theme=make_theme(primary="#0F766E", accent="#F59E0B", bg="#F8FAFC", fg="#1E293B"))`.
- Chữ trên ảnh luôn có lớp phủ (hero/quote/closing đã tự làm). Không đặt chữ trực tiếp lên ảnh rối.

## 4. Chữ
- Phân cấp rõ: tiêu đề ≥ 1.6 lần chữ nội dung. Không quá 3 cỡ chữ trên một slide.
- Không viết hoa cả câu, không gạch chân, không chữ gradient. Nhấn mạnh bằng cỡ chữ và độ đậm.
- Viết tiếng Việt có dấu đầy đủ, câu ngắn, động từ mạnh.

## 5. Hình ảnh
- Ảnh là nửa giá trị của slide. Mỗi bộ cần 4–6 ảnh chất lượng, cùng tông.
- Ảnh bìa và ảnh chia chương: `generate_ai_image` với mô tả điện ảnh, cùng một câu phong cách cho cả bộ, ví dụ:
  "editorial photograph of …, soft natural window light, shallow depth of field, calm muted {màu theme} palette, no text, no watermark".
- Ảnh minh hoạ thật: `search_and_download_images` với từ khoá tiếng Anh cụ thể (vật thể + ánh sáng + bối cảnh), không dùng từ trừu tượng.
- Không dùng clip-art, ảnh có chữ/watermark, ảnh vỡ. Ảnh nào không hợp thì bỏ, đừng cố nhét.

## 6. Icon
- Mỗi thẻ có một icon mang nghĩa (heart cho tim mạch, shield cho đề kháng…). Không dùng icon chỉ để trang trí; không lặp một icon cho nhiều thẻ.

## 7. Số liệu
- Biểu đồ chỉ nói MỘT điều; tiêu đề slide nói luôn kết luận ("Doanh thu tăng 3 lần sau 2 năm").
- ≤ 6 cột / 5 lát bánh. Đơn vị rõ ràng. Thẻ "Nhận xét" giải thích ý nghĩa, không đọc lại số.

## 8. Vòng tự kiểm tra (bắt buộc)
Sau khi `deck.save(...)`:
1. Nếu có "CẢNH BÁO", rút gọn đúng đoạn đó.
2. Gọi `preview_file(path)` để xem ảnh thật của từng slide.
3. Chấm như giám đốc thiết kế, theo danh sách:
   - Chữ có bị cắt, đè, quá nhỏ (< 14pt) không? Có slide nào quá nhiều chữ?
   - Khoảng trống có cân không (không có vùng trống lớn vô nghĩa, không chật)?
   - Ảnh có hợp nội dung, cùng tông, không mờ, không lặp lại?
   - Có 2 slide liền nhau giống nhau không? Nhịp sáng/tối có đều?
   - Tương phản chữ/nền đủ đọc từ cuối phòng không?
4. Sửa các lỗi rõ ràng, lưu lại CÙNG tên file, xem trước lại. Tối đa 2 vòng sửa — đừng sửa vụn vặt mãi.
5. Trả lời người dùng: tóm tắt ngắn cấu trúc bài (không dán đường dẫn file).
