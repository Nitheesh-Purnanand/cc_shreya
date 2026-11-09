# CS3081 Mini Project: distilled command parser on a local cloud

A Pythia-70M student, fine-tuned on phi3.5 teacher replies (sequence-level
knowledge distillation), served by FastAPI on a k3d cluster with SeaweedFS
object storage. AI use is in `AI_USE.md`; command evidence is in `results/`.

## Prerequisites

Docker, k3d (v5), kubectl, make, Python 3.11+, openssl. For labelling:
Ollama with `phi3.5` on the laptop. For releases: the `gh` CLI.

## Build and deploy (fresh clone)

```bash
git clone https://github.com/Nitheesh-Purnanand/cc_shreya.git && cd cc_shreya
make up        # cluster + SeaweedFS + images + seed buckets/models from the GitHub Releases + app
```

`make up` creates `.env` with random S3 keys if it is missing (git-ignored;
`.env.example` shows the format). The keys reach Pods only through Kubernetes
Secrets. The service answers at `http://localhost:8080/parse`:

```bash
curl -X POST localhost:8080/parse -H 'content-type: application/json' -d '{"text":"what is the weather in london"}'
```

Ports 8080 (ingress) and 8333 (S3) come from `cluster/k3d.yaml`; if they are
taken, override them: `make up HTTP_PORT=8081 S3_PORT=8334`.

Tear down: `make down` (deletes the k3d cluster).

## Pipeline commands

| Step | Command |
|------|---------|
| Teacher labelling: two parallel Jobs in namespace `pipeline` (needs Ollama on the host) | `make label` |
| Clean shards into `datasets/v1/train.jsonl` + `train.sha256` (+ copy in `data/v1/`) | `make clean-data` |
| Re-check the checksum offline from the committed shards | `python worker/clean.py --local data/teacher --out /tmp/v1` |
| Train student v1 (reads only `training/config.yaml`) | `make train` |
| Quick check on the first 50 records | `make train SUBSET=50` |
| Train v2 (one more epoch) | `make train-v2` |
| Upload a model to `s3://models/<version>/` | `make upload-model VERSION=v1` |
| Publish a model as a GitHub Release asset | `make release VERSION=v1` |
| Score student and base Pythia on `validation.jsonl` | `make eval` |
| Score the teacher (same prompt and settings) | `make teacher-eval` |
| Lint / unit tests | `make lint` / `make test` |
| Load test through the ingress | `make loadtest` |
| NACL check | `python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check` |

`make train`, `make eval` and friends create `.venv` from `requirements-dev.txt`
on first use (CPU-only torch).

## Results so far (all from real runs; files in `results/`)

| Model | JSON validity | Intent | Date | Time | Place | Full frame |
|-------|--:|--:|--:|--:|--:|--:|
| Teacher phi3.5 | 98 | 84 | 69 | 84 | 89 | 46 |
| Base Pythia-70M | 0 | 0 | 0 | 0 | 0 | 0 |
| Student v1 (4 epochs) | 98 | 64 | 58 | 87 | 83 | 26 |
| Student v2 (5 epochs) | 93 | 73 | 59 | 74 | 80 | 36 |

- Cleaning (`data/v1/counts.md`): 3,000 input = 2 (a) + 0 (b) + 20 (c) + 278 (d) + 47 duplicates + 2,653 kept.
- Container at 1 CPU / 1 GiB: 50 sequential requests, no OOM kill, peak 565.4 MiB, image 1.72 GB.
- Cold start (creation to Ready): 6, 7, 7 s, median 7 s.
- Load test (2 replicas, standard command): 250 requests, 5 failures (2.0%, all
  HTTP 500 `invalid_model_output` on 2 validation commands), p50 1,800 ms,
  p95 3,400 ms; replicas served 122 / 123.
- CI: passing run https://github.com/Nitheesh-Purnanand/cc_shreya/actions/runs/42552037150,
  quality-gate failure with the untrained model https://github.com/Nitheesh-Purnanand/cc_shreya/actions/runs/42552046162.

## Not done yet

- Task 4: rolling update v1 to v2 plus rollback under load, recovery test, HPA 1-2-1 evidence.
- Task 7: cost, SLO and review table.
- `report/report.pdf`.
- The 2% failure rate is above the 1% target. It comes from student outputs that
  fail schema validation; a better-trained student is the fix.

## Notes

- All 3,000 pool commands were labelled (the worker supports `LIMIT=N` for quick runs).
- The teacher call uses temperature 0, seed 42, num_predict 128, and stops at the
  first newline (phi3.5 otherwise appends notes after the JSON). Replies are
  stored exactly as generated.
- Model weights are never in Git or in the image: they live in SeaweedFS
  (`models/v1`, `models/v2`) and in the GitHub Releases `model-v1` and `model-v2`.

Data: commands from SLURP (Bastianelli et al., EMNLP 2020), CC BY 4.0.
