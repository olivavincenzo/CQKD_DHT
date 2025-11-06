#!/bin/bash
set -e

# --- Docker Cleanup (Optional) ---
echo "================================================"
echo "  Docker Cleanup (Optional)"
echo "================================================"
read -t 5 -p "Do you want to perform a full Docker cleanup (removes ALL containers, images, volumes)? (y/n) [y]: " -n 1 -r
REPLY=${REPLY:-y}
echo # Move to a new line
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Running docker_cleanup.sh script..."
    if [ -f ./docker_cleanup.sh ]; then
        chmod +x ./docker_cleanup.sh
        ./docker_cleanup.sh
    else
        echo "Error: docker_cleanup.sh not found."
        exit 1
    fi
else
    echo "Cleanup skipped. Stopping and removing only previous project containers..."
    docker-compose -f docker-compose.yml -f docker-compose-workers.yml down --remove-orphans || true
fi
echo "================================================
"

# --- Dozzle Log Monitoring (Optional) ---
echo "================================================"
echo "  Log Monitoring (Optional)"
echo "================================================"
read -t 5 -p "Do you want to start Dozzle for real-time log monitoring? (y/n) [y]: " -n 1 -r
REPLY=${REPLY:-y}
echo # Move to a new line
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Starting Dozzle..."
    docker-compose -f docker-compose.dozzle.yml up -d
    echo "✓ Dozzle started. You can access it at http://localhost:9999"
else
    echo "Dozzle not started. You can view logs with: docker-compose -f docker-compose.yml -f docker-compose-workers.yml logs -f"
fi
echo "================================================
"

# Default number of workers
NUM_WORKERS=${1:-1}
BASE_PORT=7000
WORKER_MEMORY_LIMIT=${WORKER_MEMORY_LIMIT:-30M} # Default to 30MB if not set
PROJECT_NAME=$(basename "$(pwd)" | tr '[:upper:]' '[:lower:]')
WORKERS_COMPOSE_FILE="docker-compose-workers.yml"

echo "Building Docker images..."
docker-compose build --no-cache

echo "Starting bootstrap nodes, Bob, and Alice..."
docker-compose up -d --wait bootstrap-primary bootstrap-secondary bob alice

echo "Generating dynamic worker services in $WORKERS_COMPOSE_FILE..."
cat <<EOF > "$WORKERS_COMPOSE_FILE"

services:
EOF

for i in $(seq 1 $NUM_WORKERS); do
  CURRENT_PORT=$((BASE_PORT + i - 1))
  CONTAINER_NAME="${PROJECT_NAME}-worker-${i}"
  
  cat <<EOF >> "$WORKERS_COMPOSE_FILE"
  worker-${i}:
    build:
      context: .
      dockerfile: Dockerfile
    image: cqkd-dht-node:worker-${i}
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

cat <<EOF >> "$WORKERS_COMPOSE_FILE"

networks:
  cqkd-network:
    external: true
    name: ${PROJECT_NAME}_cqkd-network
EOF

echo "Starting $NUM_WORKERS worker nodes dynamically..."
docker-compose -f docker-compose.yml -f "$WORKERS_COMPOSE_FILE" up -d

echo "================================================"
echo "  Project started successfully"
echo "================================================"
echo "Total workers: $NUM_WORKERS"
echo ""

echo "To stop the project: docker-compose -f docker-compose.yml -f \"$WORKERS_COMPOSE_FILE\" down"
