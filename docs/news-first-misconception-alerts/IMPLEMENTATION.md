# Implementation plan

## Phase N0 — Close the alert loop

- Chạy đủ chuỗi nguồn → chủ đề → quy định → claim → NLI → lưu tín hiệu → cảnh báo.
- Cảnh báo fail-closed khi thiếu nguồn, URL, claim, đoạn trích hoặc căn cứ pháp lý.
- Tổng hợp tín hiệu đã lưu theo cửa sổ thời gian và chống trùng bằng `dedupe_key`.
- Kiểm thử worker, repository, provenance và cooldown.

## Phase N1 — News-first foundation

- Chuẩn hóa `ContentItem` và lưu nhãn `NoiDungNguon` trong Neo4j.
- Chuyển bài báo thành payload dùng chung với pipeline hiện tại.
- Thêm worker và lịch chạy riêng, mặc định tắt bằng feature flag.
- Đổi ngôn ngữ giao diện từ kết luận “tin sai” sang “nguy cơ hiểu nhầm cần xác minh”.

## Phase N2 — Production gate

- Bổ sung registry nhiều nguồn báo, snapshot nội dung gốc và tuân thủ robots/điều khoản nguồn.
- Tạo gold set tiếng Việt và ngưỡng precision trước khi bật lịch production.
- Thêm bộ lọc nguồn, trạng thái duyệt và giải thích rủi ro trên Admin Portal.

## Phase N3 — Social expansion

- Thêm collector theo adapter cho Facebook, TikTok, YouTube, diễn đàn hoặc API được cấp phép.
