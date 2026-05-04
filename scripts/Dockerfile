FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir google-genai psycopg2-binary
COPY sync-events.py .
CMD ["python3", "sync-events.py"]
