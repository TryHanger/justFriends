FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /service
COPY pyproject.toml README.md ./
COPY app ./app
COPY tests ./tests
COPY contracts ./contracts
# Lexicons, RAG knowledge base, few-shot examples and normalization tables are runtime data.
COPY data ./data
COPY experiments ./experiments
COPY annotation ./annotation
COPY docs ./docs
COPY frontend/src ./frontend/src
COPY ARCHITECTURE.md Dockerfile docker-compose.yml ./
COPY .github ./.github
# Fine-tuned XLM-R profiles need PyTorch: the CPU build keeps the image ~2 GB smaller
# than the default CUDA wheels, and inference on short poems is fast enough on CPU.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu     && pip install --no-cache-dir '.[dev,nlp]'
COPY scripts ./scripts

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

