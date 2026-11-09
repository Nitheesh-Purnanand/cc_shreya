"""Clean the teacher shards into datasets/v1/train.jsonl (Task 1, step 6).

Reads every datasets/teacher/shard-*.jsonl object (or *.jsonl files in --local DIR),
removes bad records, writes the rest in id order to datasets/v1/train.jsonl, its
SHA-256 to datasets/v1/train.sha256 and the counts to datasets/v1/counts.json.

Reject reasons, checked in this order for every record:
  (a) teacher_raw is not valid JSON
  (b) not a JSON object with exactly the keys intent, date, time, place
  (c) intent is not one of the eight
  (d) a slot is neither null nor a non-empty string found in the command (case-insensitive)
Then (e): among the remaining records, duplicate commands (same text, case and
outer spaces ignored) are dropped, keeping the smallest id.

Usage: python worker/clean.py [--local DIR] [--out DIR]   (S3 env as in worker.py)
"""
import argparse
import hashlib
import json
import pathlib

KEYS = {"intent", "date", "time", "place"}
SCHEMA = pathlib.Path(__file__).resolve().parent.parent / "data" / "schema.json"  # repo: data/, image: /data/
INTENTS = set(json.loads(SCHEMA.read_text())["intents"])


def reject_reason(rec):
    try:
        obj = json.loads(rec["teacher_raw"])
    except ValueError:
        return "a"
    if not isinstance(obj, dict) or set(obj) != KEYS:
        return "b"
    if obj["intent"] not in INTENTS:
        return "c"
    text = rec["text"].lower()
    for k in ("date", "time", "place"):
        v = obj[k]
        if v is not None and not (isinstance(v, str) and v.strip() and v.lower() in text):
            return "d"
    return None


def clean(records):
    """Return (kept records in id order, counts dict)."""
    records = sorted(records, key=lambda r: r["id"])
    counts = {"input": len(records), "a": 0, "b": 0, "c": 0, "d": 0, "duplicates": 0, "kept": 0}
    seen, kept = set(), []
    for rec in records:
        why = reject_reason(rec)
        if why:
            counts[why] += 1
            continue
        key = rec["text"].strip().lower()
        if key in seen:
            counts["duplicates"] += 1
            continue
        seen.add(key)
        kept.append(rec)
    counts["kept"] = len(kept)
    assert counts["input"] == sum(counts[k] for k in ("a", "b", "c", "d", "duplicates", "kept"))
    return kept, counts


def to_jsonl(records):
    return "".join(json.dumps({"id": r["id"], "text": r["text"], "teacher_raw": r["teacher_raw"]}, ensure_ascii=False) + "\n"
                   for r in records).encode("utf-8")


def counts_table(c):
    rows = [("Input records", c["input"]), ("(a) not valid JSON", c["a"]), ("(b) keys not exactly intent/date/time/place", c["b"]),
            ("(c) intent not one of the eight", c["c"]), ("(d) slot not null and not in the command", c["d"]),
            ("(e) duplicate commands", c["duplicates"]), ("Kept", c["kept"])]
    return "| Count | Records |\n|---|---:|\n" + "".join(f"| {a} | {b} |\n" for a, b in rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", help="read shard-*.jsonl from this directory instead of S3")
    ap.add_argument("--out", default="data/v1", help="also write train.jsonl, train.sha256, counts here")
    a = ap.parse_args()

    s3 = None
    if a.local:
        texts = [p.read_text(encoding="utf-8") for p in sorted(pathlib.Path(a.local).glob("shard-*.jsonl"))]
    else:
        from worker import s3_client
        s3 = s3_client()
        keys = sorted(o["Key"] for o in s3.list_objects_v2(Bucket="datasets", Prefix="teacher/shard-").get("Contents", []))
        texts = [s3.get_object(Bucket="datasets", Key=k)["Body"].read().decode("utf-8") for k in keys]
    records = [json.loads(line) for t in texts for line in t.splitlines() if line.strip()]

    ids = [r["id"] for r in records]
    print(f"shards: {len(texts)}, records: {len(ids)}, distinct ids: {len(set(ids))} (repeats: {len(ids) - len(set(ids))})")

    kept, counts = clean(records)
    body = to_jsonl(kept)
    digest = hashlib.sha256(body).hexdigest()
    sha_line = f"{digest}  train.jsonl\n"
    print(counts_table(counts))
    print(sha_line, end="")

    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "train.jsonl").write_bytes(body)
    (out / "train.sha256").write_text(sha_line)
    (out / "counts.json").write_text(json.dumps(counts, indent=2) + "\n")
    (out / "counts.md").write_text(counts_table(counts))
    if s3:
        s3.put_object(Bucket="datasets", Key="v1/train.jsonl", Body=body)
        s3.put_object(Bucket="datasets", Key="v1/train.sha256", Body=sha_line.encode())
        s3.put_object(Bucket="datasets", Key="v1/counts.json", Body=json.dumps(counts, indent=2).encode())
        print("uploaded s3://datasets/v1/{train.jsonl,train.sha256,counts.json}")


if __name__ == "__main__":
    main()
