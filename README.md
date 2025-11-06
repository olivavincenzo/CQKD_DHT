curl -X POST http://localhost:8001/generate-key -H "Content-Type: application/json" -d '{"desired_key_length": 1}'

docker-compose up --build --scale worker=10

curl -s http://localhost:8001/network-status

docker compose -f docker-compose-workers.yml logs worker | grep "Bootstrap completato con successo!" | sort | uniq | wc -l

docker-compose -f docker-compose.dozzle.yml up -d
