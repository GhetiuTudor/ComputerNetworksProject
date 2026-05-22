FROM python:3.11-slim

# fara dep externe 
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# se copiaza toata applicatia in imagine
COPY . /app

# start default 
CMD ["python", "server/server.py"]
