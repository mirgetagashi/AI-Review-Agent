# Image for scripts/sandbox-run.sh. Build: docker build -t ai-review-sandbox sandbox/
FROM python:3.12-slim

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# sandbox-run.sh runs everything as 1000:1000; the user must not be root
USER 1000:1000
WORKDIR /app
