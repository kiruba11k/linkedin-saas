FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 \
    libgbm1 libasound2 libpangocairo-1.0-0 libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN pip install -r requirements.txt
RUN playwright install --with-deps

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
