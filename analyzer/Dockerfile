FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY analyzer.py signals.py ./

EXPOSE 9110
CMD ["python", "analyzer.py"]
