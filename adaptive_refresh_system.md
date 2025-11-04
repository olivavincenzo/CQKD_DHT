# Sistema di Refresh Rate Adattivo per Routing Table

## Problema Corrente
Refresh rate fisso di 300 secondi (5 minuti) in discovery_strategies.py riga 315 è troppo lento per reti dinamiche con 1000+ nodi, causando routing table obsoleta e performance degradate.

## Analisi del Problema

### Codice Attuale
```python
# discovery/discovery_strategies.py riga 315
async def _periodic_refresh(self):
    """Task periodico per refresh dei nodi in cache"""
    while True:
        try:
            await asyncio.sleep(300)  # Ogni 5 minuti (come Kademlia standard)
            # ... refresh logic ...
```

### Limitazioni
- **Refresh Fisso**: 300 secondi per tutte le condizioni
- **Non Adattivo**: Non considera dimensione rete o dinamicità
- **Inefficiente**: Refresh completo anche per nodi stabili
- **Scalabilità**: Inadeguato per 1000+ nodi dinamici

## Soluzione: Sistema di Refresh Adattivo Intelligente

### 1. **Architettura Refresh Multi-Livello**

```
Livello 1: Refresh Immediato (Critical)
├── Trigger: Eventi critici (node failure, network partition)
├── Intervallo: Immediato
└── Scope: Solo bucket affetti

Livello 2: Refresh Rapido (Active)
├── Trigger: Nodi ad alta dinamicità
├── Intervallo: 30-60 secondi
└── Scope: Bucket attivi

Livello 3: Refresh Normale (Stable)
├── Trigger: Nodi stabili
├── Intervallo: 120-300 secondi
└── Scope: Tutti i bucket

Livello 4: Refresh Profondo (Maintenance)
├── Trigger: Manutenzione programmata
├── Intervallo: 600-1800 secondi
└── Scope: Routing table completa
```

### 2. **Sistema di Refresh Adattivo**

