FROM python:3.11.10-slim
WORKDIR /app
COPY worker/requirements.txt .
RUN pip install --no-cache-dir --default-timeout=300 --retries 10 -r requirements.txt
COPY worker/worker.py worker/clean.py worker/s3_init.py ./
COPY data/schema.json data/commands_pool.jsonl /data/
CMD ["python", "worker.py"]
