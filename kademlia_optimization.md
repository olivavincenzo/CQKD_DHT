# Ottimizzazione Parametri Kademlia per Reti Large-Scale

## Problema Corrente
Parametri Kademlia conservativi (`ALPHA=3`, `K=20`, `QUERY_TIMEOUT=5.0`) causano performance scadenti con 50+ worker e collasso con 1000+ nodi.

## Analisi Parametri Attuali

### Configurazione Esistente
```python
# discovery/node_discovery.py
ALPHA = 3          # Parallelism factor per query concorrenti
K = 20             # Numero di nodi più vicini da trovare
QUERY_TIMEOUT = 5.0 # Timeout per singola query RPC
MAX_RETRIES = 3    # Tentativi massimi per nodo non responsivo
```

### Limitazioni
- **ALPHA=3**: Troppo basso per reti 1000+ nodi
- **K=20**: Insufficiente per copertura ottimale
- **QUERY_TIMEOUT=5.0**: Inadeguato per latenze in reti grandi
- **MAX_RETRIES=3**: Troppo conservativo per reti dinamiche

## Soluzione: Parametri Adattivi

### 1. **Sistema di Parametri Adattivi**

#### Configurazione Dinamica basata su Dimensione Rete
```python
class AdaptiveKademliaParams:
    """Parametri Kademlia adattivi basati su dimensione rete"""
    
    def __init__(self):
        self.network_size_thresholds = {
            'small': (0, 50),      # 0-50 nodi
            'medium': (51, 200),   # 51-200 nodi
            'large': (201, 500),   # 201-500 nodi
            'xlarge': (501, 1000), # 501-1000 nodi
            'xxlarge': (1001, float('inf')) # 1000+ nodi
        }
        
        self.param_configs = {
            'small': {
                'alpha': 3,
                'k': 20,
                'query_timeout': 5.0,
                'max_retries': 3,
                'refresh_interval': 300
            },
            'medium': {
                'alpha': 4,
                'k': 25,
                'query_timeout': 8.0,
                'max_retries': 4,
                'refresh_interval': 240
            },
            'large': {
                'alpha': 5,
                'k': 30,
                'query_timeout': 12.0,
                'max_retries': 5,
                'refresh_interval': 180
            },
            'xlarge': {
                'alpha': 6,
                'k': 35,
                'query_timeout': 15.0,
                'max_retries': 6,
                'refresh_interval': 120
            },
            'xxlarge': {
                'alpha': 8,
                'k': 40,
                'query_timeout': 20.0,
                'max_retries': 8,
                'refresh_interval': 60
            }
        }
    
    def get_optimal_params(self, network_size: int) -> dict:
        """Ottieni parametri ottimali per dimensione rete"""
        
        # Determina categoria dimensione
        network_category = None
        for category, (min_size, max_size) in self.network_size_thresholds.items():
            if min_size <= network_size <= max_size:
                network_category = category
                break
        
        if not network_category:
            network_category = 'small'
        
        base_params = self.param_configs[network_category].copy()
        
        # Ottimizzazioni aggiuntive per reti molto grandi
        if network_size > 500:
            base_params.update(self._get_large_scale_optimizations(network_size))
        
        return base_params
    
    def _get_large_scale_optimizations(self, network_size: int) -> dict:
        """Ottimizzazioni per reti large-scale"""
        
        optimizations = {}
        
        # Aumenta parallelismo per reti molto grandi
        if network_size > 1000:
            optimizations['alpha'] = min(10, optimizations.get('alpha', 6) + 2)
            optimizations['concurrent_queries'] = min(20, network_size // 50)
        
        # Timeout adattivo basato su latenza stimata
        estimated_latency = self._estimate_network_latency(network_size)
        optimizations['query_timeout'] = max(15.0, estimated_latency * 3)
        
        # Retry aggressivi per reti dinamiche
        optimizations['max_retries'] = min(10, network_size // 100)
        
        return optimizations
    
    def _estimate_network_latency(self, network_size: int) -> float:
        """Stima latenza media basata su dimensione rete"""
        
        # Formula empirica: latenza ~ log2(network_size) * base_latency
        base_latency = 0.5  # 500ms base
        network_hops = math.log2(max(2, network_size))
        
        return base_latency * network_hops
```

