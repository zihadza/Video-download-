FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Apnar main file ta youtube.py hole ei line ta hobe: youtube:app
# Jodi app.py hoy, tahole app:app
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "youtube:app"]
