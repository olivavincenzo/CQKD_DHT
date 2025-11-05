#!/bin/bash
set -e

# Number of new workers to add
NUM_NEW_WORKERS=${1:?Please provide the number of new workers to add.}
BASE_PORT=7000
WORKER_MEMORY_LIMIT=${WORKER_MEMORY_LIMIT:-30M}
PROJECT_NAME=$(basename "$(pwd)" | tr '[:upper:]' '[:lower:]')
WORKERS_COMPOSE_FILE="docker-compose-workers.yml"

if [ ! -f "$WORKERS_COMPOSE_FILE" ]; then
  echo "Error: Workers compose file '$WORKERS_COMPOSE_FILE' not found."
  echo "Please run ./start_project.sh first to start the initial set of workers."
  exit 1
fi

echo "Detecting existing workers..."

# Find the highest existing worker number
# This looks for worker-N and gets the highest N
LAST_WORKER_NUM=$(grep -o 'worker-[0-9]*' "$WORKERS_COMPOSE_FILE" | grep -o '[0-9]*' | sort -rn | head -1)

if [ -z "$LAST_WORKER_NUM" ]; then
  LAST_WORKER_NUM=0
fi

echo "Currently there are $LAST_WORKER_NUM workers."
echo "Adding $NUM_NEW_WORKERS new workers..."

# Remove the networks section temporarily, we will add it back at the end
sed -i.bak '/^networks:/,$d' "$WORKERS_COMPOSE_FILE"

# Generate and append new worker services
for i in $(seq 1 $NUM_NEW_WORKERS); do
  WORKER_INDEX=$((LAST_WORKER_NUM + i))
  CURRENT_PORT=$((BASE_PORT + WORKER_INDEX - 1))
  CONTAINER_NAME="${PROJECT_NAME}-worker-${WORKER_INDEX}"
  
  cat <<EOF >> "$WORKERS_COMPOSE_FILE"
  worker-${WORKER_INDEX}:
    image: cqkd-dht-node:latest
    container_name: ${CONTAINER_NAME}
    environment:
      - DHT_PORT=${CURRENT_PORT}
      - BOOTSTRAP_NODES=bootstrap-primary:5678,bootstrap-secondary:5679
    ports:
      - "${CURRENT_PORT}:${CURRENT_PORT}/udp"
    depends_on:
      bootstrap-primary:
        condition: service_healthy
      bootstrap-secondary:
        condition: service_healthy
    networks:
      - cqkd-network
    command: ["python", "-m", "scripts.worker_node"]
    healthcheck:
      test: ["CMD-SHELL", "python3 -c \"import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind(('0.0.0.0', ${CURRENT_PORT})); s.close()\""]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    deploy:
      resources:
        limits:
          memory: ${WORKER_MEMORY_LIMIT}
        reservations:
          memory: ${WORKER_MEMORY_LIMIT}
EOF
done

# Add the networks section back to the generated file
cat <<EOF >> "$WORKERS_COMPOSE_FILE"

networks:
  cqkd-network:
    external: true
    name: ${PROJECT_NAME}_cqkd-network
EOF

rm "${WORKERS_COMPOSE_FILE}.bak"

echo "Starting $NUM_NEW_WORKERS new worker nodes..."
# Use both compose files to bring up the new workers
docker-compose -f docker-compose.yml -f "$WORKERS_COMPOSE_FILE" up -d

TOTAL_WORKERS=$((LAST_WORKER_NUM + NUM_NEW_WORKERS))
echo "Successfully added $NUM_NEW_WORKERS workers. Total workers: $TOTAL_WORKERS."
echo "To stop the project: docker-compose -f docker-compose.yml -f \"$WORKERS_COMPOSE_FILE\" down"
