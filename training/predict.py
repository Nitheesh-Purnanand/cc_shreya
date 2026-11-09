"""Write {"id", "prediction"} lines for score.py using a local model dir or a HF model id.

Usage: python training/predict.py MODEL OUT.jsonl [--gold data/validation.jsonl] [--max-new-tokens 48]
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "service"))
from inference import generate, load

ap = argparse.ArgumentParser()
ap.add_argument("model")
ap.add_argument("out")
ap.add_argument("--gold", default="data/validation.jsonl")
ap.add_argument("--max-new-tokens", type=int, default=48)
a = ap.parse_args()

model, tok = load(a.model)
with open(a.gold, encoding="utf-8") as f, open(a.out, "w", encoding="utf-8") as out:
    for line in f:
        rec = json.loads(line)  # only rec["text"] reaches the model
        out.write(json.dumps({"id": rec["id"], "prediction": generate(model, tok, rec["text"], a.max_new_tokens)}) + "\n")
