FROM python:3.10.0

RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    python3-dev \
    libsodium-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]