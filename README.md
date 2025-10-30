 curl -X POST http://localhost:8001/generate-key -H "Content-Type: application/json" -d '{"desired_key_length": 16}'


docker-compose up --build --scale worker=10
