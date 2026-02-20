#!/bin/bash
echo "Git pull..."
git pull
echo "Baue und starte Docker Container neu..."
docker compose -f ./docker-compose.yml up -d --build
echo "Updated!"