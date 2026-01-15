FROM python:3.12-slim

WORKDIR /app


COPY backend /app/backend
COPY frontend /app/frontend


RUN pip install --no-cache-dir -r /app/backend/requirements.txt

ENV PORT=8000
EXPOSE 8000

CMD ["python", "/app/backend/server.py"]
