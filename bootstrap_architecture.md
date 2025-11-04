# Architettura Bootstrap Multi-Livello per 1000+ Nodi

## Problema Corrente
Solo 2 bootstrap nodes (5678, 5679) causano bottleneck con 50+ worker, collassando completamente con 1000+ nodi.

## Soluzione Proposta: Architettura Bootstrap Gerarchica

### 1. **Architettura a 3 Livelli**

```
Livello 1: Super-Bootstrap (2-4 nodi)
├── Porte: 5678-5681
├── Ruolo: Entry point principale
└── Capacità: 250+ connessioni concorrenti

Livello 2: Regional Bootstrap (8-16 nodi)
├── Porte: 5682-5697
├── Ruolo: Distribuzione regionale
└── Capacità: 125+ connessioni concorrenti

Livello 3: Local Bootstrap (32-64 nodi)
├── Porte: 5698-5761
├── Ruolo: Bootstrap locale per worker
└── Capacità: 50+ connessioni concorrenti
```

### 2. **Topologia di Rete**

#### Configurazione Ottimale per 1000+ Worker
```
Super-Bootstrap (4 nodi)
├── sb-primary: 5678
├── sb-secondary: 5679
├── sb-tertiary: 5680
└── sb-quaternary: 5681

Regional Bootstrap (16 nodi)
├── rb-east-1: 5682 → sb-primary:5678
├── rb-east-2: 5683 → sb-primary:5678
├── rb-west-1: 5684 → sb-secondary:5679
├── rb-west-2: 5685 → sb-secondary:5679
├── rb-north-1: 5686 → sb-tertiary:5680
├── rb-north-2: 5687 → sb-tertiary:5680
├── rb-south-1: 5688 → sb-quaternary:5681
├── rb-south-2: 5689 → sb-quaternary:5681
└── ... (altri 8 nodi regionali)

Local Bootstrap (64 nodi)
├── lb-001: 5698 → rb-east-1:5682
├── lb-002: 5699 → rb-east-1:5682
├── lb-003: 5700 → rb-east-2:5683
├── lb-004: 5701 → rb-east-2:5683
└── ... (altri 60 nodi locali)

Worker Nodes (1000+ nodi)
├── worker-001: 7000 → lb-001:5698
├── worker-002: 7001 → lb-001:5698
├── worker-003: 7002 → lb-002:5699
└── ... (altri 997 worker)
```

### 3. **Algoritmo di Bootstrap Intelligente**

#### Strategia di Selezione Bootstrap
```python
class BootstrapSelector:
    """Selettore intelligente di nodi bootstrap"""
    
    def __init__(self):
        self.bootstrap_levels = {
            'super': [],      # Livello 1
            'regional': [],    # Livello 2
            'local': []        # Livello 3
        }
        self.load_balancer = BootstrapLoadBalancer()
    
    async def select_bootstrap_nodes(self, worker_count: int, region: str = None):
        """Seleziona nodi bootstrap ottimali"""
        
        # Strategia basata su carico attuale
        if worker_count <= 50:
            # Piccolo deployment: bootstrap diretti
            return await self._select_direct_bootstrap()
        
        elif worker_count <= 200:
            # Medio deployment: 2 livelli
            return await self._select_two_level_bootstrap(region)
        
        else:
            # Grande deployment: 3 livelli completi
            return await self._select_three_level_bootstrap(region)
    
    async def _select_three_level_bootstrap(self, region: str):
        """Selezione bootstrap a 3 livelli"""
        
        # 1. Seleziona super-bootstrap con carico minimo
        super_nodes = await self.load_balancer.get_least_loaded(
            self.bootstrap_levels['super'], 
            max_nodes=2
        )
        
        # 2. Seleziona regional bootstrap per la regione
        regional_nodes = await self.load_balancer.get_least_loaded(
            [n for n in self.bootstrap_levels['regional'] 
             if n.region == region or region is None],
            max_nodes=4
        )
        
        # 3. Seleziona local bootstrap disponibili
        local_nodes = await self.load_balancer.get_least_loaded(
            self.bootstrap_levels['local'],
            max_nodes=8
        )
        
        return super_nodes + regional_nodes + local_nodes
```

