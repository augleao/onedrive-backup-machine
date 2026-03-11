FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt /app/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl ca-certificates libssl-dev libffi-dev python3-dev && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY . /app
RUN chmod +x /app/start.sh
EXPOSE 8080
CMD ["/app/start.sh"]
