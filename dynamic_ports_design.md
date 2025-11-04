# Sistema di Porte Dinamiche per Worker Docker

## Problema Corrente
Tutti i worker Docker usano `DHT_PORT=7000` fisso, causando conflitti quando si scalano a 50+ worker.

## Soluzione Proposta: Sistema di Porte Dinamiche

### 1. **Architettura del Sistema di Porte**

#### Range di Porte Disponibili
- **Range Principale**: 7000-7999 (1000 porte per worker)
- **Range Bootstrap**: 5678-5699 (20 porte per bootstrap nodes)
- **Range Speciali**: 6000-6099 (100 porte per Alice/Bob/nodi speciali)

#### Strategia di Allocazione
```
Worker 1: 7000
Worker 2: 7001
Worker 3: 7002
...
Worker N: 7000 + (N-1)
```

### 2. **Implementazione Docker Compose**

#### Configurazione Dinamica
```yaml
services:
  worker:
    image: cqkd-dht-node:latest
    environment:
      - DHT_PORT=${DHT_PORT:-7000}  # Variabile d'ambiente
      - WORKER_ID=${WORKER_ID:-1}   # ID worker per calcolo porta
      - PORT_OFFSET=${PORT_OFFSET:-0} # Offset per batch diversi
    ports:
      - "${DHT_PORT:-7000}:${DHT_PORT:-7000}/udp"
```

#### Script di Generazione Docker Compose
```bash
#!/bin/bash
# generate_docker_compose.sh
WORKER_COUNT=$1
OUTPUT_FILE="docker-compose.generated.yml"

cat > $OUTPUT_FILE << EOF
version: '3.8'

services:
EOF

# Genera worker dinamici
for i in $(seq 1 $WORKER_COUNT); do
    PORT=$((7000 + i - 1))
    cat >> $OUTPUT_FILE << EOF
  worker-$i:
    image: cqkd-dht-node:latest
    container_name: cqkd-worker-$i
    environment:
      - DHT_PORT=$PORT
      - WORKER_ID=$i
      - BOOTSTRAP_NODES=bootstrap-primary:5678,bootstrap-secondary:5679
    ports:
      - "$PORT:$PORT/udp"
    networks:
      - cqkd-network
    depends_on:
      bootstrap-primary:
        condition: service_healthy
      bootstrap-secondary:
        condition: service_healthy
    command: ["python", "-m", "scripts.worker_node"]
    deploy:
      resources:
        limits:
          memory: 256M
        reservations:
          memory: 128M

EOF
done
```

### 3. **Modifiche ai Worker Node Scripts**

#### Aggiornamento scripts/worker_node.py
```python
import os
import socket

def get_dynamic_port():
    """Calcola porta dinamica basata su worker ID o variabile ambiente"""
    # Priorità: DHT_PORT > calcolo automatico
    if os.getenv("DHT_PORT"):
        return int(os.getenv("DHT_PORT"))
    
    # Calcolo basato su WORKER_ID
    worker_id = int(os.getenv("WORKER_ID", 1))
    base_port = int(os.getenv("BASE_PORT", 7000))
    port_offset = int(os.getenv("PORT_OFFSET", 0))
    
    return base_port + (worker_id - 1) + port_offset

def is_port_available(port):
    """Verifica se la porta è disponibile"""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.bind(('', port))
            return True
        except OSError:
            return False

async def main():
    # Calcola porta dinamica
    port = get_dynamic_port()
    
    # Verifica disponibilità porta
    if not is_port_available(port):
        logger.error(f"Port {port} non disponibile, tentativo con porta casuale...")
        # Fallback a porta casuale nel range
        import random
        port = random.randint(7000, 7999)
    
    logger.info(f"Worker avviato su porta dinamica: {port}")
    
    # Resto del codice esistente...
```

### 4. **Gestione dei Conflitti di Porta**

#### Sistema di Retry con Backoff
```python
async def get_available_port(start_port=7000, max_attempts=100):
    """Trova una porta disponibile nel range specificato"""
    for attempt in range(max_attempts):
        port = start_port + attempt
        if port > 7999:  # Superato il range massimo
            break
            
        if is_port_available(port):
            return port
            
        # Backoff esponenziale per evitare race condition
        await asyncio.sleep(0.1 * (2 ** min(attempt, 5)))
    
    # Fallback a porta casuale
    import random
    return random.randint(7000, 7999)
```

#### Registro Porte Allocate
```python
class PortRegistry:
    """Registro centralizzato per porte allocate"""
    def __init__(self):
        self.allocated_ports = set()
        self._lock = asyncio.Lock()
    
    async def allocate_port(self, preferred_port=None):
        """Alloca una porta disponibile"""
        async with self._lock:
            if preferred_port and preferred_port not in self.allocated_ports:
                if is_port_available(preferred_port):
                    self.allocated_ports.add(preferred_port)
                    return preferred_port
            
            # Cerca porta disponibile nel range
            for port in range(7000, 8000):
                if port not in self.allocated_ports and is_port_available(port):
                    self.allocated_ports.add(port)
                    return port
            
            raise RuntimeError("Nessuna porta disponibile nel range 7000-7999")
    
    async def release_port(self, port):
        """Rilascia una porta allocata"""
        async with self._lock:
            self.allocated_ports.discard(port)
```

