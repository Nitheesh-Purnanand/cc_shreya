# CS3081 mini project. From a fresh clone:  make up   (creates .env with random keys if missing)
SHELL := /bin/bash
CLUSTER   ?= cs3081
HTTP_PORT ?= 8080
S3_PORT   ?= 8333
SUBSET    ?= 0
VERSION   ?= v1
K   := kubectl --context k3d-$(CLUSTER)
PY  := .venv/bin/python
ENV := set -a; source ./.env; set +a
S3_LOCAL := S3_ENDPOINT=http://localhost:$(S3_PORT)

.PHONY: up down cluster secrets storage images seed app label clean-data train train-v2 upload-model \
        eval teacher-eval lint test loadtest release

up: cluster secrets storage images seed app

down:
	k3d cluster delete $(CLUSTER)

.env:
	printf 'S3_ACCESS_KEY=%s\nS3_SECRET_KEY=%s\n' "$$(openssl rand -hex 10)" "$$(openssl rand -hex 20)" > .env
	chmod 600 .env

$(PY):
	python3 -m venv .venv
	$(PY) -m pip install -q -r requirements-dev.txt

cluster:
	@k3d cluster list $(CLUSTER) >/dev/null 2>&1 || { \
	  sed -e 's/8080:80/$(HTTP_PORT):80/' -e 's/8333:30333/$(S3_PORT):30333/' cluster/k3d.yaml > .k3d.generated.yaml; \
	  k3d cluster create --config .k3d.generated.yaml --kubeconfig-switch-context=false; rm -f .k3d.generated.yaml; }

secrets: .env
	@$(ENV); for ns in data pipeline app; do $(K) create ns $$ns --dry-run=client -o yaml | $(K) apply -f - >/dev/null; done; \
	$(K) -n data create secret generic seaweedfs-s3 --dry-run=client -o yaml \
	  --from-literal=s3.json="{\"identities\":[{\"name\":\"admin\",\"credentials\":[{\"accessKey\":\"$$S3_ACCESS_KEY\",\"secretKey\":\"$$S3_SECRET_KEY\"}],\"actions\":[\"Admin\",\"Read\",\"Write\",\"List\",\"Tagging\"]}]}" | $(K) apply -f -; \
	for ns in pipeline app; do $(K) -n $$ns create secret generic s3-credentials --dry-run=client -o yaml \
	  --from-literal=S3_ACCESS_KEY="$$S3_ACCESS_KEY" --from-literal=S3_SECRET_KEY="$$S3_SECRET_KEY" | $(K) apply -f -; done

storage:
	$(K) apply -f k8s/data/seaweedfs.yaml
	$(K) -n data rollout status deploy/seaweedfs --timeout=600s

images:
	docker build -q -t cs3081-worker:v1 -f worker/Dockerfile .
	docker build -q -t cs3081-parser:v1 -f service/Dockerfile .
	k3d image import -c $(CLUSTER) cs3081-worker:v1 cs3081-parser:v1

seed:
	$(K) -n pipeline delete pod s3-init --ignore-not-found
	$(K) -n pipeline run s3-init --image=cs3081-worker:v1 --restart=Never \
	  --overrides='{"spec":{"containers":[{"name":"s3-init","image":"cs3081-worker:v1","imagePullPolicy":"IfNotPresent","command":["python","s3_init.py"],"env":[{"name":"S3_ENDPOINT","value":"http://seaweedfs.data.svc.cluster.local:8333"}],"envFrom":[{"secretRef":{"name":"s3-credentials"}}]}]}}'
	$(K) -n pipeline wait --for=jsonpath='{.status.phase}'=Succeeded pod/s3-init --timeout=600s
	$(K) -n pipeline logs s3-init

app:
	$(K) apply -f k8s/app/parser.yaml
	$(K) -n app rollout status deploy/parser --timeout=600s

# Task 1: teacher labelling with two parallel Jobs, then cleaning
label:
	$(K) -n pipeline create configmap teacher-prompt --from-file=teacher_prompt.txt=prompts/teacher_prompt.txt --dry-run=client -o yaml | $(K) apply -f -
	$(K) -n pipeline delete job teacher-shard-0 teacher-shard-1 --ignore-not-found
	$(K) apply -f k8s/pipeline/jobs.yaml
	$(K) -n pipeline wait --for=condition=complete job/teacher-shard-0 job/teacher-shard-1 --timeout=6h

clean-data: | $(PY)
	$(ENV); $(S3_LOCAL) $(PY) worker/clean.py --out data/v1

# Task 2
train: | $(PY)
	$(PY) training/train.py training/config.yaml --subset $(SUBSET)

train-v2: | $(PY)
	$(PY) training/train.py training/config_v2.yaml

upload-model: | $(PY)
	$(ENV); $(S3_LOCAL) $(PY) -c "import sys,pathlib; sys.path.insert(0,'worker'); from worker import s3_client; s=s3_client(); \
	[s.upload_file(str(p),'models','$(VERSION)/'+p.name) or print('s3://models/$(VERSION)/'+p.name) for p in sorted(pathlib.Path('training/out/$(VERSION)').iterdir())]"

eval: | $(PY)
	mkdir -p results
	$(PY) training/predict.py training/out/v1 results/student_validation_raw.jsonl
	python3 tools/score.py results/student_validation_raw.jsonl data/validation.jsonl --out results/student_validation.json
	$(PY) training/predict.py EleutherAI/pythia-70m results/base_validation_raw.jsonl
	python3 tools/score.py results/base_validation_raw.jsonl data/validation.jsonl --out results/base_validation.json

teacher-eval: | $(PY)
	mkdir -p results
	$(PY) worker/teacher_validation.py results/teacher_validation_raw.jsonl
	python3 tools/score.py results/teacher_validation_raw.jsonl data/validation.jsonl --out results/teacher_validation.json

release:
	gh release create model-$(VERSION) training/out/$(VERSION)/* --title "Student model $(VERSION)" --notes "Pythia-70M fine-tuned on phi3.5 teacher replies. SHA-256 per file in model.sha256."

lint: | $(PY)
	$(PY) -m ruff check .

test: | $(PY)
	$(PY) -m pytest -q tests

loadtest: | $(PY)
	mkdir -p results
	-.venv/bin/locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m --host http://localhost:$(HTTP_PORT) --csv results/loadtest
