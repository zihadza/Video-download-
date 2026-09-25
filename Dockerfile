FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render-er $PORT use korun, jate automatic port assign hoy
CMD gunicorn youtube:app --bind 0.0.0.0:$PORT --timeout 120
