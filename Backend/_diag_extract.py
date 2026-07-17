"""One-off diagnostic: read the stuck PDF from MinIO and try text extraction."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from app.main import _load_dotenv  # noqa
_load_dotenv()

import asyncpg
from urllib.parse import urlparse
from minio import Minio
from app.pipelines.legal.extract_text import extract_text

FILE_ID = sys.argv[1] if len(sys.argv) > 1 else "8a5e538c-e235-4a42-9b94-2d7afed3a5f1"


async def main():
    dsn = os.getenv("DATABASE_URL")
    conn = await asyncpg.connect(dsn)
    row = await conn.fetchrow(
        "SELECT filename, mime, storage_key FROM van_ban_files WHERE file_id=$1::uuid", FILE_ID
    )
    await conn.close()
    if not row:
        print("NO ROW for", FILE_ID); return
    print("filename:", row["filename"])
    print("mime    :", row["mime"])
    print("key     :", row["storage_key"])

    ep = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
    p = urlparse(ep)
    client = Minio(p.netloc or p.path, access_key=os.getenv("MINIO_ROOT_USER"),
                   secret_key=os.getenv("MINIO_ROOT_PASSWORD"), secure=p.scheme == "https")
    resp = client.get_object(os.getenv("MINIO_BUCKET_LEGAL", "legal-raw"), row["storage_key"])
    try:
        data = resp.read()
    finally:
        resp.close(); resp.release_conn()
    print("bytes   :", len(data))

    text = extract_text(data, row["filename"], row["mime"] or "")
    print("extracted chars:", len(text))
    print("----- preview (first 600) -----")
    print(text[:600])


asyncio.run(main())
