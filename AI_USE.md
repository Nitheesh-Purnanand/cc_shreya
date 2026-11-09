# AI use

Tool: Claude Code (Anthropic, model Claude Opus 5.5), used in the terminal on
this repository. It wrote most of the code, manifests and documents, ran the
commands, and drafted the teacher prompt and the commit messages at my request.
Everything below was checked by running it; every number in the report and in
`results/` comes from a real run on my laptop.

| Task | What the AI did | How it was checked |
|------|-----------------|--------------------|
| 5 Network | Subnet table, working, NACL rules, explanation. | Recomputed every subnet value with Python `ipaddress`; `nacl_sim.py --check` gives 6/6; read each rule against the handout bullet it implements. |
| 1 Storage + labelling | k3d config, SeaweedFS manifest, worker, Jobs, `clean.py`. **Drafted `prompts/teacher_prompt.txt`** (I asked it to, to save time). | Smoke-tested the prompt on 3 pool commands first. Found phi3.5 adds notes and invented examples after the JSON, so `stop: ["\n"]` was added (replies are still stored exactly as generated, never edited). Checked that both shards together hold 3,000 distinct ids, and that re-running `clean.py --local data/teacher` reproduces `train.sha256`. Unit tests for the reject rules and sharding. |
| 2 Training | `train.py`, `predict.py`, configs, the distillation explanation. | First run gave `loss nan`: transformers 5 loads Pythia in its fp16 checkpoint dtype; fixed by loading in float32 (found by printing `model.dtype`). Loss curve in `training/loss.csv`. Scores come from `tools/score.py`, not from the AI. Hyper-parameters were compared on held-out teacher records 1501-1700 (never trained on), not on `validation.jsonl`. |
| 3 Service | FastAPI app, Dockerfile, pinned requirements (generated with `uv pip compile`). | Unit tests with a fake model (endpoints, headers, 500 on invalid output, FAULT_INJECT). Ran the container at `--cpus 1 --memory 1g` with 50 requests; checked `docker images` size and searched the image for weight files (none). |
| 4 Kubernetes | Deployment, Service, Ingress, HPA. | Every claim backed by command output saved in `results/task4_*`. |
| 6 CI | Makefile, tests, GitHub Actions workflow. | Ran `ruff`, `pytest` locally; the workflow ran on GitHub (links in the report), including a run that fails at the quality gate with the untrained model. |

Things the AI got wrong and I caught by running the code: fp16 NaN loss; a
rambling teacher reply that would have been rejected as invalid JSON; a broken
`teacher-eval` Makefile path; Docker build timeouts (added pip retries).

Rules kept: no teacher reply edited; no training on `data/validation.jsonl`; no
credentials in Git (`.env` is git-ignored, credentials reach Pods only through
Kubernetes Secrets); no weights in Git or in the image (they live in SeaweedFS
and in GitHub Releases).
