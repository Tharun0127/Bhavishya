FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Download any weights here. The container has no network when it forecasts.
# RUN python -c "from huggingface_hub import snapshot_download; snapshot_download('org/model', revision='<commit>')"
RUN useradd -u 1000 runner
USER runner
ENTRYPOINT ["python", "-m", "bhavishya.models.container"]
