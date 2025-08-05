FROM python:3.10.0

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && apt-get update
COPY . .
CMD ["python", "main.py"]