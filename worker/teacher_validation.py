"""Run the teacher on data/validation.jsonl with the same prompt and settings as Task 1.

Only the command text is sent; the labels are never shown to the teacher.
Usage: python worker/teacher_validation.py OUT.jsonl   (OLLAMA_URL, default http://localhost:11434)
"""
import json
import os
import pathlib
import sys

from worker import ask_teacher

template = pathlib.Path("prompts/teacher_prompt.txt").read_text(encoding="utf-8")
url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
with open("data/validation.jsonl", encoding="utf-8") as f, open(sys.argv[1], "w", encoding="utf-8") as out:
    for line in f:
        rec = json.loads(line)
        out.write(json.dumps({"id": rec["id"], "prediction": ask_teacher(url, template, rec["text"])}) + "\n")
