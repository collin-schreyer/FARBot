FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        cron \
        tesseract-ocr \
        tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies — install CPU-only torch first to keep image small
COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Copy all source
COPY *.py ./

# Copy data (508 standards, pre-built FAISS index, and legacy sklearn model)
COPY data/ data/

# Create output directory
RUN mkdir -p /app/output /app/attachments

COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Cloud Foundry injects PORT at runtime
EXPOSE 8080

CMD ["/app/entrypoint.sh"]