### 2. **Ottimizzazione ALPHA (Parallelismo)**

#### ALPHA Adattivo Dinamico
```python
class AdaptiveAlphaManager:
    """Gestore ALPHA adattivo per parallelismo ottimale"""
    
    def __init__(self, initial_alpha: int = 3):
        self.current_alpha = initial_alpha
        self.performance_history = []
        self.network_load_monitor = NetworkLoadMonitor()
    
    async def calculate_optimal_alpha(self, target_nodes: int, network_size: int) -> int:
        """Calcola ALPHA ottimale basato su condizioni attuali"""
        
        # Base ALPHA per dimensione rete
        base_alpha = min(10, max(3, math.ceil(math.log2(network_size))))
        
        # Aggiusta basato su carico rete
        network_load = await self.network_load_monitor.get_current_load()
        load_factor = 1.0 - (network_load / 100.0)  # Riduci parallelismo se rete sovraccarica
        
        # Aggiusta basato su performance storiche
        performance_factor = self._calculate_performance_factor()
        
        # Calcola ALPHA finale
        optimal_alpha = int(base_alpha * load_factor * performance_factor)
        
        # Limiti di sicurezza
        optimal_alpha = max(2, min(15, optimal_alpha))
        
        logger.info(
            "alpha_calculation",
            base_alpha=base_alpha,
            network_load=network_load,
            performance_factor=performance_factor,
            optimal_alpha=optimal_alpha
        )
        
        return optimal_alpha
    
    def _calculate_performance_factor(self) -> float:
        """Calcola fattore di performance basato su storia"""
        
        if len(self.performance_history) < 5:
            return 1.0
        
        # Analizza performance recenti
        recent_performance = self.performance_history[-10:]
        avg_success_rate = sum(p['success_rate'] for p in recent_performance) / len(recent_performance)
        
        # Aumenta ALPHA se success rate alto, diminuisci se basso
        if avg_success_rate > 0.9:
            return 1.2  # Aumenta parallelismo
        elif avg_success_rate < 0.7:
            return 0.8  # Riduci parallelismo
        else:
            return 1.0
    
    async def update_performance_metrics(self, alpha: int, success_rate: float, duration: float):
        """Aggiorna metriche performance"""
        
        self.performance_history.append({
            'alpha': alpha,
            'success_rate': success_rate,
            'duration': duration,
            'timestamp': datetime.now()
        })
        
        # Mantieni solo storia recente
        if len(self.performance_history) > 50:
            self.performance_history = self.performance_history[-50:]
        
        self.current_alpha = await self.calculate_optimal_alpha(
            target_nodes=50,  # Default target
            network_size=await self._estimate_network_size()
        )
```

### 3. **Ottimizzazione K (Bucket Size)**

