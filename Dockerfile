FROM python:3.11-slim

# No external dependencies — stdlib only
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Copy everything into the image
COPY . /app

# Default: start the server
CMD ["python", "server/server.py"]
