# AI use

Tool: Claude Code (Anthropic, model Claude Opus 5.5), used in the terminal on
this repository.

| Task | What the AI did | How I checked it |
|------|-----------------|------------------|
| Task 5 | Drafted `network/subnets.md` (working, table, explanation) and `network/nacl.json`. | Recomputed every subnet value with Python's `ipaddress` module; ran `python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check` (6/6 correct); read each NACL rule against the handout bullet it implements. |

What I did myself (not AI): wrote `prompts/teacher_prompt.txt`, wrote every
commit message.

Rules I kept: no teacher reply edited by hand or by AI; no training on
`data/validation.jsonl`; no credentials or weights in Git; all reported
numbers come from real runs.
