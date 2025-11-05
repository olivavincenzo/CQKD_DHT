#!/bin/bash
set -e

# Default number of workers
NUM_WORKERS=${1:-1}
BASE_PORT=7000
WORKER_MEMORY_LIMIT=${WORKER_MEMORY_LIMIT:-30M} # Default to 30MB if not set
# Get the project name from the current directory name
PROJECT_NAME=$(basename "$(pwd)" | tr '[:upper:]' '[:lower:]')

WORKERS_COMPOSE_FILE="docker-compose-workers.yml"

echo "Stopping and removing previous containers..."
# Use the main compose file and the generated one for down command
docker-compose -f docker-compose.yml -f "$WORKERS_COMPOSE_FILE" down --remove-orphans || true # `|| true` to prevent error if file doesn't exist

echo "Building Docker images..."
docker-compose build

echo "Starting bootstrap nodes, Bob, and Alice..."
# Start only the non-worker services from the main docker-compose.yml
docker-compose up -d --wait bootstrap-primary bootstrap-secondary bob alice

echo "Generating dynamic worker services in $WORKERS_COMPOSE_FILE..."
# Start the YAML content for the generated file
cat <<EOF > "$WORKERS_COMPOSE_FILE"
version: '3.8'
services:
EOF

for i in $(seq 1 $NUM_WORKERS); do
  CURRENT_PORT=$((BASE_PORT + i - 1))
  # Container name will be projectname-servicename-instance_number by default for scaled services
  # But since we are defining each worker explicitly, we can set container_name
  CONTAINER_NAME="${PROJECT_NAME}-worker-${i}"
  
  cat <<EOF >> "$WORKERS_COMPOSE_FILE"
  worker-${i}:
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
    healthcheck:  # ← NUOVO: Health check UDP
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

# Add the networks section to the generated file, referencing the existing network
cat <<EOF >> "$WORKERS_COMPOSE_FILE"

networks:
  cqkd-network:
    external: true
    name: ${PROJECT_NAME}_cqkd-network # This assumes the network name is projectname_cqkd-network
EOF

echo "Starting $NUM_WORKERS worker nodes dynamically..."
# Use both compose files to bring up the dynamically generated workers
docker-compose -f docker-compose.yml -f "$WORKERS_COMPOSE_FILE" up -d

echo "Project started successfully with $NUM_WORKERS worker nodes."
echo "You can check the logs with: docker-compose logs"
echo "To stop the project: docker-compose -f docker-compose.yml -f \"$WORKERS_COMPOSE_FILE\" down"
echo "To remove the generated workers compose file: rm \"$WORKERS_COMPOSE_FILE\""
