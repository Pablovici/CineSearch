FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
EXPOSE 8080

# Use gunicorn for production (1 worker, 8 threads suits Cloud Run's single-instance model)
CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 60 app:app
