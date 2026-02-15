# MediGate AI - Cloud Run デプロイ用
FROM python:3.11-slim

WORKDIR /app

# システム依存（必要に応じて）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run は PORT 環境変数を使用
ENV STREAMLIT_SERVER_PORT=8080
EXPOSE 8080

CMD ["streamlit", "run", "app.py", "--server.port=8080", "--server.address=0.0.0.0"]
