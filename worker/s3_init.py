"""Seed object storage for `make up`: buckets datasets + models, commands_pool.jsonl,
and models/v1, models/v2 from the GitHub Release assets (tags model-v1, model-v2)
when they are not in the bucket yet. Runs as a one-off Pod with the worker image.
"""
import os

import requests
from botocore.exceptions import ClientError

from worker import s3_client

REPO = os.environ.get("GITHUB_REPO", "Nitheesh-Purnanand/cc_shreya")
s3 = s3_client()

for bucket in ("datasets", "models"):
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError:
        s3.create_bucket(Bucket=bucket)
        print(f"created bucket {bucket}")

s3.upload_file("/data/commands_pool.jsonl", "datasets", "commands_pool.jsonl")
print("uploaded s3://datasets/commands_pool.jsonl")

for version in ("v1", "v2"):
    if s3.list_objects_v2(Bucket="models", Prefix=f"{version}/").get("KeyCount"):
        print(f"models/{version}/ already present")
        continue
    r = requests.get(f"https://api.github.com/repos/{REPO}/releases/tags/model-{version}", timeout=30)
    if r.status_code != 200:
        print(f"no release model-{version} ({r.status_code}); upload it with `make upload-model`")
        continue
    for asset in r.json()["assets"]:
        body = requests.get(asset["browser_download_url"], timeout=300).content
        s3.put_object(Bucket="models", Key=f"{version}/{asset['name']}", Body=body)
        print(f"seeded s3://models/{version}/{asset['name']} ({len(body)} bytes)")