#### Load Balancer per Bootstrap
```python
class BootstrapLoadBalancer:
    """Load balancer per nodi bootstrap"""
    
    def __init__(self):
        self.node_stats = {}
        self.health_checker = BootstrapHealthChecker()
    
    async def get_least_loaded(self, nodes: list, max_nodes: int = 3):
        """Ottieni nodi con carico minimo"""
        
        # Filtra solo nodi sani
        healthy_nodes = []
        for node in nodes:
            if await self.health_checker.is_healthy(node):
                healthy_nodes.append(node)
        
        # Ordina per carico (connessioni attive)
        sorted_nodes = sorted(
            healthy_nodes,
            key=lambda n: self.node_stats.get(n.id, {}).get('active_connections', 0)
        )
        
        return sorted_nodes[:max_nodes]
    
    def update_load_stats(self, node_id: str, connections: int):
        """Aggiorna statistiche carico nodo"""
        if node_id not in self.node_stats:
            self.node_stats[node_id] = {}
        
        self.node_stats[node_id]['active_connections'] = connections
        self.node_stats[node_id]['last_update'] = datetime.now()
```

### 4. **Configurazione Docker Compose Multi-Livello**

#### Docker Compose per Super-Bootstrap
```yaml
version: '3.8'

services:
  sb-primary:
    build:
      context: .
      dockerfile: Dockerfile
    image: cqkd-dht-node:latest
    container_name: cqkd-sb-primary
    environment:
      - DHT_PORT=5678
      - NODE_ID=sb-primary
      - BOOTSTRAP_LEVEL=super
      - MAX_CONNECTIONS=500
    ports:
      - "5678:5678/udp"
    networks:
      - cqkd-network
    command: ["python", "-m", "scripts.super_bootstrap_node"]
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
        reservations:
          memory: 256M
          cpus: '0.25'

  sb-secondary:
    build:
      context: .
      dockerfile: Dockerfile
    image: cqkd-dht-node:latest
    container_name: cqkd-sb-secondary
    environment:
      - DHT_PORT=5679
      - NODE_ID=sb-secondary
      - BOOTSTRAP_LEVEL=super
      - BOOTSTRAP_NODES=sb-primary:5678
      - MAX_CONNECTIONS=500
    ports:
      - "5679:5679/udp"
    networks:
      - cqkd-network
    depends_on:
      sb-primary:
        condition: service_healthy
    command: ["python", "-m", "scripts.super_bootstrap_node"]
```

#### Docker Compose per Regional Bootstrap
```yaml
version: '3.8'

services:
  rb-east-1:
    image: cqkd-dht-node:latest
    container_name: cqkd-rb-east-1
    environment:
      - DHT_PORT=5682
      - NODE_ID=rb-east-1
      - BOOTSTRAP_LEVEL=regional
      - REGION=east
      - BOOTSTRAP_NODES=sb-primary:5678,sb-secondary:5679
      - MAX_CONNECTIONS=250
    ports:
      - "5682:5682/udp"
    networks:
      - cqkd-network
    command: ["python", "-m", "scripts.regional_bootstrap_node"]

  rb-east-2:
    image: cqkd-dht-node:latest
    container_name: cqkd-rb-east-2
    environment:
      - DHT_PORT=5683
      - NODE_ID=rb-east-2
      - BOOTSTRAP_LEVEL=regional
      - REGION=east
      - BOOTSTRAP_NODES=sb-primary:5678,sb-secondary:5679
      - MAX_CONNECTIONS=250
    ports:
      - "5683:5683/udp"
    networks:
      - cqkd-network
    command: ["python", "-m", "scripts.regional_bootstrap_node"]
```

### 5. **Script Bootstrap Specializzati**

