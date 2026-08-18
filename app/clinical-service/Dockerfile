FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py fhir_mapping.py ./

# FHIR_BASE is overridden in Kubernetes to point at the in-cluster HAPI service.
ENV FHIR_BASE=http://localhost:8080/fhir

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
