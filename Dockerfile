FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY data ./data
COPY frontend ./frontend
COPY templates ./templates
COPY pytest.ini .

ENV HOST=0.0.0.0
ENV PORT=8000
ENV LIBRARY_DIR=/app/library
ENV LIBRARY_DB=/app/library/library.db

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