#### Refresh Manager Intelligente
```python
class AdaptiveRefreshManager:
    """Gestore refresh adattivo per routing table"""
    
    def __init__(self, coordinator_node: CQKDNode):
        self.coordinator = coordinator_node
        self.refresh_strategies = {
            'immediate': ImmediateRefreshStrategy(),
            'active': ActiveRefreshStrategy(),
            'stable': StableRefreshStrategy(),
            'maintenance': MaintenanceRefreshStrategy()
        }
        
        # Analizzatori per decisioni adattive
        self.network_dynamics_analyzer = NetworkDynamicsAnalyzer()
        self.routing_table_analyzer = RoutingTableAnalyzer()
        self.performance_predictor = RefreshPerformancePredictor()
        
        # Stato refresh
        self.refresh_history = []
        self.bucket_refresh_status = {}
        self.refresh_metrics = RefreshMetricsCollector()
        
        # Configurazione adattiva
        self.adaptive_config = AdaptiveRefreshConfig()
    
    async def start_adaptive_refresh(self):
        """Avvia sistema refresh adattivo"""
        
        logger.info("adaptive_refresh_system_started")
        
        # Avvia task per ogni strategia
        tasks = []
        
        # Refresh immediato (event-driven)
        immediate_task = asyncio.create_task(
            self._immediate_refresh_loop()
        )
        tasks.append(immediate_task)
        
        # Refresh attivo (high-frequency)
        active_task = asyncio.create_task(
            self._active_refresh_loop()
        )
        tasks.append(active_task)
        
        # Refresh stabile (normal-frequency)
        stable_task = asyncio.create_task(
            self._stable_refresh_loop()
        )
        tasks.append(stable_task)
        
        # Refresh manutenzione (low-frequency)
        maintenance_task = asyncio.create_task(
            self._maintenance_refresh_loop()
        )
        tasks.append(maintenance_task)
        
        # Ottimizzazione parametri
        optimization_task = asyncio.create_task(
            self._continuous_optimization()
        )
        tasks.append(optimization_task)
        
        return tasks
    
    async def _immediate_refresh_loop(self):
        """Refresh immediato per eventi critici"""
        
        logger.info("immediate_refresh_loop_started")
        
        while True:
            try:
                # Aspetta eventi critici
                critical_event = await self._wait_for_critical_event()
                
                if critical_event:
                    logger.warning(
                        "critical_refresh_triggered",
                        event_type=critical_event.type,
                        affected_buckets=critical_event.affected_buckets
                    )
                    
                    # Esegui refresh immediato sui bucket affetti
                    await self._execute_immediate_refresh(critical_event)
                
            except Exception as e:
                logger.error("immediate_refresh_error", error=str(e))
                await asyncio.sleep(5)  # Retry rapido
    
    async def _active_refresh_loop(self):
        """Refresh rapido per bucket ad alta dinamicità"""
        
        logger.info("active_refresh_loop_started")
        
        while True:
            try:
                # Analizza dinamicità rete
                dynamics_analysis = await self.network_dynamics_analyzer.analyze_current_dynamics()
                
                # Determina intervallo refresh adattivo
                refresh_interval = self._calculate_active_refresh_interval(dynamics_analysis)
                
                logger.debug(
                    "active_refresh_interval_calculated",
                    interval=refresh_interval,
                    network_dynamics_score=dynamics_analysis.dynamics_score
                )
                
                # Esegui refresh bucket attivi
                await self._execute_active_refresh(dynamics_analysis)
                
                await asyncio.sleep(refresh_interval)
                
            except Exception as e:
                logger.error("active_refresh_error", error=str(e))
                await asyncio.sleep(30)  # Fallback a 30 secondi
    
    async def _stable_refresh_loop(self):
        """Refresh normale per bucket stabili"""
        
        logger.info("stable_refresh_loop_started")
        
        while True:
            try:
                # Analizza stabilità routing table
                stability_analysis = await self.routing_table_analyzer.analyze_stability()
                
                # Calcola intervallo refresh stabile
                refresh_interval = self._calculate_stable_refresh_interval(stability_analysis)
                
                logger.debug(
                    "stable_refresh_interval_calculated",
                    interval=refresh_interval,
                    stability_score=stability_analysis.stability_score
                )
                
                # Esegui refresh stabile
                await self._execute_stable_refresh(stability_analysis)
                
                await asyncio.sleep(refresh_interval)
                
            except Exception as e:
                logger.error("stable_refresh_error", error=str(e))
                await asyncio.sleep(120)  # Fallback a 2 minuti
    
    async def _maintenance_refresh_loop(self):
        """Refresh profondo per manutenzione"""
        
        logger.info("maintenance_refresh_loop_started")
        
        while True:
            try:
                # Analizza necessità manutenzione
                maintenance_needed = await self._analyze_maintenance_needs()
                
                if maintenance_needed.required:
                    logger.info(
                        "maintenance_refresh_triggered",
                        reasons=maintenance_needed.reasons,
                        estimated_duration=maintenance_needed.estimated_duration
                    )
                    
                    # Esegui refresh manutenzione
                    await self._execute_maintenance_refresh(maintenance_needed)
                
                # Intervallo manutenzione base (con adattamento)
                base_interval = self.adaptive_config.get_maintenance_interval()
                await asyncio.sleep(base_interval)
                
            except Exception as e:
                logger.error("maintenance_refresh_error", error=str(e))
                await asyncio.sleep(600)  # Fallback a 10 minuti
    
    async def _continuous_optimization(self):
        """Ottimizzazione continua parametri refresh"""
        
        logger.info("continuous_refresh_optimization_started")
        
        while True:
            try:
                # Analizza performance refresh recenti
                performance_analysis = await self.refresh_metrics.analyze_recent_performance()
                
                # Ottimizza parametri basati su performance
                optimizations = await self.performance_predictor.suggest_optimizations(
                    performance_analysis
                )
                
                if optimizations.recommended_changes:
                    logger.info(
                        "refresh_optimization_recommended",
                        changes=optimizations.recommended_changes,
                        expected_improvement=optimizations.expected_improvement
                    )
                    
                    # Applica ottimizzazioni
                    await self._apply_refresh_optimizations(optimizations.recommended_changes)
                
                await asyncio.sleep(300)  # Ottimizzazione ogni 5 minuti
                
            except Exception as e:
                logger.error("refresh_optimization_error", error=str(e))
                await asyncio.sleep(60)
    
    async def _wait_for_critical_event(self) -> Optional[CriticalEvent]:
        """Aspetta eventi critici che richiedono refresh immediato"""
        
        try:
            # Monitora eventi critici
            events = []
            
            # 1. Node failure detection
            failed_nodes = await self._detect_failed_nodes()
            if failed_nodes:
                events.append(CriticalEvent(
                    type='node_failure',
                    affected_nodes=failed_nodes,
                    affected_buckets=await self._get_affected_buckets(failed_nodes),
                    priority='high'
                ))
            
            # 2. Network partition detection
            partition_detected = await self._detect_network_partition()
            if partition_detected:
                events.append(CriticalEvent(
                    type='network_partition',
                    affected_buckets=await self._get_all_active_buckets(),
                    priority='critical'
                ))
            
            # 3. Routing table corruption detection
            corruption_detected = await self._detect_routing_table_corruption()
            if corruption_detected:
                events.append(CriticalEvent(
                    type='routing_corruption',
                    affected_buckets=corruption_detected.corrupted_buckets,
                    priority='critical'
                ))
            
            # Ritorna l'evento con priorità più alta
            if events:
                return max(events, key=lambda e: e.priority)
            
            return None
            
        except Exception as e:
            logger.error("critical_event_detection_error", error=str(e))
            return None
    
    async def _execute_immediate_refresh(self, event: CriticalEvent):
        """Esegui refresh immediato per evento critico"""
        
        start_time = datetime.now()
        
        try:
            logger.info(
                "immediate_refresh_executing",
                event_type=event.type,
                affected_buckets=len(event.affected_buckets)
            )
            
            # Strategia refresh basata su tipo evento
            if event.type == 'node_failure':
                await self._refresh_failed_node_buckets(event.affected_nodes)
            elif event.type == 'network_partition':
                await self._refresh_partitioned_buckets(event.affected_buckets)
            elif event.type == 'routing_corruption':
                await self._refresh_corrupted_buckets(event.affected_buckets)
            
            duration = (datetime.now() - start_time).total_seconds()
            
            # Registra performance
            await self.refresh_metrics.record_refresh_performance(
                strategy='immediate',
                event_type=event.type,
                duration=duration,
                buckets_refreshed=len(event.affected_buckets),
                success=True
            )
            
            logger.info(
                "immediate_refresh_completed",
                event_type=event.type,
                duration=duration,
                buckets_refreshed=len(event.affected_buckets)
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            
            await self.refresh_metrics.record_refresh_performance(
                strategy='immediate',
                event_type=event.type,
                duration=duration,
                buckets_refreshed=0,
                success=False,
                error=str(e)
            )
            
            logger.error(
                "immediate_refresh_failed",
                event_type=event.type,
                error=str(e)
            )
    
    async def _execute_active_refresh(self, dynamics_analysis: NetworkDynamics):
        """Esegui refresh per bucket ad alta dinamicità"""
        
        start_time = datetime.now()
        
        try:
            # Identifica bucket ad alta dinamicità
            high_dynamics_buckets = await self._identify_high_dynamics_buckets(dynamics_analysis)
            
            if not high_dynamics_buckets:
                logger.debug("no_high_dynamics_buckets_found")
                return
            
            logger.info(
                "active_refresh_executing",
                high_dynamics_buckets=len(high_dynamics_buckets),
                dynamics_score=dynamics_analysis.dynamics_score
            )
            
            # Esegui refresh selettivo
            refreshed_buckets = []
            for bucket_info in high_dynamics_buckets:
                try:
                    await self._refresh_single_bucket(bucket_info.bucket_index, strategy='active')
                    refreshed_buckets.append(bucket_info.bucket_index)
                    
                except Exception as e:
                    logger.warning(
                        "bucket_refresh_failed",
                        bucket_index=bucket_info.bucket_index,
                        error=str(e)
                    )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            # Registra performance
            await self.refresh_metrics.record_refresh_performance(
                strategy='active',
                duration=duration,
                buckets_refreshed=len(refreshed_buckets),
                success=len(refreshed_buckets) > 0
            )
            
            logger.info(
                "active_refresh_completed",
                buckets_refreshed=len(refreshed_buckets),
                duration=duration
            )
            
        except Exception as e:
            logger.error("active_refresh_error", error=str(e))
    
    async def _execute_stable_refresh(self, stability_analysis: RoutingTableStability):
        """Esegui refresh normale per routing table stabile"""
        
        start_time = datetime.now()
        
        try:
            logger.info(
                "stable_refresh_executing",
                stability_score=stability_analysis.stability_score,
                total_buckets=stability_analysis.total_buckets
            )
            
            # Refresh completo ma ottimizzato
            refreshed_buckets = []
            
            # Strategia di refresh basata su stabilità
            if stability_analysis.stability_score > 0.8:
                # Alta stabilità: refresh selettivo
                refreshed_buckets = await self._selective_stable_refresh()
            elif stability_analysis.stability_score > 0.5:
                # Stabilità media: refresh parziale
                refreshed_buckets = await self._partial_stable_refresh()
            else:
                # Bassa stabilità: refresh completo
                refreshed_buckets = await self._full_stable_refresh()
            
            duration = (datetime.now() - start_time).total_seconds()
            
            # Registra performance
            await self.refresh_metrics.record_refresh_performance(
                strategy='stable',
                duration=duration,
                buckets_refreshed=len(refreshed_buckets),
                success=len(refreshed_buckets) > 0
            )
            
            logger.info(
                "stable_refresh_completed",
                buckets_refreshed=len(refreshed_buckets),
                duration=duration,
                strategy='selective' if stability_analysis.stability_score > 0.8 else 'partial' if stability_analysis.stability_score > 0.5 else 'full'
            )
            
        except Exception as e:
            logger.error("stable_refresh_error", error=str(e))
    
    async def _execute_maintenance_refresh(self, maintenance_needed: MaintenanceNeeds):
        """Esegui refresh profondo per manutenzione"""
        
        start_time = datetime.now()
        
        try:
            logger.info(
                "maintenance_refresh_executing",
                reasons=maintenance_needed.reasons,
                estimated_duration=maintenance_needed.estimated_duration
            )
            
            # Refresh completo con validazione
            refreshed_buckets = []
            validation_results = []
            
            for bucket_index in range(len(self.coordinator.server.protocol.router.buckets)):
                try:
                    # Refresh bucket
                    await self._refresh_single_bucket(bucket_index, strategy='maintenance')
                    refreshed_buckets.append(bucket_index)
                    
                    # Validazione post-refresh
                    validation = await self._validate_bucket_refresh(bucket_index)
                    validation_results.append(validation)
                    
                except Exception as e:
                    logger.warning(
                        "maintenance_bucket_refresh_failed",
                        bucket_index=bucket_index,
                        error=str(e)
                    )
            
            duration = (datetime.now() - start_time).total_seconds()
            success_rate = sum(1 for v in validation_results if v.success) / len(validation_results)
            
            # Registra performance
            await self.refresh_metrics.record_refresh_performance(
                strategy='maintenance',
                duration=duration,
                buckets_refreshed=len(refreshed_buckets),
                success=success_rate > 0.8,
                details={
                    'validation_success_rate': success_rate,
                    'reasons': maintenance_needed.reasons
                }
            )
            
            logger.info(
                "maintenance_refresh_completed",
                buckets_refreshed=len(refreshed_buckets),
                duration=duration,
                validation_success_rate=success_rate
            )
            
        except Exception as e:
            logger.error("maintenance_refresh_error", error=str(e))
    
    def _calculate_active_refresh_interval(self, dynamics_analysis: NetworkDynamics) -> float:
        """Calcola intervallo refresh basato su dinamicità rete"""
        
        # Base intervallo
        base_interval = 30.0  # 30 secondi minimo
        
        # Fattori di scaling
        dynamics_factor = max(0.5, min(3.0, dynamics_analysis.dynamics_score))
        load_factor = max(0.8, min(2.0, dynamics_analysis.network_load / 50.0))
        
        # Calcolo intervallo finale
        adaptive_interval = base_interval * dynamics_factor * load_factor
        
        # Limiti di sicurezza
        adaptive_interval = max(15.0, min(120.0, adaptive_interval))
        
        logger.debug(
            "active_refresh_interval_calculation",
            base_interval=base_interval,
            dynamics_factor=dynamics_factor,
            load_factor=load_factor,
            adaptive_interval=adaptive_interval
        )
        
        return adaptive_interval
    
    def _calculate_stable_refresh_interval(self, stability_analysis: RoutingTableStability) -> float:
        """Calcola intervallo refresh basato su stabilità routing table"""
        
        # Base intervallo
        base_interval = 120.0  # 2 minuti base
        
        # Fattori di scaling
        stability_factor = max(0.3, min(2.0, 2.0 - stability_analysis.stability_score))
        size_factor = max(0.8, min(1.5, stability_analysis.total_nodes / 500.0))
        
        # Calcolo intervallo finale
        adaptive_interval = base_interval * stability_factor * size_factor
        
        # Limiti di sicurezza
        adaptive_interval = max(60.0, min(600.0, adaptive_interval))
        
        logger.debug(
            "stable_refresh_interval_calculation",
            base_interval=base_interval,
            stability_factor=stability_factor,
            size_factor=size_factor,
            adaptive_interval=adaptive_interval
        )
        
        return adaptive_interval
    
    async def _refresh_single_bucket(self, bucket_index: int, strategy: str) -> bool:
        """Esegui refresh di singolo bucket"""
        
        try:
            logger.debug(
                "bucket_refresh_start",
                bucket_index=bucket_index,
                strategy=strategy
            )
            
            # Ottieni bucket dalla routing table
            router = self.coordinator.server.protocol.router
            bucket = router.buckets[bucket_index]
            
            # Esegui refresh bucket basato su strategia
            if strategy == 'immediate':
                await self._immediate_bucket_refresh(bucket)
            elif strategy == 'active':
                await self._active_bucket_refresh(bucket)
            elif strategy == 'stable':
                await self._stable_bucket_refresh(bucket)
            elif strategy == 'maintenance':
                await self._maintenance_bucket_refresh(bucket)
            else:
                await self._default_bucket_refresh(bucket)
            
            # Aggiorna stato bucket
            self.bucket_refresh_status[bucket_index] = {
                'last_refresh': datetime.now(),
                'strategy': strategy,
                'success': True
            }
            
            logger.debug(
                "bucket_refresh_complete",
                bucket_index=bucket_index,
                strategy=strategy
            )
            
            return True
            
        except Exception as e:
            logger.error(
                "bucket_refresh_failed",
                bucket_index=bucket_index,
                strategy=strategy,
                error=str(e)
            )
            
            # Aggiorna stato con fallimento
            self.bucket_refresh_status[bucket_index] = {
                'last_refresh': datetime.now(),
                'strategy': strategy,
                'success': False,
                'error': str(e)
            }
            
            return False
```

