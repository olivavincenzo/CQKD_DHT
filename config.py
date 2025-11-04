try:
    # Pydantic v2
    from pydantic_settings import BaseSettings, SettingsConfigDict
    PYDANTIC_V2 = True
except ImportError:
    # Fallback a pydantic v1
    from pydantic import BaseSettings
    SettingsConfigDict = None
    PYDANTIC_V2 = False

from typing import List, Optional
import os


class Settings(BaseSettings):
    """Configurazione globale del sistema CQKD"""

    if PYDANTIC_V2:
        model_config = SettingsConfigDict(
            env_file='.env',
            env_file_encoding='utf-8',
            case_sensitive=False
        )
    else:
        # Pydantic v1 compatibility
        class Config:
            env_file = '.env'
            env_file_encoding = 'utf-8'
            case_sensitive = False

    # DHT Configuration
    dht_port: int = 5678
    bootstrap_nodes: str = "127.0.0.1:5678"
    node_id: Optional[str] = None

    # Node Configuration
    node_type: str = "worker"  # bootstrap, worker, alice, bob
    max_concurrent_roles: int = 5
    role_timeout_seconds: int = 300

    # Protocol Configuration
    key_length_multiplier: float = 2.5  # lk = multiplier * lc
    required_nodes_multiplier: int = 5  # 5lk nodes required

    # Security Configuration
    enable_channel_encryption: bool = True
    tls_cert_path: Optional[str] = None
    tls_key_path: Optional[str] = None

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # json or text

    # Performance
    max_retries: int = 3
    request_timeout_seconds: int = 30

    # DHT Scalability
    dht_ksize: int = 25  # Dimensione bucket Kademlia
    bootstrap_timeout_seconds: int = 30  # Timeout per bootstrap
    max_concurrent_discovery: int = 50  # Max discovery paralleli
    discovery_batch_size: int = 10  # Batch size per discovery
    max_discovery_time: int = 60  # Timeout discovery per reti grandi
    
    # Adaptive Kademlia Parameters
    enable_adaptive_kademlia: bool = True  # Abilita parametri adattivi
    
    # Scaling thresholds
    small_network_threshold: int = 15    # Soglia rete piccola
    medium_network_threshold: int = 50   # Soglia rete media
    large_network_threshold: int = 100   # Soglia rete grande
    xlarge_network_threshold: int = 500  # Soglia rete molto grande
    
    # Base parameters for small networks (current configuration)
    base_alpha: int = 3          # Parallelism factor per reti piccole
    base_k: int = 20             # Bucket size per reti piccole
    base_query_timeout: float = 5.0  # Timeout query per reti piccole
    
    # Scaling factors
    alpha_scaling_factor: float = 1.5  # Fattore di scaling per ALPHA
    k_scaling_factor: float = 1.3       # Fattore di scaling per K
    timeout_scaling_factor: float = 1.6 # Fattore di scaling per timeout
    
    # Maximum limits
    max_alpha: int = 8           # Massimo parallelismo
    max_k: int = 40              # Massimo bucket size
    max_query_timeout: float = 20.0  # Massimo timeout query
    max_discovery_timeout: int = 180  # Massimo timeout discovery (3 minuti)

    # Health Check Configuration
    enable_health_check: bool = True  # Abilita health check dei nodi
    health_check_batch_size: int = 20  # Numero di nodi per batch di health check
    health_check_concurrent_batches: int = 3  # Batch paralleli di health check
    
    # Health Check Timeouts (in seconds)
    health_check_fast_timeout: float = 1.0  # Fast check: ping base
    health_check_medium_timeout: float = 2.0  # Medium check: verifica completa
    health_check_deep_timeout: float = 5.0  # Deep check: nodi critici
    
    # Health Check Intervals (in seconds)
    health_check_fast_interval: int = 60   # Fast check ogni minuto
    health_check_medium_interval: int = 300  # Medium check ogni 5 minuti
    health_check_deep_interval: int = 900   # Deep check ogni 15 minuti
    
    # Health Check Thresholds
    health_check_failure_threshold: int = 3  # Fallimenti consecutivi prima rimozione
    health_check_min_availability_score: float = 0.3  # Score minimo per mantenere nodo
    health_check_critical_nodes_threshold: int = 50  # Soglia per considerare nodo critico
    
    # Health Check Strategy
    health_check_strategy: str = "adaptive"  # adaptive, uniform, priority
    health_check_priority_roles: List[str] = ["QSG", "BG"]  # Ruoli prioritari per health check

    # Bootstrap Nodes Configuration
    bootstrap_strategy: str = "adaptive"  # small, medium, large, xlarge, adaptive
    bootstrap_selection_strategy: str = "round_robin"  # round_robin, least_loaded, priority, random
    bootstrap_health_check_interval: int = 30  # seconds
    bootstrap_failure_threshold: int = 3  # fallimenti prima di marcare come unhealthy
    bootstrap_connection_timeout: float = 5.0  # timeout per connessione bootstrap
    
    # Bootstrap Nodes Scaling Configuration
    bootstrap_small_nodes: int = 2  # ≤15 worker
    bootstrap_medium_nodes: int = 3  # 16-50 worker
    bootstrap_large_nodes: int = 4  # 51-200 worker
    bootstrap_xlarge_nodes: int = 6  # >200 worker
    
    # Bootstrap Nodes Ports (fixed as required)
    bootstrap_ports: List[int] = [5678, 5679, 5680, 5681, 5682, 5683]
    
    # Bootstrap Load Balancing
    enable_bootstrap_load_balancing: bool = True
    bootstrap_load_balance_interval: int = 60  # seconds
    bootstrap_max_connections_per_node: int = 50  # massimo worker per bootstrap node
    
    # Bootstrap Fallback Configuration
    enable_bootstrap_fallback: bool = True
    bootstrap_fallback_retry_delay: float = 2.0  # seconds
    bootstrap_fallback_max_retries: int = 3

    # Monitoring
    enable_prometheus: bool = False
    prometheus_port: int = 9090

    @property
    def bootstrap_nodes_list(self) -> List[tuple]:
        """Parse bootstrap nodes from string"""
        nodes = []
        for node in self.bootstrap_nodes.split(','):
            node = node.strip()
            if ':' in node:
                host, port = node.split(':')
                nodes.append((host, int(port)))
        return nodes
    
    def calculate_adaptive_kademlia_params(self, network_size: int) -> dict:
        """
        Calcola parametri Kademlia adattivi basati sulla dimensione della rete
        
        Args:
            network_size: Numero di nodi nella rete
            
        Returns:
            dict: Parametri calcolati (alpha, k, query_timeout, discovery_timeout)
        """
        if not self.enable_adaptive_kademlia:
            # Restituisci parametri base se adattivo disabilitato
            return {
                'alpha': self.base_alpha,
                'k': self.base_k,
                'query_timeout': self.base_query_timeout,
                'discovery_timeout': self.max_discovery_time,
                'network_size': network_size,
                'adaptive_enabled': False
            }
        
        # Calcola parametri basati sulla dimensione della rete
        if network_size <= self.small_network_threshold:
            # Rete piccola (≤15 nodi): configurazione base
            alpha = self.base_alpha
            k = self.base_k
            query_timeout = self.base_query_timeout
            discovery_timeout = 60
        elif network_size <= self.medium_network_threshold:
            # Rete media (16-50 nodi): scaling leggero
            alpha = min(self.max_alpha, int(self.base_alpha * self.alpha_scaling_factor))
            k = min(self.max_k, int(self.base_k * self.k_scaling_factor))
            query_timeout = min(self.max_query_timeout, self.base_query_timeout * 1.6)
            discovery_timeout = 90
        elif network_size <= self.large_network_threshold:
            # Rete grande (51-100 nodi): scaling moderato
            alpha = min(self.max_alpha, int(self.base_alpha * self.alpha_scaling_factor * 2))
            k = min(self.max_k, int(self.base_k * self.k_scaling_factor * 1.5))
            query_timeout = min(self.max_query_timeout, self.base_query_timeout * 2.4)
            discovery_timeout = 120
        else:
            # Rete molto grande (>100 nodi): scaling aggressivo
            alpha = self.max_alpha
            k = self.max_k
            query_timeout = self.max_query_timeout
            discovery_timeout = self.max_discovery_timeout
        
        return {
            'alpha': alpha,
            'k': k,
            'query_timeout': query_timeout,
            'discovery_timeout': discovery_timeout,
            'network_size': network_size,
            'adaptive_enabled': True,
            'network_category': self._get_network_category(network_size)
        }
    
    def _get_network_category(self, network_size: int) -> str:
        """Determina la categoria della rete basata sulla dimensione"""
        if network_size <= self.small_network_threshold:
            return "small"
        elif network_size <= self.medium_network_threshold:
            return "medium"
        elif network_size <= self.large_network_threshold:
            return "large"
        else:
            return "xlarge"
    
    def calculate_health_check_params(self, network_size: int) -> dict:
        """
        Calcola parametri di health check adattivi basati sulla dimensione della rete
        
        Args:
            network_size: Numero di nodi nella rete
            
        Returns:
            dict: Parametri di health check calcolati
        """
        if not self.enable_health_check:
            return {
                'enabled': False,
                'fast_timeout': self.health_check_fast_timeout,
                'medium_timeout': self.health_check_medium_timeout,
                'deep_timeout': self.health_check_deep_timeout,
                'batch_size': self.health_check_batch_size,
                'concurrent_batches': self.health_check_concurrent_batches
            }
        
        # Calcola parametri adattivi basati sulla dimensione della rete
        if network_size <= self.small_network_threshold:
            # Rete piccola: health check più frequenti ma meno paralleli
            batch_size = min(self.health_check_batch_size, network_size)
            concurrent_batches = 1
            fast_interval = self.health_check_fast_interval
            medium_interval = self.health_check_medium_interval
            deep_interval = self.health_check_deep_interval
        elif network_size <= self.medium_network_threshold:
            # Rete media: bilanciamento tra frequenza e parallelismo
            batch_size = self.health_check_batch_size
            concurrent_batches = 2
            fast_interval = int(self.health_check_fast_interval * 1.5)
            medium_interval = int(self.health_check_medium_interval * 1.2)
            deep_interval = self.health_check_deep_interval
        elif network_size <= self.large_network_threshold:
            # Rete grande: più parallelo ma meno frequente
            batch_size = int(self.health_check_batch_size * 1.5)
            concurrent_batches = self.health_check_concurrent_batches
            fast_interval = int(self.health_check_fast_interval * 2)
            medium_interval = int(self.health_check_medium_interval * 1.5)
            deep_interval = int(self.health_check_deep_interval * 1.2)
        else:
            # Rete molto grande: massimo parallelismo, meno frequente
            batch_size = int(self.health_check_batch_size * 2)
            concurrent_batches = self.health_check_concurrent_batches
            fast_interval = int(self.health_check_fast_interval * 3)
            medium_interval = int(self.health_check_medium_interval * 2)
            deep_interval = int(self.health_check_deep_interval * 1.5)
        
        return {
            'enabled': True,
            'network_size': network_size,
            'network_category': self._get_network_category(network_size),
            'fast_timeout': self.health_check_fast_timeout,
            'medium_timeout': self.health_check_medium_timeout,
            'deep_timeout': self.health_check_deep_timeout,
            'fast_interval': fast_interval,
            'medium_interval': medium_interval,
            'deep_interval': deep_interval,
            'batch_size': batch_size,
            'concurrent_batches': concurrent_batches,
            'failure_threshold': self.health_check_failure_threshold,
            'min_availability_score': self.health_check_min_availability_score,
            'strategy': self.health_check_strategy,
            'priority_roles': self.health_check_priority_roles
        }
    
    def get_bootstrap_config_for_scale(self, worker_count: int) -> dict:
        """
        Calcola la configurazione bootstrap ottimale basata sul numero di worker
        
        Args:
            worker_count: Numero totale di worker nella rete
            
        Returns:
            dict: Configurazione bootstrap calcolata
        """
        # Determina la scala della rete
        if worker_count <= 15:
            scale = "small"
            max_nodes = self.bootstrap_small_nodes
        elif worker_count <= 50:
            scale = "medium"
            max_nodes = self.bootstrap_medium_nodes
        elif worker_count <= 200:
            scale = "large"
            max_nodes = self.bootstrap_large_nodes
        else:
            scale = "xlarge"
            max_nodes = self.bootstrap_xlarge_nodes
        
        # Calcola il ratio worker per bootstrap node
        ratio = worker_count / max_nodes if max_nodes > 0 else float('inf')
        
        # Determina se il ratio è accettabile
        ratio_status = "OK" if ratio <= 25 else "WARNING" if ratio <= 50 else "CRITICAL"
        
        return {
            "scale": scale,
            "worker_count": worker_count,
            "max_bootstrap_nodes": max_nodes,
            "worker_per_bootstrap_ratio": ratio,
            "ratio_status": ratio_status,
            "bootstrap_strategy": self.bootstrap_strategy,
            "selection_strategy": self.bootstrap_selection_strategy,
            "enable_load_balancing": self.enable_bootstrap_load_balancing,
            "enable_fallback": self.enable_bootstrap_fallback,
            "health_check_interval": self.bootstrap_health_check_interval,
            "failure_threshold": self.bootstrap_failure_threshold,
            "connection_timeout": self.bootstrap_connection_timeout,
            "max_connections_per_node": self.bootstrap_max_connections_per_node,
            "recommended_bootstrap_nodes": self.bootstrap_ports[:max_nodes]
        }
    
    def get_bootstrap_nodes_list_for_scale(self, worker_count: int = None) -> List[str]:
        """
        Ottieni la lista dei bootstrap nodes consigliati per la scala specificata
        
        Args:
            worker_count: Numero di worker (se None, usa strategia configurata)
            
        Returns:
            List[str]: Lista dei bootstrap nodes nel formato "host:port"
        """
        if worker_count is None:
            # Usa la strategia configurata
            if self.bootstrap_strategy == "small":
                max_nodes = self.bootstrap_small_nodes
            elif self.bootstrap_strategy == "medium":
                max_nodes = self.bootstrap_medium_nodes
            elif self.bootstrap_strategy == "large":
                max_nodes = self.bootstrap_large_nodes
            elif self.bootstrap_strategy == "xlarge":
                max_nodes = self.bootstrap_xlarge_nodes
            else:  # adaptive - usa tutti disponibili
                max_nodes = len(self.bootstrap_ports)
        else:
            # Calcola basato su worker_count
            config = self.get_bootstrap_config_for_scale(worker_count)
            max_nodes = config["max_bootstrap_nodes"]
        
        # Genera la lista dei bootstrap nodes
        bootstrap_names = ["bootstrap-primary", "bootstrap-secondary", "bootstrap-tertiary",
                          "bootstrap-quaternary", "bootstrap-quinary", "bootstrap-senary"]
        
        nodes = []
        for i in range(min(max_nodes, len(self.bootstrap_ports))):
            host = bootstrap_names[i]
            port = self.bootstrap_ports[i]
            nodes.append(f"{host}:{port}")
        
        return nodes


# Istanza globale delle settings
settings = Settings()
