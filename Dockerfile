FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY id_validation.py .
COPY static ./static

ENV PORT=8080
EXPOSE 8080

CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --timeout 300 main:app