#### K Adattivo per Coverage Ottimale
```python
class AdaptiveKManager:
    """Gestore K adattivo per dimensione bucket ottimale"""
    
    def __init__(self, initial_k: int = 20):
        self.current_k = initial_k
        self.routing_table_analyzer = RoutingTableAnalyzer()
    
    async def calculate_optimal_k(self, network_size: int, target_reliability: float = 0.95) -> int:
        """Calcola K ottimale per reliability target"""
        
        # K base per dimensione rete
        base_k = min(50, max(20, math.ceil(network_size * 0.04)))
        
        # Analisi distribuzione nodi nella routing table
        distribution_analysis = await self.routing_table_analyzer.analyze_distribution()
        
        # Aumenta K se distribuzione non uniforme
        if not distribution_analysis['well_distributed']:
            base_k = int(base_k * 1.5)
        
        # Calcola K per reliability target
        # Formula: P(success) = 1 - (1/K)^redundancy_factor
        redundancy_factor = 3  # Target 3 nodi ridondanti per chiave
        required_k = math.ceil(1 / (1 - target_reliability ** (1/redundancy_factor)))
        
        optimal_k = max(base_k, required_k)
        
        # Limiti pratici
        optimal_k = max(20, min(60, optimal_k))
        
        logger.info(
            "k_calculation",
            base_k=base_k,
            required_k=required_k,
            distribution_score=distribution_analysis['distribution_score'],
            optimal_k=optimal_k
        )
        
        return optimal_k
    
    async def monitor_routing_table_health(self):
        """Monitora salute routing table e aggiusta K"""
        
        while True:
            try:
                # Analizza routing table
                health_metrics = await self.routing_table_analyzer.get_health_metrics()
                
                # Se troppi bucket vuoti, aumenta K
                if health_metrics['empty_bucket_ratio'] > 0.3:
                    new_k = min(self.current_k * 1.2, 60)
                    logger.info(
                        "increasing_k_due_to_empty_buckets",
                        old_k=self.current_k,
                        new_k=new_k,
                        empty_ratio=health_metrics['empty_bucket_ratio']
                    )
                    self.current_k = int(new_k)
                
                # Se routing table sovraccarica, riduci K
                elif health_metrics['overload_ratio'] > 0.8:
                    new_k = max(self.current_k * 0.9, 20)
                    logger.info(
                        "decreasing_k_due_to_overload",
                        old_k=self.current_k,
                        new_k=new_k,
                        overload_ratio=health_metrics['overload_ratio']
                    )
                    self.current_k = int(new_k)
                
                await asyncio.sleep(300)  # Check ogni 5 minuti
                
            except Exception as e:
                logger.error("k_monitoring_error", error=str(e))
                await asyncio.sleep(60)
```

### 4. **Ottimizzazione Timeout e Retry**

#### Timeout Adattivo Intelligente
```python
class AdaptiveTimeoutManager:
    """Gestore timeout adattivo basato su condizioni rete"""
    
    def __init__(self):
        self.latency_history = []
        self.network_conditions = NetworkConditionsMonitor()
        self.retry_strategies = {
            'conservative': ExponentialBackoff(base=1.0, max=10.0),
            'aggressive': ExponentialBackoff(base=0.5, max=15.0),
            'adaptive': AdaptiveBackoff()
        }
    
    async def calculate_optimal_timeout(self, operation_type: str, network_size: int) -> float:
        """Calcola timeout ottimale per tipo operazione"""
        
        # Timeout base per tipo operazione
        base_timeouts = {
            'ping': 2.0,
            'find_node': 5.0,
            'find_value': 8.0,
            'store': 10.0
        }
        
        base_timeout = base_timeouts.get(operation_type, 5.0)
        
        # Fattori di scaling
        size_factor = math.log2(max(2, network_size)) / 8.0  # Scaling logaritmico
        latency_factor = await self._get_current_latency_factor()
        load_factor = await self._get_current_load_factor()
        
        # Calcolo timeout finale
        optimal_timeout = base_timeout * size_factor * latency_factor * load_factor
        
        # Limiti di sicurezza
        optimal_timeout = max(2.0, min(30.0, optimal_timeout))
        
        logger.debug(
            "timeout_calculation",
            operation=operation_type,
            base_timeout=base_timeout,
            size_factor=size_factor,
            latency_factor=latency_factor,
            load_factor=load_factor,
            optimal_timeout=optimal_timeout
        )
        
        return optimal_timeout
    
    async def _get_current_latency_factor(self) -> float:
        """Ottieni fattore latenza attuale"""
        
        recent_latencies = await self.network_conditions.get_recent_latencies()
        
        if not recent_latencies:
            return 1.0
        
        avg_latency = sum(recent_latencies) / len(recent_latencies)
        expected_latency = 1.0  # 1 secondo baseline
        
        return max(0.5, min(3.0, avg_latency / expected_latency))
    
    async def _get_current_load_factor(self) -> float:
        """Ottieni fattore carico rete attuale"""
        
        network_load = await self.network_conditions.get_current_load()
        
        # Aumenta timeout se rete sovraccarica
        if network_load > 80:
            return 1.5
        elif network_load > 60:
            return 1.2
        elif network_load < 20:
            return 0.8
        else:
            return 1.0
    
    def get_retry_strategy(self, network_size: int, operation_criticality: str) -> str:
        """Seleziona strategia retry appropriata"""
        
        if operation_criticality == 'critical':
            return 'aggressive'
        elif network_size > 500:
            return 'adaptive'
        else:
            return 'conservative'
```

