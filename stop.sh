#!/bin/bash

echo "🛑 Inizio la procedura di spegnimento del progetto..."

echo "📉 Fermo ed elimino i container di docker compose..."
docker compose down

echo "🧹 Pulizia delle reti Docker orfane..."
docker network prune -f

echo "🐳 Spengo Docker Desktop per liberare risorse..."
systemctl --user stop docker-desktop 2>/dev/null || true

echo "✅ Fatto! Servizi arrestati e risorse liberate con successo."
