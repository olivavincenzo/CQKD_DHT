"""
Bootstrap Manager - Gestione avanzata dei bootstrap nodes con load balancing e scaling
"""

import asyncio
import os
import random
import time
from typing import List, Tuple, Dict, Optional, Set
from dataclasses import dataclass
from utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class BootstrapNode:
    """Rappresenta un nodo bootstrap con metadati"""
    host: str
    port: int
    name: str
    priority: int = 1  # 1=highest, higher=lower priority
    load_score: float = 0.0  # 0.0-1.0, higher=more loaded
    last_health_check: float = 0.0
    is_healthy: bool = True
    connection_count: int = 0
    failure_count: int = 0


class BootstrapManager:
    """
    Gestore avanzato dei bootstrap nodes con:
    - Load balancing intelligente
    - Health checking
    - Fallback automatico
    - Scaling basato su numero worker
    """
    
    # Configurazione scaling basata su requisiti
    SCALING_CONFIG = {
        "small": {      # ≤15 worker
            "max_nodes": 2,
            "nodes": ["bootstrap-primary:5678", "bootstrap-secondary:5679"]
        },
        "medium": {     # 16-50 worker
            "max_nodes": 3,
            "nodes": ["bootstrap-primary:5678", "bootstrap-secondary:5679", "bootstrap-tertiary:5680"]
        },
        "large": {      # 51-200 worker
            "max_nodes": 4,
            "nodes": ["bootstrap-primary:5678", "bootstrap-secondary:5679", "bootstrap-tertiary:5680", "bootstrap-quaternary:5681"]
        },
        "xlarge": {     # >200 worker
            "max_nodes": 6,
            "nodes": ["bootstrap-primary:5678", "bootstrap-secondary:5679", "bootstrap-tertiary:5680", 
                     "bootstrap-quaternary:5681", "bootstrap-quinary:5682", "bootstrap-senary:5683"]
        }
    }
    
    def __init__(self, worker_count: int = 0, strategy: str = "adaptive"):
        """
        Inizializza il bootstrap manager
        
        Args:
            worker_count: Numero totale di worker nella rete
            strategy: Strategia di selezione (small, medium, large, xlarge, adaptive)
        """
        self.worker_count = worker_count
        self.strategy = strategy
        self.bootstrap_nodes: Dict[str, BootstrapNode] = {}
        self.round_robin_index = 0
        self.last_health_check = 0
        self.health_check_interval = 30  # seconds
        
        # Inizializza i bootstrap nodes disponibili
        self._initialize_bootstrap_nodes()
    
    def _initialize_bootstrap_nodes(self):
        """Inizializza i bootstrap nodes basandosi sulla configurazione"""
        # Ottieni tutti i bootstrap nodes dalla variabile d'ambiente
        bootstrap_env = os.getenv("BOOTSTRAP_NODES", "")
        if not bootstrap_env:
            logger.warning("BOOTSTRAP_NODES environment variable not set")
            return
        
        # Parse tutti i bootstrap nodes disponibili
        all_nodes = []
        for node_str in bootstrap_env.split(','):
            node_str = node_str.strip()
            if ':' in node_str:
                host, port = node_str.split(':')
                name = host
                all_nodes.append((name, host, int(port)))
        
        # Determina la scala della rete
        scale = self._determine_scale()
        config = self.SCALING_CONFIG[scale]
        
        # Inizializza solo i bootstrap nodes per questa scala
        for node_config in config["nodes"]:
            # node_config è nel formato "bootstrap-primary:5678"
            if ':' in node_config:
                parts = node_config.split(':')
                if len(parts) == 2:
                    name, port_str = parts
                    host = name  # Il nome è anche l'host nel container Docker
                    port = int(port_str)
                else:
                    # Fallback per formati non previsti
                    continue
                
                node_key = f"{host}:{port}"
                
                # Assegna priorità basata sulla posizione nella lista
                priority = list(config["nodes"]).index(node_config) + 1
                
                self.bootstrap_nodes[node_key] = BootstrapNode(
                    host=host,
                    port=port,
                    name=name,
                    priority=priority
                )
        
        logger.info(f"Bootstrap manager initialized for scale '{scale}' with {len(self.bootstrap_nodes)} nodes")
    
    def _determine_scale(self) -> str:
        """Determina la scala della rete basata su worker count e strategy"""
        if self.strategy != "adaptive":
            return self.strategy
        
        # Strategia adattiva basata su numero worker
        if self.worker_count <= 15:
            return "small"
        elif self.worker_count <= 50:
            return "medium"
        elif self.worker_count <= 200:
            return "large"
        else:
            return "xlarge"
    
    def get_bootstrap_nodes(self, count: int = None, strategy: str = "round_robin") -> List[Tuple[str, int]]:
        """
        Ottieni bootstrap nodes basandosi sulla strategia specificata
        
        Args:
            count: Numero di bootstrap nodes da restituire (default: tutti disponibili)
            strategy: Strategia di selezione (round_robin, least_loaded, priority, random)
        
        Returns:
            Lista di tuple (host, port) dei bootstrap nodes selezionati
        """
        if not self.bootstrap_nodes:
            logger.warning("No bootstrap nodes available")
            return []
        
        # Filtra solo i nodi sani
        healthy_nodes = [node for node in self.bootstrap_nodes.values() if node.is_healthy]
        
        if not healthy_nodes:
            logger.warning("No healthy bootstrap nodes available, using all nodes")
            healthy_nodes = list(self.bootstrap_nodes.values())
        
        # Se count non specificato, usa tutti i nodi sani
        if count is None:
            count = len(healthy_nodes)
        
        # Applica la strategia di selezione
        if strategy == "round_robin":
            selected = self._select_round_robin(healthy_nodes, count)
        elif strategy == "least_loaded":
            selected = self._select_least_loaded(healthy_nodes, count)
        elif strategy == "priority":
            selected = self._select_by_priority(healthy_nodes, count)
        elif strategy == "random":
            selected = self._select_random(healthy_nodes, count)
        else:
            logger.warning(f"Unknown strategy '{strategy}', using round_robin")
            selected = self._select_round_robin(healthy_nodes, count)
        
        # Converti in formato (host, port)
        result = [(node.host, node.port) for node in selected]
        
        logger.debug(f"Selected {len(result)} bootstrap nodes using strategy '{strategy}': {result}")
        return result
    
    def _select_round_robin(self, nodes: List[BootstrapNode], count: int) -> List[BootstrapNode]:
        """Selezione round-robin dei bootstrap nodes"""
        selected = []
        
        for i in range(count):
            node = nodes[self.round_robin_index % len(nodes)]
            selected.append(node)
            self.round_robin_index += 1
        
        return selected
    
    def _select_least_loaded(self, nodes: List[BootstrapNode], count: int) -> List[BootstrapNode]:
        """Selezione dei bootstrap nodes con meno carico"""
        # Ordina per load score (ascending) e connection count (ascending)
        sorted_nodes = sorted(nodes, key=lambda n: (n.load_score, n.connection_count))
        return sorted_nodes[:count]
    
    def _select_by_priority(self, nodes: List[BootstrapNode], count: int) -> List[BootstrapNode]:
        """Selezione per priorità (lower priority number = higher priority)"""
        sorted_nodes = sorted(nodes, key=lambda n: n.priority)
        return sorted_nodes[:count]
    
    def _select_random(self, nodes: List[BootstrapNode], count: int) -> List[BootstrapNode]:
        """Selezione casuale dei bootstrap nodes"""
        return random.sample(nodes, min(count, len(nodes)))
    
    def update_node_load(self, host: str, port: int, load_score: float = None, connection_count: int = None):
        """
        Aggiorna le metriche di carico di un bootstrap node
        
        Args:
            host: Host del bootstrap node
            port: Porta del bootstrap node
            load_score: Score di carico (0.0-1.0, optional)
            connection_count: Numero di connessioni attive (optional)
        """
        node_key = f"{host}:{port}"
        if node_key in self.bootstrap_nodes:
            node = self.bootstrap_nodes[node_key]
            if load_score is not None:
                node.load_score = max(0.0, min(1.0, load_score))
            if connection_count is not None:
                node.connection_count = max(0, connection_count)
            
            logger.debug(f"Updated load for {node_key}: load_score={node.load_score}, connections={node.connection_count}")
    
    def report_connection_success(self, host: str, port: int):
        """Report di connessione riuscita a un bootstrap node"""
        node_key = f"{host}:{port}"
        if node_key in self.bootstrap_nodes:
            node = self.bootstrap_nodes[node_key]
            node.connection_count += 1
            node.failure_count = 0
            node.is_healthy = True
            node.last_health_check = time.time()
    
    def report_connection_failure(self, host: str, port: int):
        """Report di connessione fallita a un bootstrap node"""
        node_key = f"{host}:{port}"
        if node_key in self.bootstrap_nodes:
            node = self.bootstrap_nodes[node_key]
            node.failure_count += 1
            
            # Marchia come non sano dopo 3 fallimenti
            if node.failure_count >= 3:
                node.is_healthy = False
                logger.warning(f"Bootstrap node {node_key} marked as unhealthy after {node.failure_count} failures")
    
    def get_healthy_nodes_count(self) -> int:
        """Restituisce il numero di bootstrap nodes sani"""
        return sum(1 for node in self.bootstrap_nodes.values() if node.is_healthy)
    
    def get_bootstrap_info(self) -> Dict:
        """Restituisce informazioni dettagliate sui bootstrap nodes"""
        return {
            "strategy": self.strategy,
            "worker_count": self.worker_count,
            "scale": self._determine_scale(),
            "total_nodes": len(self.bootstrap_nodes),
            "healthy_nodes": self.get_healthy_nodes_count(),
            "nodes": {
                key: {
                    "name": node.name,
                    "priority": node.priority,
                    "load_score": node.load_score,
                    "connection_count": node.connection_count,
                    "is_healthy": node.is_healthy,
                    "failure_count": node.failure_count,
                    "last_health_check": node.last_health_check
                }
                for key, node in self.bootstrap_nodes.items()
            }
        }
    
    async def health_check_loop(self):
        """Loop periodico di health check dei bootstrap nodes"""
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)
                await self._perform_health_checks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")
    
    async def _perform_health_checks(self):
        """Esegue health check su tutti i bootstrap nodes"""
        # Implementazione semplificata - in produzione usare ping/health check reali
        current_time = time.time()
        
        for node_key, node in self.bootstrap_nodes.items():
            # Simula health check basato su failure count
            if node.failure_count >= 3:
                node.is_healthy = False
            elif node.failure_count == 0 and current_time - node.last_health_check > 60:
                # Resetta lo stato healthy se non ci sono stati fallimenti recenti
                node.is_healthy = True
            
            node.last_health_check = current_time
        
        logger.debug(f"Health check completed: {self.get_healthy_nodes_count()}/{len(self.bootstrap_nodes)} nodes healthy")