### 5. **Integrazione con NodeDiscoveryService**

#### Aggiornamento NodeDiscoveryService con Parametri Adattivi
```python
class OptimizedNodeDiscoveryService(NodeDiscoveryService):
    """Node discovery service con parametri Kademlia ottimizzati"""
    
    def __init__(self, coordinator_node: CQKDNode):
        super().__init__(coordinator_node)
        
        # Componenti ottimizzazione
        self.adaptive_params = AdaptiveKademliaParams()
        self.alpha_manager = AdaptiveAlphaManager()
        self.k_manager = AdaptiveKManager()
        self.timeout_manager = AdaptiveTimeoutManager()
        
        # Task background per ottimizzazione
        self.optimization_task = None
        
        # Metriche performance
        self.performance_metrics = PerformanceMetricsCollector()
    
    async def start_optimization(self):
        """Avvia task di ottimizzazione parametri"""
        
        self.optimization_task = asyncio.create_task(self._continuous_optimization())
        logger.info("adaptive_kademlia_optimization_started")
    
    async def discover_nodes_for_roles(
        self,
        required_count: int,
        required_capabilities: Optional[List[NodeRole]] = None
    ) -> NodeDiscoveryResult:
        """Discovery con parametri ottimizzati"""
        
        start_time = datetime.now()
        
        # Stima dimensione rete corrente
        network_size = await self._estimate_network_size()
        
        # Ottieni parametri ottimali
        optimal_params = self.adaptive_params.get_optimal_params(network_size)
        
        # Applica parametri ottimali
        self.ALPHA = await self.alpha_manager.calculate_optimal_alpha(
            target_nodes=required_count,
            network_size=network_size
        )
        self.K = await self.k_manager.calculate_optimal_k(network_size)
        self.QUERY_TIMEOUT = await self.timeout_manager.calculate_optimal_timeout(
            'find_node', network_size
        )
        self.MAX_RETRIES = optimal_params['max_retries']
        
        logger.info(
            "optimized_discovery_start",
            network_size=network_size,
            alpha=self.ALPHA,
            k=self.K,
            timeout=self.QUERY_TIMEOUT,
            max_retries=self.MAX_RETRIES
        )
        
        try:
            # Esegui discovery con parametri ottimizzati
            result = await super().discover_nodes_for_roles(required_count, required_capabilities)
            
            # Registra performance per ottimizzazione futura
            duration = (datetime.now() - start_time).total_seconds()
            success_rate = len(result.discovered_nodes) / required_count
            
            await self.performance_metrics.record_discovery_performance(
                network_size=network_size,
                alpha=self.ALPHA,
                k=self.K,
                timeout=self.QUERY_TIMEOUT,
                duration=duration,
                success_rate=success_rate
            )
            
            return result
            
        except Exception as e:
            logger.error("optimized_discovery_failed", error=str(e))
            raise
    
    async def _continuous_optimization(self):
        """Task continuo per ottimizzazione parametri"""
        
        while True:
            try:
                # Analizza performance recenti
                performance_analysis = await self.performance_metrics.analyze_recent_performance()
                
                # Aggiusta parametri basato su analysis
                if performance_analysis['needs_adjustment']:
                    await self._adjust_parameters(performance_analysis['recommendations'])
                
                await asyncio.sleep(300)  # Ottimizzazione ogni 5 minuti
                
            except Exception as e:
                logger.error("continuous_optimization_error", error=str(e))
                await asyncio.sleep(60)
    
    async def _estimate_network_size(self) -> int:
        """Stima dimensione rete corrente"""
        
        try:
            routing_info = self.coordinator.get_routing_table_info()
            total_nodes = routing_info.get("total_nodes", 0)
            
            # Aggiusta stima basata su bucket coverage
            active_buckets = routing_info.get("active_buckets", 0)
            total_buckets = routing_info.get("total_buckets", 160)  # Kademlia standard
            
            if active_buckets > 0:
                coverage_ratio = active_buckets / total_buckets
                estimated_size = int(total_nodes / coverage_ratio)
            else:
                estimated_size = total_nodes
            
            logger.debug(
                "network_size_estimation",
                routing_table_nodes=total_nodes,
                active_buckets=active_buckets,
                estimated_size=estimated_size
            )
            
            return estimated_size
            
        except Exception as e:
            logger.error("network_size_estimation_failed", error=str(e))
            return 50  # Default conservativo
```

