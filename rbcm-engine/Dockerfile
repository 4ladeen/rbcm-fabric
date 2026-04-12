FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY reputation_engine.py .
CMD ["python", "reputation_engine.py"]