### 3. **Analizzatori di Dinamicità**

#### Network Dynamics Analyzer
```python
class NetworkDynamicsAnalyzer:
    """Analizzatore dinamicità rete per decisioni refresh"""
    
    def __init__(self):
        self.dynamics_history = []
        self.node_lifecycle_tracker = NodeLifecycleTracker()
    
    async def analyze_current_dynamics(self) -> NetworkDynamics:
        """Analizza dinamicità corrente della rete"""
        
        try:
            # Metriche dinamicità
            node_churn_rate = await self._calculate_node_churn_rate()
            bucket_change_rate = await self._calculate_bucket_change_rate()
            network_load = await self._measure_network_load()
            latency_variance = await self._measure_latency_variance()
            
            # Calcola score complessivo dinamicità
            dynamics_score = self._calculate_dynamics_score(
                node_churn_rate,
                bucket_change_rate,
                network_load,
                latency_variance
            )
            
            # Classifica livello dinamicità
            dynamics_level = self._classify_dynamics_level(dynamics_score)
            
            network_dynamics = NetworkDynamics(
                dynamics_score=dynamics_score,
                dynamics_level=dynamics_level,
                node_churn_rate=node_churn_rate,
                bucket_change_rate=bucket_change_rate,
                network_load=network_load,
                latency_variance=latency_variance,
                timestamp=datetime.now()
            )
            
            # Salva in storia
            self.dynamics_history.append(network_dynamics)
            
            # Mantieni solo storia recente
            if len(self.dynamics_history) > 100:
                self.dynamics_history = self.dynamics_history[-100:]
            
            return network_dynamics
            
        except Exception as e:
            logger.error("network_dynamics_analysis_error", error=str(e))
            return NetworkDynamics(
                dynamics_score=0.5,  # Default medio
                dynamics_level='medium',
                timestamp=datetime.now()
            )
    
    async def _calculate_node_churn_rate(self) -> float:
        """Calcola tasso di cambio nodi"""
        
        try:
            # Analizza cambiamenti nodi nell'ultima ora
            recent_changes = await self.node_lifecycle_tracker.get_recent_changes(
                timedelta(hours=1)
            )
            
            total_nodes = len(self.node_lifecycle_tracker.get_all_known_nodes())
            
            if total_nodes == 0:
                return 0.0
            
            churn_rate = len(recent_changes) / total_nodes
            
            logger.debug(
                "node_churn_rate_calculated",
                recent_changes=len(recent_changes),
                total_nodes=total_nodes,
                churn_rate=churn_rate
            )
            
            return churn_rate
            
        except Exception as e:
            logger.error("node_churn_rate_error", error=str(e))
            return 0.0
    
    async def _calculate_bucket_change_rate(self) -> float:
        """Calcola tasso di cambio bucket"""
        
        try:
            # Confronta stato attuale bucket con stato precedente
            current_bucket_state = await self._get_current_bucket_state()
            
            if not self.dynamics_history:
                return 0.0
            
            previous_bucket_state = self.dynamics_history[-1].bucket_state
            
            if not previous_bucket_state:
                return 0.0
            
            # Calcola differenze
            changes = 0
            total_buckets = len(current_bucket_state)
            
            for i, current_nodes in enumerate(current_bucket_state):
                previous_nodes = previous_bucket_state[i] if i < len(previous_bucket_state) else []
                
                # Confronta set di nodi
                current_set = set(node.id for node in current_nodes)
                previous_set = set(node.id for node in previous_nodes)
                
                changes += len(current_set.symmetric_difference(previous_set))
            
            change_rate = changes / total_buckets if total_buckets > 0 else 0.0
            
            logger.debug(
                "bucket_change_rate_calculated",
                changes=changes,
                total_buckets=total_buckets,
                change_rate=change_rate
            )
            
            return change_rate
            
        except Exception as e:
            logger.error("bucket_change_rate_error", error=str(e))
            return 0.0
    
    def _calculate_dynamics_score(
        self,
        node_churn_rate: float,
        bucket_change_rate: float,
        network_load: float,
        latency_variance: float
    ) -> float:
        """Calcola score complessivo dinamicità"""
        
        # Pesi per ogni metrica
        weights = {
            'node_churn': 0.3,
            'bucket_change': 0.3,
            'network_load': 0.2,
            'latency_variance': 0.2
        }
        
        # Normalizzazione metriche (0-1)
        normalized_churn = min(1.0, node_churn_rate * 10)  # 10% churn = 1.0
        normalized_bucket_change = min(1.0, bucket_change_rate / 5.0)  # 5 changes = 1.0
        normalized_load = min(1.0, network_load / 100.0)  # 100% load = 1.0
        normalized_latency = min(1.0, latency_variance / 2.0)  # 2s variance = 1.0
        
        # Calcolo score pesato
        dynamics_score = (
            normalized_churn * weights['node_churn'] +
            normalized_bucket_change * weights['bucket_change'] +
            normalized_load * weights['network_load'] +
            normalized_latency * weights['latency_variance']
        )
        
        logger.debug(
            "dynamics_score_calculated",
            normalized_churn=normalized_churn,
            normalized_bucket_change=normalized_bucket_change,
            normalized_load=normalized_load,
            normalized_latency=normalized_latency,
            final_score=dynamics_score
        )
        
        return dynamics_score
    
    def _classify_dynamics_level(self, dynamics_score: float) -> str:
        """Classifica livello dinamicità"""
        
        if dynamics_score < 0.2:
            return 'very_low'
        elif dynamics_score < 0.4:
            return 'low'
        elif dynamics_score < 0.6:
            return 'medium'
        elif dynamics_score < 0.8:
            return 'high'
        else:
            return 'very_high'
```