### 6. **Configurazione Centralizzata**

#### Aggiornamento config.py con Parametri Adattivi
```python
# config.py
class Settings(BaseSettings):
    # ... configurazione esistente ...
    
    # Parametri Kademlia adattivi
    enable_adaptive_kademlia: bool = True
    kademlia_optimization_interval: int = 300  # secondi
    
    # Threshold parametri adattivi
    small_network_threshold: int = 50
    medium_network_threshold: int = 200
    large_network_threshold: int = 500
    xlarge_network_threshold: int = 1000
    
    # Parametri base per diverse dimensioni
    small_network_alpha: int = 3
    small_network_k: int = 20
    small_network_timeout: float = 5.0
    
    medium_network_alpha: int = 4
    medium_network_k: int = 25
    medium_network_timeout: float = 8.0
    
    large_network_alpha: int = 6
    large_network_k: int = 35
    large_network_timeout: float = 15.0
    
    xlarge_network_alpha: int = 8
    xlarge_network_k: int = 40
    xlarge_network_timeout: float = 20.0
    
    # Limiti sicurezza
    max_alpha: int = 15
    max_k: int = 60
    max_timeout: float = 30.0
    
    @property
    def adaptive_kademlia_config(self) -> dict:
        """Configurazione completa per Kademlia adattivo"""
        return {
            'enabled': self.enable_adaptive_kademlia,
            'optimization_interval': self.kademlia_optimization_interval,
            'thresholds': {
                'small': self.small_network_threshold,
                'medium': self.medium_network_threshold,
                'large': self.large_network_threshold,
                'xlarge': self.xlarge_network_threshold
            },
            'parameters': {
                'small': {
                    'alpha': self.small_network_alpha,
                    'k': self.small_network_k,
                    'timeout': self.small_network_timeout
                },
                'medium': {
                    'alpha': self.medium_network_alpha,
                    'k': self.medium_network_k,
                    'timeout': self.medium_network_timeout
                },
                'large': {
                    'alpha': self.large_network_alpha,
                    'k': self.large_network_k,
                    'timeout': self.large_network_timeout
                },
                'xlarge': {
                    'alpha': self.xlarge_network_alpha,
                    'k': self.xlarge_network_k,
                    'timeout': self.xlarge_network_timeout
                }
            },
            'limits': {
                'max_alpha': self.max_alpha,
                'max_k': self.max_k,
                'max_timeout': self.max_timeout
            }
        }
```

## Vantaggi dell'Ottimizzazione Kademlia

1. **Performance Adattiva**: Parametri ottimali per ogni dimensione rete
2. **Efficienza**: Riduzione timeout e retry non necessari
3. **Scalabilità**: Supporto nativo per 1000+ nodi
4. **Affidabilità**: Retry strategici e fallback intelligenti
5. **Monitoraggio**: Metriche continue per ottimizzazione
6. **Compatibilità**: Mantenuta con configurazione esistente

## Implementazione Incrementale

1. **Fase 1**: Implementazione parametri adattivi base
2. **Fase 2**: Ottimizzazione ALPHA dinamica
3. **Fase 3**: Sistema K adattivo
4. **Fase 4**: Timeout e retry intelligenti
5. **Fase 5**: Integrazione completa e monitoraggio