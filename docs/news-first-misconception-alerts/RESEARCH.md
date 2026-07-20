# Research: News-first misconception alerts

## Scope

Rà soát luồng cảnh báo hiểu nhầm hiện tại và thiết kế nền tảng bắt đầu từ báo điện tử, sau đó mở rộng sang bài đăng, video, bình luận và diễn đàn.

## Findings

- Luồng cũ dừng sau phân loại chủ đề và liên kết pháp luật, rồi gọi tạo cảnh báo với danh sách tín hiệu rỗng.
- Kết quả NLI chưa được lưu nên không có bằng chứng claim-level để tổng hợp cảnh báo.
- Khóa chống trùng được đọc từ `AlertMeta.uuid` nhưng giá trị truy vấn lại là khóa chủ đề/quy định.
- Mô hình `SocialPost` gắn chặt với nền tảng, gây khó khi thêm nguồn báo.

## Design decision

Dùng một hợp đồng `ContentItem` trung lập nguồn, giữ tương thích với `SocialPost`, và chỉ tạo cảnh báo khi claim, đoạn trích nguồn, URL, quy định pháp luật và kết quả đối chiếu đã được lưu đầy đủ.

