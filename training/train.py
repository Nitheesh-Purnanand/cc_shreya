"""Fine-tune Pythia-70M on the teacher replies (sequence-level distillation, Task 2).

Each example is "Command: <command>\nJSON: <teacher reply>" + EOS; the loss is
computed on the reply tokens only. Usage: python training/train.py CONFIG [--subset N]
"""
import argparse
import csv
import hashlib
import json
import pathlib
import random
import sys
import time

import torch
import yaml
from transformers import AutoModelForCausalLM, AutoTokenizer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "service"))
from inference import prompt_for


def encode(tok, text, reply, max_length):
    p = tok(prompt_for(text)).input_ids
    t = tok(" " + reply.strip()).input_ids + [tok.eos_token_id]
    ids = (p + t)[:max_length]
    labels = ([-100] * len(p) + t)[:max_length]
    return ids, labels


def batches(examples, batch_size, pad_id, gen):
    order = torch.randperm(len(examples), generator=gen).tolist()
    for i in range(0, len(order), batch_size):
        chunk = [examples[j] for j in order[i:i + batch_size]]
        n = max(len(ids) for ids, _ in chunk)
        ids = torch.full((len(chunk), n), pad_id)
        labels = torch.full((len(chunk), n), -100)
        mask = torch.zeros((len(chunk), n), dtype=torch.long)
        for k, (a, b) in enumerate(chunk):
            ids[k, :len(a)] = torch.tensor(a)
            labels[k, :len(b)] = torch.tensor(b)
            mask[k, :len(a)] = 1
        yield ids, labels, mask


def sha256_files(out_dir):
    lines = []
    for p in sorted(out_dir.iterdir()):
        if p.is_file() and p.name != "model.sha256":
            lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n")
    (out_dir / "model.sha256").write_text("".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--subset", type=int, default=0, help="train on the first N records only (0 = max_records)")
    a = ap.parse_args()
    cfg = yaml.safe_load(pathlib.Path(a.config).read_text())

    seed = cfg["seed"]
    random.seed(seed)
    torch.manual_seed(seed)
    gen = torch.Generator().manual_seed(seed)

    n = a.subset or cfg["max_records"]
    records = [json.loads(line) for line in pathlib.Path(cfg["train_file"]).read_text(encoding="utf-8").splitlines() if line.strip()][:min(n, cfg["max_records"])]
    tok = AutoTokenizer.from_pretrained(cfg["model_name"])
    model = AutoModelForCausalLM.from_pretrained(cfg["model_name"], dtype=torch.float32)  # checkpoint is fp16: NaN loss on CPU
    examples = [encode(tok, r["text"], r["teacher_raw"], cfg["max_length"]) for r in records]
    print(f"training on {len(examples)} records, {cfg['epochs']} epochs", flush=True)

    opt = torch.optim.AdamW(model.parameters(), lr=cfg["learning_rate"])
    model.train()
    losses = []
    for epoch in range(1, cfg["epochs"] + 1):
        t0, total, steps = time.time(), 0.0, 0
        for ids, labels, mask in batches(examples, cfg["batch_size"], tok.eos_token_id, gen):
            loss = model(input_ids=ids, attention_mask=mask, labels=labels).loss
            loss.backward()
            opt.step()
            opt.zero_grad()
            total += loss.item()
            steps += 1
        losses.append(total / steps)
        print(f"epoch {epoch}: loss {losses[-1]:.4f} ({time.time() - t0:.0f}s)", flush=True)

    loss_csv = pathlib.Path(cfg["loss_csv"])
    loss_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(loss_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["epoch", "loss"])
        w.writerows([[i, f"{v:.6f}"] for i, v in enumerate(losses, 1)])

    out = pathlib.Path(cfg["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out)
    tok.save_pretrained(out)
    sha256_files(out)
    print(f"saved model to {out} and loss to {loss_csv}")


if __name__ == "__main__":
    main()
