# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CQKD_DHT is a Covert Quantum Key Distribution system implemented using a Distributed Hash Table (DHT) network. The project implements a decentralized quantum key generation protocol where multiple nodes collaborate to generate cryptographic keys.

### Core Architecture

The system follows a multi-tier architecture:

- **DHT Network Layer**: Kademlia-based DHT for node discovery and communication (core/dht_node.py)
- **Protocol Layer**: Implements the 19-step quantum key generation algorithm (protocol/alice.py, protocol/bob.py)
- **Quantum Processing Layer**: Simulated quantum operations (quantum/qsg.py, quantum/bg.py, quantum/qpp.py, quantum/qpm.py, quantum/qpc.py)
- **Node Management**: Role-based node allocation and orchestration (protocol/key_generation.py)
- **Discovery System**: Smart node discovery with caching and random walk strategies (discovery/)

### Node Types

The system supports different node types with specific roles:
- **Alice**: Initiates key generation, coordinates the protocol
- **Bob**: Receives key generation notifications from Alice
- **Bootstrap Nodes**: Provide network entry points
- **Worker Nodes**: Perform quantum operations (QSG, BG, QPP, QPM, QPC roles)

### Key Components

- **CQKDNode**: Core DHT node implementation with role management
- **KeyGenerationOrchestrator**: Manages the 19-step key generation protocol
- **SmartDiscoveryStrategy**: Efficient node discovery in large DHT networks

## Development Commands

### Docker Deployment

```bash
# Build and start the complete network with 10 worker nodes
docker-compose up --build --scale worker=10

# Build and start with custom worker count
docker-compose up --build --scale worker=20

# Stop all services
docker-compose down

# View logs for specific service
docker-compose logs -f alice
docker-compose logs -f worker
```

### API Endpoints

Once running, the system exposes HTTP APIs:

**Alice (Port 8001):**
```bash
# Generate a cryptographic key
curl -X POST http://localhost:8001/generate-key \
  -H "Content-Type: application/json" \
  -d '{"desired_key_length": 1}'

# Check network status
curl -s http://localhost:8001/network-status
```

**Bob (Port 8002):**
```bash
# Check Bob's status and received keys
curl -s http://localhost:8002/status
```

### Python Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run specific node types
python -m scripts.bootstrap_node      # Bootstrap node
python -m scripts.worker_node         # Worker node
python -m scripts.bob_node           # Bob node
python -m protocol.alice             # Alice with FastAPI server

# Run tests
pytest

# Code formatting and linting
black .
flake8 .
mypy .
isort .
```

### Environment Configuration

Key environment variables (see config.py for complete list):

```bash
# DHT Configuration
DHT_PORT=6000                          # Node's DHT port
BOOTSTRAP_NODES=host1:5678,host2:5679  # Bootstrap node addresses
NODE_ID=alice                          # Optional node identifier

# Protocol Configuration
KEY_LENGTH_MULTIPLIER=2.5              # lk = multiplier * lc
REQUIRED_NODES_MULTIPLIER=5            # 5lk nodes required
MAX_CONCURRENT_ROLES=5                  # Max concurrent quantum roles

# Performance Tuning
DHT_KSIZE=25                           # Kademlia bucket size
BOOTSTRAP_TIMEOUT_SECONDS=30           # Bootstrap timeout
MAX_CONCURRENT_DISCOVERY=50            # Max parallel discovery operations
DISCOVERY_BATCH_SIZE=10                # Discovery batch size
MAX_DISCOVERY_TIME=60                  # Max discovery time in seconds
```

## Testing

The system includes comprehensive testing for quantum operations, DHT functionality, and protocol validation:

```bash
# Run all tests
pytest

# Run specific test categories
pytest test/test_quantum_operations.py
pytest test/test_dht_functionality.py
pytest test/test_protocol_validation.py

# Run with coverage
pytest --cov=.

# Run performance tests
pytest test/test_performance.py -v
```

## Protocol Implementation Details

The 19-step quantum key generation protocol is implemented in protocol/alice.py:

1. **Steps 1-3**: Calculate required parameters and discover available nodes
2. **Steps 4-6**: Allocate quantum processing roles (QSG, BG, QPP, QPM, QPC)
3. **Steps 7-8**: Process initialization and command dispatch
4. **Steps 9-11**: Result collection and Bob notification
5. **Steps 12-17**: Parallel quantum operations and measurements
6. **Steps 18-19**: QPC sifting and final key extraction

## Network Architecture

The DHT network uses Kademlia for distributed node management with optimizations for large-scale deployments:

- **Bucket Management**: Configurable k-size for load balancing
- **Discovery Strategy**: Smart caching with random walk exploration
- **Bootstrap Process**: Multi-stage bootstrap with health checks
- **Node Roles**: Dynamic role assignment with timeout management

## Performance Considerations

For large-scale deployments (1000+ nodes):

1. **Adjust DHT parameters**: Increase `dht_ksize` and `max_concurrent_discovery`
2. **Optimize timeouts**: Set appropriate `bootstrap_timeout_seconds` and `max_discovery_time`
3. **Resource management**: Monitor memory usage per worker node (256M limit in docker-compose.yml)
4. **Network health**: Monitor routing table distribution and bucket load balancing

## Security Notes

This is a research implementation for studying distributed quantum key generation protocols. The quantum operations are simulated for protocol validation purposes. For production use, replace quantum simulations with actual quantum hardware interfaces.