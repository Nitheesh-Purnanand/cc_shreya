"""Command-parser inference service (Task 3).

Env: MODEL_URI (s3://bucket/prefix), MODEL_VERSION, S3_ENDPOINT, MAX_NEW_TOKENS,
     FAULT_INJECT ("1" replaces the model output with "not json"),
     S3_ACCESS_KEY / S3_SECRET_KEY (from a Kubernetes Secret).
"""
import json
import logging
import os
import pathlib
import socket
import threading
import time
from contextlib import asynccontextmanager

import inference
import jsonschema
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("service")

HERE = pathlib.Path(__file__).resolve().parent
SCHEMA_FILE = HERE / "schema.json" if (HERE / "schema.json").exists() else HERE.parent / "data" / "schema.json"
SCHEMA = json.loads(SCHEMA_FILE.read_text())["json_schema"]
MODEL_DIR = pathlib.Path(os.environ.get("MODEL_DIR", "/tmp/model"))

state = {"model": None, "tok": None}


def download_model(model_uri, dest):
    import boto3

    bucket, _, prefix = model_uri.removeprefix("s3://").partition("/")
    s3 = boto3.client("s3", endpoint_url=os.environ["S3_ENDPOINT"], region_name="us-east-1",
                      aws_access_key_id=os.environ["S3_ACCESS_KEY"],
                      aws_secret_access_key=os.environ["S3_SECRET_KEY"])
    dest.mkdir(parents=True, exist_ok=True)
    keys = [o["Key"] for o in s3.list_objects_v2(Bucket=bucket, Prefix=prefix.rstrip("/") + "/").get("Contents", [])]
    if not keys:
        raise RuntimeError(f"no objects under {model_uri}")
    for key in keys:
        s3.download_file(bucket, key, str(dest / pathlib.PurePosixPath(key).name))
    return keys


def load_model():
    try:
        t0 = time.time()
        uri = os.environ["MODEL_URI"]
        log.info("downloading model from %s (endpoint %s)", uri, os.environ["S3_ENDPOINT"])
        keys = download_model(uri, MODEL_DIR)
        log.info("downloaded %d files from %s in %.1fs", len(keys), uri, time.time() - t0)
        state["model"], state["tok"] = inference.load(str(MODEL_DIR))
        log.info("model %s ready after %.1fs", os.environ.get("MODEL_VERSION"), time.time() - t0)
    except Exception:
        log.exception("model load failed")
        os._exit(1)  # let Kubernetes restart the Pod


@asynccontextmanager
async def lifespan(app):
    if os.environ.get("SKIP_MODEL_LOAD") != "1":  # tests inject a fake model
        threading.Thread(target=load_model, daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)


class ParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)


def headers():
    return {"X-Model-Version": os.environ.get("MODEL_VERSION", "unknown"),
            "X-Served-By": os.environ.get("POD_NAME") or socket.gethostname()}


def validate(raw):
    """Return the parsed object if raw is valid against schema.json, else None."""
    try:
        obj = json.loads(raw)
        jsonschema.validate(obj, SCHEMA)
        return obj
    except (ValueError, jsonschema.ValidationError):
        return None


@app.get("/healthz")
def healthz():
    return {"status": "alive"}


@app.get("/readyz")
def readyz():
    if state["model"] is None:
        return JSONResponse({"status": "loading"}, status_code=503)
    return {"status": "ready"}


@app.post("/parse")
def parse(req: ParseRequest):
    if state["model"] is None:
        return JSONResponse({"error": "model_not_ready"}, status_code=503, headers=headers())
    raw = inference.generate(state["model"], state["tok"], req.text, int(os.environ.get("MAX_NEW_TOKENS", "48")))
    if os.environ.get("FAULT_INJECT") == "1":
        raw = "not json"
    obj = validate(raw)
    if obj is None:
        return JSONResponse({"error": "invalid_model_output"}, status_code=500, headers=headers())
    return JSONResponse(obj, headers=headers())
