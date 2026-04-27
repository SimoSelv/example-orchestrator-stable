#!/bin/bash

# Controlla se Docker è attivo, altrimenti avvia Docker Desktop
if ! docker info &> /dev/null; then
  echo "🐳 Docker non è attivo. Avvio Docker Desktop..."
  nohup /opt/docker-desktop/bin/docker-desktop &> /dev/null &

  echo "⏳ Attendo che Docker sia pronto..."
  timeout=60
  elapsed=0
  while ! docker info &> /dev/null; do
    sleep 2
    elapsed=$((elapsed + 2))
    if [ "$elapsed" -ge "$timeout" ]; then
      echo "❌ Timeout: Docker non si è avviato entro ${timeout} secondi."
      exit 1
    fi
  done
  echo "✅ Docker è pronto!"
else
  echo "✅ Docker è già attivo."
fi

echo "🧹 Pulizia stato precedente..."
docker compose down 2>/dev/null || true
docker network prune -f 2>/dev/null || true

echo "🚀 Avvio dei container con docker compose..."
docker compose up -d

echo "⏳ Attendo che i servizi siano pronti..."
sleep 5

echo "🌐 Apertura di Google Chrome..."
google-chrome --new-window \
  http://localhost:3000 \
  http://localhost:8000 \
  http://localhost:4000 &

echo "✅ Fatto! I servizi sono in avvio e Chrome è stato aperto."
