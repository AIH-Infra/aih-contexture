FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir pymupdf==1.27.2.3
COPY cluster.py cluster_gateway.py cluster_admin.py cluster_production.py /app/aih_contexture/scripts/
COPY cluster_ui/ /app/aih_contexture/scripts/cluster_ui/
CMD ["python", "-m", "aih_contexture.scripts.cluster", "gateway", "/app/config.json"]
