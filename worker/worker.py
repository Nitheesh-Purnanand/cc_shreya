"""Teacher labelling worker (Task 1).

Takes the commands of datasets/commands_pool.jsonl whose line number (from 0)
% SHARD_COUNT == SHARD_INDEX, asks the teacher (Ollama phi3.5) for each one and
writes {"id", "text", "teacher_raw"} lines to datasets/teacher/shard-<SHARD_INDEX>.jsonl.

Env: SHARD_INDEX, SHARD_COUNT, S3_ENDPOINT, S3_ACCESS_KEY, S3_SECRET_KEY,
     OLLAMA_URL, PROMPT_FILE, LIMIT (0 = all lines).
"""
import json
import os
import pathlib
import sys

import boto3
import requests

MODEL = "phi3.5"
# stop at the first newline: phi3.5 otherwise appends notes and invented extra examples after the JSON line
OPTIONS = {"temperature": 0, "seed": 42, "num_predict": 128, "stop": ["\n"]}


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        region_name="us-east-1",
    )


def build_prompt(template, text):
    """The prompt file may contain {command}; otherwise the command is appended."""
    if "{command}" in template:
        return template.replace("{command}", text)
    return f"{template.rstrip()}\n\nCommand: {text}\nJSON:"


def ask_teacher(ollama_url, template, text):
    r = requests.post(
        f"{ollama_url}/api/generate",
        json={"model": MODEL, "prompt": build_prompt(template, text), "stream": False, "options": OPTIONS},
        timeout=600,
    )
    r.raise_for_status()
    return r.json()["response"]  # stored exactly as generated


def shard(records, index, count):
    return [rec for i, rec in enumerate(records) if i % count == index]


def main():
    index, count = int(os.environ["SHARD_INDEX"]), int(os.environ["SHARD_COUNT"])
    # LIMIT=N labels only the first N pool lines (quick runs); 0 = all 3,000
    limit = int(os.environ.get("LIMIT", "0"))
    template = pathlib.Path(os.environ.get("PROMPT_FILE", "/prompt/teacher_prompt.txt")).read_text(encoding="utf-8")
    s3 = s3_client()
    body = s3.get_object(Bucket="datasets", Key="commands_pool.jsonl")["Body"].read().decode("utf-8")
    records = [json.loads(line) for line in body.splitlines() if line.strip()]
    if limit:
        records = records[:limit]
    mine = shard(records, index, count)
    print(f"shard {index}/{count}: {len(mine)} commands", flush=True)
    out = []
    for n, rec in enumerate(mine, 1):
        raw = ask_teacher(os.environ["OLLAMA_URL"], template, rec["text"])
        out.append(json.dumps({"id": rec["id"], "text": rec["text"], "teacher_raw": raw}, ensure_ascii=False))
        if n % 10 == 0:
            print(f"shard {index}: {n}/{len(mine)}", flush=True)
    key = f"teacher/shard-{index}.jsonl"
    s3.put_object(Bucket="datasets", Key=key, Body=("\n".join(out) + "\n").encode("utf-8"))
    print(f"wrote s3://datasets/{key} ({len(out)} lines)", flush=True)


if __name__ == "__main__":
    sys.exit(main())
