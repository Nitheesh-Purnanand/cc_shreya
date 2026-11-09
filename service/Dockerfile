# Build from the repo root: docker build -t cs3081-parser:v1 -f service/Dockerfile .
# No model weights inside: the model is downloaded from S3 (MODEL_URI) at start-up.
FROM python:3.11.10-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HUB_OFFLINE=1
WORKDIR /app
COPY service/requirements.txt .
# requirements.txt pins every package (CPU-only torch index is set inside it)
RUN pip install --no-cache-dir --default-timeout=300 --retries 10 -r requirements.txt
COPY data/schema.json ./schema.json
COPY service/app.py service/inference.py ./
RUN useradd -r -u 10001 app && mkdir -p /tmp/model && chown app /tmp/model
USER 10001
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
