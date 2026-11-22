# Container image for the public demo (Hugging Face Spaces, Docker SDK).
# Build:  docker build -t resume-screening .
# Run:    docker run -p 7860:7860 resume-screening   ->  http://localhost:7860
FROM python:3.14-slim

# Hugging Face Spaces runs containers as uid 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    HF_HOME=/home/user/.cache/huggingface \
    PYTHONUNBUFFERED=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    ANONYMIZED_TELEMETRY=False \
    DEMO_MODE=1
WORKDIR /home/user/app

# CPU-only torch first: the default Linux wheel pulls ~2 GB of CUDA libraries
COPY --chown=user requirements-app.txt .
RUN pip install --no-cache-dir --user torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir --user -r requirements-app.txt

COPY --chown=user . .

# Bake both models and the search index into the image so the app starts fast
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/stsb-distilroberta-base')" \
 && python vector_store.py

EXPOSE 7860
CMD ["gunicorn", "--workers", "1", "--threads", "4", "--timeout", "180", "--bind", "0.0.0.0:7860", "app:app"]