#### Super Bootstrap Node
```python
# scripts/super_bootstrap_node.py
import asyncio
import os
from core.dht_node import CQKDNode
from utils.logging_config import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

class SuperBootstrapNode(CQKDNode):
    """Nodo super-bootstrap con capacità elevate"""
    
    def __init__(self, port: int, node_id: str):
        super().__init__(port, node_id)
        self.max_connections = int(os.getenv("MAX_CONNECTIONS", "500"))
        self.active_connections = 0
        self.connection_history = []
    
    async def handle_connection_request(self, remote_node):
        """Gestisce richieste di connessione con limitazione"""
        
        if self.active_connections >= self.max_connections:
            logger.warning(
                "super_bootstrap_at_capacity",
                node_id=self.node_id,
                current=self.active_connections,
                max=self.max_connections
            )
            return False
        
        # Accetta connessione
        self.active_connections += 1
        self.connection_history.append({
            'timestamp': datetime.now(),
            'node_id': remote_node.id,
            'action': 'connect'
        })
        
        logger.info(
            "super_bootstrap_connection_accepted",
            node_id=self.node_id,
            remote_node=remote_node.id[:16],
            active_connections=self.active_connections
        )
        
        return True
    
    async def release_connection(self, remote_node):
        """Rilascia connessione"""
        self.active_connections = max(0, self.active_connections - 1)
        self.connection_history.append({
            'timestamp': datetime.now(),
            'node_id': remote_node.id,
            'action': 'disconnect'
        })

async def main():
    port = int(os.getenv("DHT_PORT", 5678))
    node_id = os.getenv("NODE_ID", f"sb-{port}")
    bootstrap_nodes_str = os.getenv("BOOTSTRAP_NODES")
    
    logger.info(f"Avvio super-bootstrap '{node_id}' su porta {port}")
    
    super_node = SuperBootstrapNode(port, node_id)
    
    try:
        await super_node.start()
        
        if bootstrap_nodes_str:
            bootstrap_nodes = [(host, int(b_port)) 
                             for host, b_port in (addr.strip().split(':') 
                             for addr in bootstrap_nodes_str.split(','))]
            await super_node.bootstrap(bootstrap_nodes)
            logger.info(f"✓ Super-bootstrap '{node_id}' connesso alla rete")
        else:
            logger.info(f"✓ Super-bootstrap primario '{node_id}' attivo")
        
        # Task per monitoraggio carico
        async def monitor_load():
            while True:
                await asyncio.sleep(30)
                logger.info(
                    "super_bootstrap_load_stats",
                    node_id=node_id,
                    active_connections=super_node.active_connections,
                    max_connections=super_node.max_connections,
                    utilization=(super_node.active_connections / super_node.max_connections) * 100
                )
        
        monitor_task = asyncio.create_task(monitor_load())
        
        # Mantieni attivo
        while True:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Errore super-bootstrap '{node_id}': {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
```

#### Regional Bootstrap Node
```python
# scripts/regional_bootstrap_node.py
import asyncio
import os
from core.dht_node import CQKDNode
from utils.logging_config import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

class RegionalBootstrapNode(CQKDNode):
    """Nodo bootstrap regionale con gestione load balancing"""
    
    def __init__(self, port: int, node_id: str):
        super().__init__(port, node_id)
        self.region = os.getenv("REGION", "default")
        self.max_connections = int(os.getenv("MAX_CONNECTIONS", "250"))
        self.active_connections = 0
        self.worker_count = 0
    
    async def register_worker(self, worker_info):
        """Registra worker nella regione"""
        self.worker_count += 1
        
        logger.info(
            "regional_bootstrap_worker_registered",
            node_id=self.node_id,
            region=self.region,
            worker_id=worker_info.node_id,
            total_workers=self.worker_count
        )
        
        # Pubblica informazione worker nella DHT regionale
        await self.store_data(
            f"region:{self.region}:worker:{worker_info.node_id}",
            {
                'node_id': worker_info.node_id,
                'address': worker_info.address,
                'port': worker_info.port,
                'registered_at': datetime.now().isoformat()
            }
        )

async def main():
    port = int(os.getenv("DHT_PORT", 5682))
    node_id = os.getenv("NODE_ID", f"rb-{port}")
    region = os.getenv("REGION", "default")
    bootstrap_nodes_str = os.getenv("BOOTSTRAP_NODES")
    
    logger.info(f"Avvio regional bootstrap '{node_id}' per regione '{region}'")
    
    regional_node = RegionalBootstrapNode(port, node_id)
    
    try:
        await regional_node.start()
        
        if bootstrap_nodes_str:
            bootstrap_nodes = [(host, int(b_port)) 
                             for host, b_port in (addr.strip().split(':') 
                             for addr in bootstrap_nodes_str.split(','))]
            await regional_node.bootstrap(bootstrap_nodes)
            logger.info(f"✓ Regional bootstrap '{node_id}' connesso")
        
        # Task per statistiche regionali
        async def regional_stats():
            while True:
                await asyncio.sleep(60)
                logger.info(
                    "regional_bootstrap_stats",
                    node_id=node_id,
                    region=region,
                    active_connections=regional_node.active_connections,
                    registered_workers=regional_node.worker_count,
                    utilization=(regional_node.active_connections / regional_node.max_connections) * 100
                )
        
        stats_task = asyncio.create_task(regional_stats())
        
        while True:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Errore regional bootstrap '{node_id}': {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
```

