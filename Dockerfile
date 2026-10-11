FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY groupby ./groupby
COPY tests ./tests

RUN useradd --create-home --uid 1000 app
USER app
ENV PYTHONUNBUFFERED=1
