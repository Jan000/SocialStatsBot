FROM python:3.11-slim

WORKDIR /app

# Install git + SSH client for self-update support (/admin update)
RUN apt-get update \
    && apt-get install -y --no-install-recommends git openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create data directory
RUN mkdir -p /app/data

# Use entrypoint wrapper for /admin update support
RUN chmod +x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]