# Istanza globale del bootstrap manager
_bootstrap_manager: Optional[BootstrapManager] = None


def get_bootstrap_manager(worker_count: int = 0, strategy: str = "adaptive") -> BootstrapManager:
    """
    Ottiene l'istanza del bootstrap manager (singleton)
    
    Args:
        worker_count: Numero di worker nella rete
        strategy: Strategia di selezione bootstrap
    
    Returns:
        BootstrapManager instance
    """
    global _bootstrap_manager
    
    if _bootstrap_manager is None or _bootstrap_manager.worker_count != worker_count or _bootstrap_manager.strategy != strategy:
        _bootstrap_manager = BootstrapManager(worker_count, strategy)
    
    return _bootstrap_manager


def parse_bootstrap_nodes_from_env() -> List[Tuple[str, int]]:
    """
    Funzione utility per parsare bootstrap nodes dalla variabile d'ambiente
    Mantenuta per compatibilità con codice esistente
    """
    bootstrap_nodes_str = os.getenv("BOOTSTRAP_NODES", "")
    if not bootstrap_nodes_str:
        return []
    
    nodes = []
    for addr in bootstrap_nodes_str.split(','):
        addr = addr.strip()
        if ':' in addr:
            host, port = addr.split(':')
            nodes.append((host, int(port)))
    
    return nodes