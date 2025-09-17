FROM debian:bookworm

ENV TZ=Europe/Paris

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    sqlite3 \
    nut-client \
    curl \
    tzdata \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 📦 Installer les dépendances Python
COPY ./app/requirements.txt /app/requirements.txt
RUN pip3 install --break-system-packages --no-cache-dir -r /app/requirements.txt

# 📁 Copier tout le code
COPY ./app /app

# 🔧 Rendre le script exécutable
RUN chmod +x /app/entrypoint.sh

WORKDIR /app
EXPOSE 5010
ENTRYPOINT ["/app/entrypoint.sh"]