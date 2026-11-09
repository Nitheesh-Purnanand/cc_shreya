"""Shared student-model inference: used by the service and by training/predict.py."""


def prompt_for(text):
    return f"Command: {text}\nJSON:"


def load(model_dir):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.set_num_threads(1)  # one request per thread; the container gets 1 CPU
    tok = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForCausalLM.from_pretrained(model_dir, dtype=torch.float32)
    model.eval()
    return model, tok


def generate(model, tok, text, max_new_tokens):
    """Greedy decoding; returns the raw text after 'JSON:' up to the first newline."""
    import torch

    enc = tok(prompt_for(text), return_tensors="pt")
    with torch.no_grad():
        out = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False,
                             pad_token_id=tok.eos_token_id)
    new = tok.decode(out[0, enc["input_ids"].shape[1]:], skip_special_tokens=True)
    return new.split("\n", 1)[0].strip()
