FROM python:3.13-slim

WORKDIR /app

# Системные зависимости для psycopg2
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Зависимости Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код приложения
COPY app.py .
COPY templates/ ./templates/
COPY static/ ./static/

# Запуск через Gunicorn (можно переопределить в docker-compose)
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
