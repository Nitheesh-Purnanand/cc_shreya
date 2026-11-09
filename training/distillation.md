# Sequence-level vs logit-based distillation (Task 2, step 7)

**What sequence-level distillation trains on.** The teacher (phi3.5) is run once
over the commands and its *generated output text*, the final JSON string chosen
by greedy decoding, becomes the training target. The student (Pythia-70M) is
fine-tuned with ordinary next-token cross-entropy on
`Command: <command>\nJSON: <teacher reply>`, with the loss computed only on the
reply tokens. The student never sees the teacher's probabilities, only one
"hard" sequence per input: the teacher's best guess (Kim and Rush, 2016,
approximate the teacher's sequence distribution by its mode in this way).

**What logit-based distillation trains on.** Word-level (logit-based)
distillation trains the student to match the teacher's full *probability
distribution over the vocabulary at every token position*, usually by
minimising the KL divergence between the teacher's and the student's softmax
outputs (often softened with a temperature), sometimes mixed with the normal
cross-entropy loss. These soft targets carry more information than one
sequence: how likely the teacher thought every alternative token was ("dark
knowledge"), for example that `calendar_query` was a close second to
`calendar_set`.

**Why logit-based distillation is not possible here.**
1. *Different vocabularies.* phi3.5 uses a 32k-token Llama-style tokenizer;
   Pythia-70M uses the 50k-token GPT-NeoX tokenizer. A per-position KL needs the
   two distributions over the same vocabulary and the same token positions, and
   the same JSON string is split into different tokens by each model.
2. *The teacher interface returns text.* Ollama's `/api/generate` returns the
   generated string. It does not give the full vocabulary distribution at every
   step, so the teacher's logits are not available to train on. Keeping them
   for 1,500 examples x ~30 tokens x 32k entries would also need a lot of storage.
3. The assignment fixes the setup: train only on the teacher's stored replies.

**One limitation of what we did.** The student learns only the teacher's single
greedy answer, mistakes included. Our teacher scores 46% full-frame accuracy on
`validation.jsonl` (`results/teacher_validation.json`). Its wrong slots and
intents that still passed `clean.py` (for example a slot copied from the command
but put under the wrong key, or a wrong intent) are learned as if they were
correct, and nothing tells the student how confident the teacher was. So the
student's accuracy is in practice capped by the teacher's: it copies the
teacher's errors and adds its own. A second limitation: the training set is small
(1,500 records), and the cleaning step removed every reply with a slot the teacher
paraphrased (278 records under rule (d)), so rarer phrasings are under-represented.