### 6. **Sistema di Failover e Recovery**

#### Failover Automatico
```python
class BootstrapFailoverManager:
    """Gestore failover per nodi bootstrap"""
    
    def __init__(self):
        self.failed_nodes = set()
        self.backup_nodes = {}
        self.health_checker = BootstrapHealthChecker()
    
    async def handle_bootstrap_failure(self, failed_node_id: str):
        """Gestisce fallimento nodo bootstrap"""
        
        logger.warning(
            "bootstrap_node_failed",
            node_id=failed_node_id,
            action="initiating_failover"
        )
        
        self.failed_nodes.add(failed_node_id)
        
        # Promuovi backup node se disponibile
        if failed_node_id in self.backup_nodes:
            backup_node = self.backup_nodes[failed_node_id]
            await self._promote_backup_node(backup_node)
        
        # Ribilancia carico sui nodi rimanenti
        await self._rebalance_load()
    
    async def _promote_backup_node(self, backup_node):
        """Promuove nodo backup a primario"""
        
        backup_node.role = 'primary'
        backup_node.max_connections *= 2  # Aumenta capacità
        
        logger.info(
            "backup_node_promoted",
            node_id=backup_node.id,
            new_role="primary",
            new_max_connections=backup_node.max_connections
        )
```

### 7. **Monitoraggio e Metriche**

#### Dashboard Bootstrap
```python
class BootstrapMonitor:
    """Monitoraggio sistema bootstrap"""
    
    def __init__(self):
        self.metrics_collector = BootstrapMetricsCollector()
    
    async def get_bootstrap_health(self):
        """Stato salute sistema bootstrap"""
        
        stats = await self.metrics_collector.collect_all_stats()
        
        return {
            'total_bootstrap_nodes': len(stats),
            'healthy_nodes': len([s for s in stats if s['healthy']]),
            'total_connections': sum(s['active_connections'] for s in stats),
            'total_capacity': sum(s['max_connections'] for s in stats),
            'utilization_percent': self._calculate_utilization(stats),
            'regions_coverage': self._calculate_region_coverage(stats),
            'failover_events': await self._get_recent_failovers()
        }
    
    def _calculate_utilization(self, stats):
        """Calcola utilizzazione sistema"""
        total_active = sum(s['active_connections'] for s in stats)
        total_capacity = sum(s['max_connections'] for s in stats)
        
        return (total_active / total_capacity * 100) if total_capacity > 0 else 0
```

## Vantaggi dell'Architettura Multi-Livello

1. **Scalabilità**: Supporta 1000+ worker senza bottleneck
2. **Resilienza**: Failover automatico e backup nodes
3. **Performance**: Load balancing intelligente
4. **Monitoraggio**: Metriche dettagliate e dashboard
5. **Flessibilità**: Adattabile a diverse dimensioni di deployment
6. **Regionalizzazione**: Supporto per distribuzione geografica

## Implementazione Incrementale

1. **Fase 1**: Implementazione bootstrap a 2 livelli
2. **Fase 2**: Aggiunta load balancing e health check
3. **Fase 3**: Espansione a 3 livelli completi
4. **Fase 4**: Sistema failover e recovery
5. **Fase 5**: Monitoraggio avanzato e metriche