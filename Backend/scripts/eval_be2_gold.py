from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.intelligence.nli import nli_pair

KHOAN_PATTERN = re.compile(r"khoan_id:'([^']+)'\}\) SET .*?k\.noi_dung='([^']+)'", re.DOTALL)


def load_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing gold file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Gold file must contain a list: {path}")
    return data


def precision_at_k(rows: list[dict[str, Any]], k: int) -> dict[str, Any]:
    total = 0
    hit = 0
    for row in rows:
        expected = set(row.get("expected_khoan_ids") or row.get("khoan_ids") or [])
        predicted = list(row.get("predicted_khoan_ids") or [])[:k]
        if not expected:
            continue
        total += 1
        if expected.intersection(predicted):
            hit += 1
    return {"metric": f"precision@{k}", "total": total, "hits": hit, "value": hit / total if total else None}

def load_seed_khoan(root: Path) -> list[dict[str, str]]:
    seed_dir = root / "Data" / "seed" / "van_ban_mau"
    khoan: list[dict[str, str]] = []
    for path in sorted(seed_dir.glob("*.cypher")):
        text = path.read_text(encoding="utf-8")
        for khoan_id, noi_dung in KHOAN_PATTERN.findall(text):
            khoan.append({"khoan_id": khoan_id, "noi_dung": noi_dung})
    return khoan

def predict_links_from_seed(rows: list[dict[str, Any]], seed_khoan: list[dict[str, str]], k: int) -> list[dict[str, Any]]:
    predicted_rows: list[dict[str, Any]] = []
    for row in rows:
        content = str(row.get("content") or row.get("text") or "")
        scored = sorted(
            ((lexical_score(content, item["noi_dung"]), item["khoan_id"]) for item in seed_khoan),
            key=lambda item: item[0],
            reverse=True,
        )
        enriched = dict(row)
        enriched["predicted_khoan_ids"] = [khoan_id for score, khoan_id in scored[:k] if score > 0]
        predicted_rows.append(enriched)
    return predicted_rows

def lexical_score(left: str, right: str) -> float:
    left_tokens = set(tokens(left))
    right_tokens = set(tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)

def tokens(text: str) -> list[str]:
    stopwords = {"nghe", "noi", "điều", "dieu", "nay", "co", "có", "dung", "đúng", "khong", "không"}
    return [token for token in re.findall(r"[\w]+", text.lower(), flags=re.UNICODE) if len(token) > 1 and token not in stopwords]


async def eval_nli(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = 0
    correct = 0
    labels = {"khop", "mau_thuan", "khong_ro"}
    for row in rows:
        expected = row.get("label") or row.get("expected_label")
        if expected not in labels:
            continue
        premise = row.get("premise") or row.get("khoan_text") or ""
        hypothesis = row.get("hypothesis") or row.get("claim") or ""
        result = await nli_pair(premise, hypothesis)
        total += 1
        correct += int(result["label"] == expected)
    return {"metric": "nli_accuracy", "total": total, "correct": correct, "value": correct / total if total else None}


async def main() -> None:
    parser = argparse.ArgumentParser(description="BE2 gold evaluation. Reports only real metrics from provided gold files.")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    root = Path(args.root)
    results: list[dict[str, Any]] = []
    links_path = root / "Data" / "gold" / "links.json"
    nli_path = root / "Data" / "gold" / "nli.json"
    if links_path.exists():
        link_rows = load_json(links_path)
        if link_rows and not any(row.get("predicted_khoan_ids") for row in link_rows):
            link_rows = predict_links_from_seed(link_rows, load_seed_khoan(root), args.k)
        results.append(precision_at_k(link_rows, args.k))
    else:
        results.append({"metric": f"precision@{args.k}", "status": "missing_gold", "path": str(links_path)})
    if nli_path.exists():
        results.append(await eval_nli(load_json(nli_path)))
    else:
        results.append({"metric": "nli_accuracy", "status": "missing_gold", "path": str(nli_path)})
    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
