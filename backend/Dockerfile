FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements/ /app/requirements/
RUN pip install --no-cache-dir -r /app/requirements/cpu.txt

COPY . /app
RUN mkdir -p /app/data

EXPOSE 8000
CMD ["python", "run.py"]