### 5. **Integrazione con Docker Swarm/Kubernetes**

#### Docker Swarm Service
```yaml
version: '3.8'
services:
  worker:
    image: cqkd-dht-node:latest
    environment:
      - DHT_PORT={{.Task.Slot}}  # Slot number univoco
      - WORKER_ID={{.Task.Slot}}
    ports:
      - "7000-7999:7000-7999/udp"
    deploy:
      replicas: 1000
      endpoint_mode: dnsrr
```

#### Kubernetes Deployment
```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: cqkd-worker
spec:
  replicas: 1000
  serviceName: cqkd-worker
  template:
    spec:
      containers:
      - name: worker
        image: cqkd-dht-node:latest
        env:
        - name: DHT_PORT
          value: "7000"
        - name: POD_INDEX
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        ports:
        - containerPort: 7000
          protocol: UDP
```

### 6. **Compatibilità con Test Esistenti**

#### Modalità di Compatibilità
```python
# config.py
class Settings(BaseSettings):
    # Porte dinamiche
    enable_dynamic_ports: bool = True
    base_port: int = 7000
    max_port: int = 7999
    
    # Compatibilità
    legacy_port_mode: bool = False  # Disabilita porte dinamiche
    
    @property
    def worker_port_range(self):
        """Range di porte per worker"""
        if self.legacy_port_mode:
            return [self.base_port]  # Solo porta 7000
        return range(self.base_port, self.max_port + 1)
```

#### Test di Compatibilità
```python
def test_compatibility_mode():
    """Test che mantengono compatibilità con test esistenti"""
    # Modalità legacy: porta fissa 7000
    os.environ["LEGACY_PORT_MODE"] = "true"
    port = get_dynamic_port()
    assert port == 7000
    
    # Modalità dinamica: porte variabili
    os.environ["LEGACY_PORT_MODE"] = "false"
    os.environ["WORKER_ID"] = "5"
    port = get_dynamic_port()
    assert port == 7004  # 7000 + (5-1)
```

### 7. **Monitoraggio e Diagnostica**

#### Metriche di Utilizzo Porte
```python
class PortMetrics:
    """Metriche per utilizzo porte"""
    def __init__(self):
        self.port_usage = {}
        self.allocation_history = []
    
    def record_allocation(self, port, worker_id):
        """Registra allocazione porta"""
        self.port_usage[port] = {
            "worker_id": worker_id,
            "allocated_at": datetime.now(),
            "status": "active"
        }
        self.allocation_history.append({
            "port": port,
            "worker_id": worker_id,
            "action": "allocate",
            "timestamp": datetime.now()
        })
    
    def get_utilization_stats(self):
        """Statistiche utilizzo porte"""
        total_ports = 1000  # 7000-7999
        used_ports = len(self.port_usage)
        utilization = (used_ports / total_ports) * 100
        
        return {
            "total_ports": total_ports,
            "used_ports": used_ports,
            "utilization_percent": utilization,
            "available_ports": total_ports - used_ports
        }
```

### 8. **Sicurezza e Isolamento**

#### Policy di Sicurezza Porte
```python
class PortSecurityPolicy:
    """Policy di sicurezza per allocazione porte"""
    def __init__(self):
        self.allowed_ranges = [(7000, 7999)]  # Range consentiti
        self.blocked_ports = set()  # Porte bloccate
        self.max_ports_per_worker = 1  # Una porta per worker
    
    def validate_port_allocation(self, port, worker_id):
        """Valida allocazione porta"""
        # Verifica range consentito
        if not any(start <= port <= end for start, end in self.allowed_ranges):
            return False, "Porta fuori range consentito"
        
        # Verifica porta non bloccata
        if port in self.blocked_ports:
            return False, "Porta bloccata"
        
        return True, "Porta valida"
```

## Vantaggi della Soluzione

1. **Scalabilità**: Supporta 1000+ worker senza conflitti
2. **Compatibilità**: Mantenuta con test esistenti
3. **Flessibilità**: Adattabile a Docker Swarm/Kubernetes
4. **Affidabilità**: Sistema di retry e fallback
5. **Monitoraggio**: Metriche complete di utilizzo
6. **Sicurezza**: Policy di sicurezza e isolamento

## Implementazione Incrementale

1. **Fase 1**: Implementazione base con porte dinamiche
2. **Fase 2**: Sistema di retry e gestione conflitti
3. **Fase 3**: Integrazione Docker Swarm/Kubernetes
4. **Fase 4**: Monitoraggio e metriche avanzate
5. **Fase 5**: Ottimizzazioni performance e sicurezza