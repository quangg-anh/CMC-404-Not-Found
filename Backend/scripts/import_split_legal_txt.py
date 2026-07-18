from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# Ensure Backend/ is on path and .env is loaded (same as app.main)
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def _load_dotenv() -> None:
    env_path = _BACKEND_ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_dotenv()

from app.api.deps import get_db_pool, get_embedder, get_minio, get_neo4j_driver, get_qdrant_client
from app.config import get_config
from app.pipelines.legal.normalize import normalize_so_hieu
from app.services.diff_facade import LegalDiffFacade

_META_RE = {
    "title": re.compile(r"^TIÊU ĐỀ:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
    "so_hieu": re.compile(r"^SỐ HIỆU:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
    "ngay_ban_hanh": re.compile(r"^NGÀY BAN HÀNH:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
    "co_quan_ban_hanh": re.compile(r"^CƠ QUAN BAN HÀNH:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
    "body": re.compile(r"^NỘI DUNG:\s*\n(.+)$", re.IGNORECASE | re.MULTILINE | re.DOTALL),
}

_TAX_KEYWORDS = (
    "thuế",
    "thue",
    "hoàn thuế",
    "hoan thue",
    "quản lý thuế",
    "quan ly thue",
    "giá trị gia tăng",
    "gia tri gia tang",
    "gtgt",
    "thu nhập",
    "thu nhap",
    "thuế thu nhập",
    "thuế tiêu thụ",
    "thuế xuất khẩu",
    "thuế nhập khẩu",
    "hóa đơn",
    "hoa don",
    "hải quan",
    "hai quan",
)


def _read_text(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1258"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def _match(name: str, text: str) -> str:
    m = _META_RE[name].search(text)
    return (m.group(1).strip() if m else "").strip()


def parse_file(path: Path) -> dict[str, Any]:
    raw = _read_text(path)
    so_hieu = _match("so_hieu", raw)
    title = _match("title", raw)
    body = _match("body", raw) or raw
    ngay_ban_hanh = _match("ngay_ban_hanh", raw)
    co_quan_ban_hanh = _match("co_quan_ban_hanh", raw)
    if not so_hieu:
        stem = re.sub(r"^\d+_", "", path.stem).replace("_", "/", 2).replace("_", "-")
        so_hieu = stem
    return {
        "so_hieu": so_hieu,
        "ten": title or path.stem,
        "url_or_content": body,
        "ngay_ban_hanh": ngay_ban_hanh or None,
        "co_quan_ban_hanh": co_quan_ban_hanh or None,
        "source_filename": path.name,
        "visibility": "public",
        "run_ner": False,
    }

def _is_tax_file(path: Path) -> bool:
    haystack = f"{path.name}\n{_read_text(path)[:20000]}".lower()
    return any(keyword in haystack for keyword in _TAX_KEYWORDS)


async def _existing_so_hieu(driver: Any) -> set[str]:
    items: set[str] = set()
    if not (driver and hasattr(driver, "session")):
        return items
    query = "MATCH (v:VanBanPhapLuat) RETURN v.so_hieu AS so_hieu"
    try:
        async with driver.session() as session:
            res = await session.run(query)
            async for row in res:
                if row.get("so_hieu"):
                    items.add(str(row["so_hieu"]))
    except Exception:
        return items
    return items


async def main() -> int:
    parser = argparse.ArgumentParser(description="Import các file .txt đã tách vào Neo4j/Qdrant.")
    parser.add_argument("folder", type=Path, help="Thư mục chứa các file .txt đã tách")
    parser.add_argument("--limit", type=int, default=50, help="Số file nhập tối đa mỗi lượt; 0 = nhập hết")
    parser.add_argument("--offset", type=int, default=0, help="Bỏ qua N file đầu")
    parser.add_argument("--manifest", type=Path, default=Path("import_split_legal_manifest.jsonl"), help="File log kết quả")
    parser.add_argument("--skip-existing", action="store_true", help="Bỏ qua văn bản đã có cùng số hiệu")
    parser.add_argument("--no-vectors", action="store_true", help="Không index Qdrant để nhập nhanh hơn")
    parser.add_argument("--tax-only", action="store_true", help="Chỉ nhập file có nội dung/tên liên quan thuế")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ liệt kê file được chọn, không nhập database")
    args = parser.parse_args()

    all_files = sorted(args.folder.glob("*.txt"))
    if args.tax_only:
        files = []
        matched = 0
        wanted = None if not args.limit or args.limit <= 0 else args.offset + args.limit
        for path in all_files:
            if not _is_tax_file(path):
                continue
            matched += 1
            if matched <= args.offset:
                continue
            files.append(path)
            if wanted is not None and matched >= wanted:
                break
    else:
        files = all_files
        if args.offset:
            files = files[args.offset:]
        if args.limit and args.limit > 0:
            files = files[: args.limit]

    if args.dry_run:
        for index, path in enumerate(files, start=args.offset + 1):
            payload = parse_file(path)
            print(f"[{index}] {path.name} | {payload['so_hieu']} | {payload['ten']}")
        print(json.dumps({"total_selected": len(files)}, ensure_ascii=False, indent=2))
        return 0

    driver = await get_neo4j_driver()
    pool = await get_db_pool()
    qdrant = None if args.no_vectors else await get_qdrant_client()
    embedder = None if args.no_vectors else await get_embedder(get_config())
    minio = await get_minio()
    existing = await _existing_so_hieu(driver) if args.skip_existing else set()
    facade = LegalDiffFacade(pool=pool, neo4j_driver=driver, qdrant=qdrant, embedder=embedder, minio=minio)

    done = 0
    skipped = 0
    failed = 0
    review = 0
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    with args.manifest.open("a", encoding="utf-8") as log:
        for index, path in enumerate(files, start=args.offset + 1):
            payload = parse_file(path)
            so_hieu_norm = normalize_so_hieu(payload["so_hieu"])
            if so_hieu_norm in existing:
                skipped += 1
                log.write(json.dumps({"file": str(path), "so_hieu": so_hieu_norm, "status": "skipped_existing"}, ensure_ascii=False) + "\n")
                log.flush()
                print(f"[{index}] SKIP {path.name} ({so_hieu_norm})")
                continue
            try:
                res = await facade.ingest_document(payload)
                status = res.get("status")
                if status == "success":
                    done += 1
                elif status == "needs_review":
                    review += 1
                else:
                    failed += 1
                log.write(json.dumps({"file": str(path), "payload": {k: v for k, v in payload.items() if k != "url_or_content"}, "result": res}, ensure_ascii=False) + "\n")
                log.flush()
                print(f"[{index}] {status.upper()} {path.name} -> {res.get('so_hieu')} ({res.get('dieu_count', 0)} điều, {res.get('khoan_count', 0)} khoản)")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                log.write(json.dumps({"file": str(path), "so_hieu": payload.get("so_hieu"), "status": "error", "error": str(exc)}, ensure_ascii=False) + "\n")
                log.flush()
                print(f"[{index}] ERROR {path.name}: {exc}")

    print(json.dumps({"total_selected": len(files), "done": done, "skipped": skipped, "needs_review": review, "failed": failed, "manifest": str(args.manifest)}, ensure_ascii=False, indent=2))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
