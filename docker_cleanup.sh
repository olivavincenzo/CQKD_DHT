#!/bin/bash

echo "================================================"
echo "  Docker Complete Cleanup Script"
echo "================================================"

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Stopping all running containers...${NC}"
if [ -n "$(docker ps -q)" ]; then
    docker stop $(docker ps -q)
    echo -e "${GREEN}✓ All containers stopped${NC}"
else
    echo "No running containers to stop"
fi

echo -e "${YELLOW}Removing all containers...${NC}"
if [ -n "$(docker ps -a -q)" ]; then
    docker rm $(docker ps -a -q)
    echo -e "${GREEN}✓ All containers removed${NC}"
else
    echo "No containers to remove"
fi

echo -e "${YELLOW}Removing all images...${NC}"
if [ -n "$(docker images -q)" ]; then
    docker rmi -f $(docker images -q)
    echo -e "${GREEN}✓ All images removed${NC}"
else
    echo "No images to remove"
fi

echo -e "${YELLOW}Removing all volumes...${NC}"
if [ -n "$(docker volume ls -q)" ]; then
    docker volume rm $(docker volume ls -q)
    echo -e "${GREEN}✓ All volumes removed${NC}"
else
    echo "No volumes to remove"
fi

echo -e "${YELLOW}Removing all networks (except default)...${NC}"
if [ -n "$(docker network ls -q -f type=custom)" ]; then
    docker network rm $(docker network ls -q -f type=custom)
    echo -e "${GREEN}✓ All custom networks removed${NC}"
else
    echo "No custom networks to remove"
fi

echo -e "${YELLOW}Cleaning build cache...${NC}"
docker builder prune -a -f
echo -e "${GREEN}✓ Build cache cleaned${NC}"

echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  Docker cleanup completed successfully!${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
docker system df
