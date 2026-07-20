# Progress

## Current status

- Phase N0: hoàn thành phần code và kiểm thử.
- Phase N1: hoàn thành nền tảng nguồn báo; lịch production vẫn chủ động tắt.
- Phase N2: chưa bắt đầu.
- Phase N3: chưa bắt đầu.

## Completed

- Hợp đồng nội dung trung lập nguồn và metadata nguồn được giữ qua Neo4j.
- Worker báo dùng chung pipeline kiểm chứng với nguồn mạng xã hội.
- Claim được đối chiếu với từng quy định ứng viên và lưu thành `YKien`/`DOI_CHIEU`.
- Alert chỉ dùng tín hiệu có provenance đầy đủ, có cửa sổ tổng hợp và cooldown.
- Giao diện Admin mô tả đây là tín hiệu cần người xác minh.

## Verification

- Backend: 96 tests passed.
- Python compile check: passed.
- Frontend production build: passed; còn cảnh báo kích thước bundle hiện hữu.
- Diff whitespace check: passed.

## Core LAWGIC track

- Execution plan v2 và ba ADR đã hoàn thành.
- Phase L0 + Phase L1/PR-L1.2 đã hoàn thành: contract, ontology, temporal fixture, parser và immutable Neo4j writer Điều–Khoản–Điểm.
- Full backend suite hiện có 116 tests passed.
- V2 read/write/temporal/citation/amendment vẫn mặc định tắt; chưa chạy migration dữ liệu thật.

## Next task

Phase L2: Qdrant `legal_provision`, migration inventory dry-run, raw-source coverage và shadow parity; chưa migration apply.