### 4. **Configurazione Adattiva**

#### Aggiornamento config.py
```python
class Settings(BaseSettings):
    # ... configurazione esistente ...
    
    # Refresh Adattivo Configuration
    enable_adaptive_refresh: bool = True
    refresh_optimization_interval: int = 300  # secondi
    
    # Refresh Intervals (secondi)
    immediate_refresh_enabled: bool = True
    active_refresh_min_interval: int = 15
    active_refresh_max_interval: int = 120
    stable_refresh_min_interval: int = 60
    stable_refresh_max_interval: int = 600
    maintenance_refresh_interval: int = 1800  # 30 minuti
    
    # Refresh Thresholds
    high_dynamics_threshold: float = 0.7
    low_stability_threshold: float = 0.5
    node_churn_threshold: float = 0.1  # 10% per ora
    bucket_change_threshold: float = 2.0
    
    # Refresh Performance
    refresh_timeout_multiplier: float = 2.0
    max_concurrent_bucket_refresh: int = 5
    refresh_retry_attempts: int = 3
    
    # Refresh Validation
    enable_refresh_validation: bool = True
    refresh_validation_timeout: float = 10.0
    min_refresh_success_rate: float = 0.8
    
    @property
    def adaptive_refresh_config(self) -> dict:
        """Configurazione completa refresh adattivo"""
        return {
            'enabled': self.enable_adaptive_refresh,
            'optimization_interval': self.refresh_optimization_interval,
            'intervals': {
                'active': {
                    'min': self.active_refresh_min_interval,
                    'max': self.active_refresh_max_interval
                },
                'stable': {
                    'min': self.stable_refresh_min_interval,
                    'max': self.stable_refresh_max_interval
                },
                'maintenance': self.maintenance_refresh_interval
            },
            'thresholds': {
                'high_dynamics': self.high_dynamics_threshold,
                'low_stability': self.low_stability_threshold,
                'node_churn': self.node_churn_threshold,
                'bucket_change': self.bucket_change_threshold
            },
            'performance': {
                'timeout_multiplier': self.refresh_timeout_multiplier,
                'max_concurrent': self.max_concurrent_bucket_refresh,
                'retry_attempts': self.refresh_retry_attempts
            },
            'validation': {
                'enabled': self.enable_refresh_validation,
                'timeout': self.refresh_validation_timeout,
                'min_success_rate': self.min_refresh_success_rate
            }
        }
```

## Vantaggi del Sistema Refresh Adattivo

1. **Efficienza**: Refresh solo quando necessario
2. **Reattività**: Risposta immediata a eventi critici
3. **Scalabilità**: Ottimizzato per 1000+ nodi
4. **Adattabilità**: Parametri dinamici basati su condizioni rete
5. **Performance**: Riduzione overhead non necessario
6. **Affidabilità**: Validazione post-refresh e recovery

## Implementazione Incrementale

1. **Fase 1**: Implementazione refresh base adattivo
2. **Fase 2**: Sistema eventi critici e refresh immediato
3. **Fase 3**: Analizzatori dinamicità rete
4. **Fase 4**: Ottimizzazione continua e predizione
5. **Fase 5**: Validazione avanzata e monitoraggio