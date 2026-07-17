"""Bulk-import a folder of legal documents (PDF/DOCX/TXT/HTML) into the system.

For every matching file it:
  1) uploads the raw file to MinIO   -> POST /admin/legal/upload
  2) runs digitization on that file  -> POST /admin/ingest/legal  (parse -> Neo4j -> Qdrant,
     with automatic OCR fallback for scanned/image PDFs)

Each file is processed sequentially (OCR is CPU-heavy). A per-file status line is printed and a
CSV report is written next to the folder.

USAGE (from repo root, using the backend's Python interpreter):
    python Backend/scripts/bulk_import_legal.py "C:\\path\\to\\pdf_folder"
    python Backend/scripts/bulk_import_legal.py ./docs --pattern "*.pdf" --recursive
    python Backend/scripts/bulk_import_legal.py ./docs --api http://localhost:8000 \
        --email admin@local --password admin123 --visibility public

Notes:
  - The backend (:8000), MinIO (:9000) and Ollama (:11434, for embeddings) must be running.
  - so_hieu is derived from the filename (e.g. "01-2013-QD-UBND" -> "01/2013/QD-UBND"); if it can't
    be parsed, the filename stem is used. Pass --sohieu-from-name to always use the raw stem.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from pathlib import Path

try:
    import httpx
except Exception:  # noqa: BLE001
    print("Thiếu thư viện 'httpx'. Cài bằng: pip install httpx", file=sys.stderr)
    raise SystemExit(1)

EXTS = {".pdf", ".docx", ".txt", ".html", ".htm"}

# Matches "01/2013/QD-UBND", "168-2024-ND-CP", "15/2020/NĐ-CP", "03-2022-QH15" etc.
_SO_HIEU_RE = re.compile(r"(\d{1,4})[/\-_](\d{4})[/\-_]([A-Za-zĐđ][A-Za-zĐđ0-9.\-]*)")


def derive_so_hieu(filename: str, raw_stem: bool) -> str:
    stem = Path(filename).stem
    if raw_stem:
        return stem[:120]
    m = _SO_HIEU_RE.search(stem)
    if m:
        return f"{m.group(1)}/{m.group(2)}/{m.group(3)}".upper()
    return stem[:120]


def guess_mime(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".txt": "text/plain",
        ".html": "text/html",
        ".htm": "text/html",
    }.get(ext, "application/octet-stream")


def login(client: httpx.Client, base: str, email: str, password: str) -> str:
    r = client.post(f"{base}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    token = r.json().get("data", {}).get("token")
    if not token:
        raise SystemExit("Đăng nhập thất bại: không nhận được token.")
    return token


def main() -> int:
    ap = argparse.ArgumentParser(description="Bulk import legal documents into the knowledge graph.")
    ap.add_argument("folder", help="Thư mục chứa file cần số hóa")
    ap.add_argument("--pattern", default="*.pdf", help="Glob lọc file (mặc định *.pdf; dùng * để lấy tất cả)")
    ap.add_argument("--recursive", action="store_true", help="Duyệt cả thư mục con")
    ap.add_argument("--api", default="http://localhost:8000", help="BE3 API base URL")
    ap.add_argument("--email", default="admin@local")
    ap.add_argument("--password", default="admin123")
    ap.add_argument("--visibility", default="public", choices=["public", "internal"])
    ap.add_argument("--sleep", type=float, default=0.5, help="Nghỉ giữa các file (giây)")
    ap.add_argument("--timeout", type=float, default=600.0, help="Timeout mỗi file (giây); OCR có thể lâu")
    ap.add_argument("--sohieu-from-name", action="store_true", help="Luôn dùng nguyên tên file làm số hiệu")
    args = ap.parse_args()

    folder = Path(args.folder).expanduser()
    if not folder.is_dir():
        print(f"Không tìm thấy thư mục: {folder}", file=sys.stderr)
        return 1

    globber = folder.rglob if args.recursive else folder.glob
    if args.pattern in {"*", "*.*"}:
        files = sorted(p for p in globber("*") if p.is_file() and p.suffix.lower() in EXTS)
    else:
        files = sorted(p for p in globber(args.pattern) if p.is_file())
    if not files:
        print(f"Không có file nào khớp '{args.pattern}' trong {folder}")
        return 0

    print(f"Tìm thấy {len(files)} file. Bắt đầu import vào {args.api} ...\n")

    report_rows: list[dict[str, str]] = []
    counts = {"success": 0, "needs_review": 0, "queued": 0, "error": 0}

    with httpx.Client(timeout=args.timeout) as client:
        token = login(client, args.api, args.email, args.password)
        headers = {"Authorization": f"Bearer {token}"}

        for idx, path in enumerate(files, 1):
            so_hieu = derive_so_hieu(path.name, args.sohieu_from_name)
            prefix = f"[{idx}/{len(files)}] {path.name}"
            try:
                data = path.read_bytes()
                # 1) upload to MinIO
                up = client.post(
                    f"{args.api}/admin/legal/upload",
                    headers=headers,
                    files={"file": (path.name, data, guess_mime(path))},
                    data={"so_hieu": so_hieu, "visibility": args.visibility},
                )
                up.raise_for_status()
                file_id = up.json()["data"]["file_id"]

                # 2) ingest (parse -> Neo4j -> Qdrant, OCR fallback inside)
                ing = client.post(
                    f"{args.api}/admin/ingest/legal",
                    headers=headers,
                    json={"so_hieu": so_hieu, "ten": path.stem, "url_or_content": None, "file_ids": [file_id]},
                )
                ing.raise_for_status()
                d = ing.json()["data"]
                status = d.get("status", "error")
                counts[status] = counts.get(status, 0) + 1
                print(
                    f"{prefix}  -> {status.upper()}  "
                    f"({d.get('dieu_count', 0)} Điều / {d.get('khoan_count', 0)} Khoản, "
                    f"{d.get('indexed_count', 0)} vector)  so_hieu={so_hieu}"
                )
                report_rows.append({
                    "file": path.name, "so_hieu": so_hieu, "status": status,
                    "dieu": str(d.get("dieu_count", 0)), "khoan": str(d.get("khoan_count", 0)),
                    "indexed": str(d.get("indexed_count", 0)), "vb_id": str(d.get("vb_id", "")),
                    "message": str(d.get("message", "")),
                })
            except Exception as exc:  # noqa: BLE001
                counts["error"] = counts.get("error", 0) + 1
                print(f"{prefix}  -> ERROR: {exc}")
                report_rows.append({
                    "file": path.name, "so_hieu": so_hieu, "status": "error",
                    "dieu": "0", "khoan": "0", "indexed": "0", "vb_id": "", "message": str(exc),
                })
            if args.sleep:
                time.sleep(args.sleep)

    report_path = folder / "_import_report.csv"
    with open(report_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "so_hieu", "status", "dieu", "khoan", "indexed", "vb_id", "message"])
        writer.writeheader()
        writer.writerows(report_rows)

    print("\n================= TỔNG KẾT =================")
    print(f"  success      : {counts.get('success', 0)}")
    print(f"  needs_review : {counts.get('needs_review', 0)}  (VD: PDF scan OCR kém, layout lạ)")
    print(f"  queued       : {counts.get('queued', 0)}")
    print(f"  error        : {counts.get('error', 0)}")
    print(f"  Báo cáo chi tiết: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
