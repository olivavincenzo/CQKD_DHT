# Sistema di Health Check Ottimizzato per Reti Large-Scale

## Problema Corrente
Health check disabilitato in discovery_strategies.py riga 332 (`# is_available = await self._ping_node(node)`) causa fallback a nodi non raggiungibili e instabilità della rete.

## Analisi del Problema

### Codice Attuale
```python
# discovery/discovery_strategies.py riga 332
# Verifica disponibilità dei nodi
for node in nodes_to_refresh:
    # is_available = await self._ping_node(node)  # ❌ COMMENTATO
    self.cache.update_verification(node.node_id, True)
```

### Conseguenze
- Nodi morti rimangono nella cache
- Discovery restituisce nodi non raggiungibili
- Operazioni DHT falliscono silenziosamente
- Routing table si corrompe nel tempo

## Soluzione: Sistema di Health Check Intelligente

### 1. **Architettura Health Check Multi-Livello**

```
Livello 1: Ping Semplice (Fast)
├── Timeout: 1-2 secondi
├── Frequenza: ogni 30 secondi
└── Scopo: verifica base connettività

Livello 2: Health Check Completo (Medium)
├── Timeout: 3-5 secondi
├── Frequenza: ogni 2 minuti
├── Test: ping + find_node + store/get
└── Scopo: verifica funzionalità DHT

Livello 3: Diagnostica Avanzata (Slow)
├── Timeout: 10-15 secondi
├── Frequenza: ogni 10 minuti
├── Test: suite completa DHT
└── Scopo: analisi profonda nodo
```

### 2. **Health Check Manager Ottimizzato**

#### Sistema di Health Check Gerarchico
```python
class HierarchicalHealthChecker:
    """Health checker con approccio gerarchico ottimizzato"""
    
    def __init__(self, coordinator_node: CQKDNode):
        self.coordinator = coordinator_node
        self.check_levels = {
            'fast': HealthCheckLevel(
                name='fast',
                timeout=2.0,
                interval=30,
                tests=['ping']
            ),
            'medium': HealthCheckLevel(
                name='medium',
                timeout=5.0,
                interval=120,
                tests=['ping', 'find_node', 'store_get']
            ),
            'deep': HealthCheckLevel(
                name='deep',
                timeout=15.0,
                interval=600,
                tests=['full_dht_suite']
            )
        }
        
        self.node_health_status = {}
        self.check_scheduler = HealthCheckScheduler()
        self.performance_monitor = HealthCheckPerformanceMonitor()
    
    async def start_health_monitoring(self):
        """Avvia monitoraggio health check continuo"""
        
        logger.info("hierarchical_health_check_started")
        
        # Avvia task per ogni livello
        tasks = []
        for level_name, level_config in self.check_levels.items():
            task = asyncio.create_task(
                self._periodic_health_check(level_name, level_config)
            )
            tasks.append(task)
        
        # Avvia task cleanup e ottimizzazione
        cleanup_task = asyncio.create_task(self._cleanup_and_optimize())
        tasks.append(cleanup_task)
        
        return tasks
    
    async def check_node_health(self, node_info: NodeInfo, level: str = 'fast') -> HealthStatus:
        """Esegue health check su nodo specifico"""
        
        start_time = datetime.now()
        level_config = self.check_levels.get(level)
        
        if not level_config:
            raise ValueError(f"Livello health check non valido: {level}")
        
        try:
            logger.debug(
                "node_health_check_start",
                node_id=node_info.node_id[:16],
                level=level,
                tests=level_config.tests
            )
            
            # Esegui test secondo livello
            test_results = {}
            overall_status = True
            
            for test_name in level_config.tests:
                test_result = await self._execute_test(node_info, test_name, level_config.timeout)
                test_results[test_name] = test_result
                
                if not test_result.success:
                    overall_status = False
                    # Se test critico fallisce, interrompi
                    if test_name in ['ping']:
                        break
            
            duration = (datetime.now() - start_time).total_seconds()
            
            # Crea stato health
            health_status = HealthStatus(
                node_id=node_info.node_id,
                level=level,
                overall_healthy=overall_status,
                test_results=test_results,
                duration=duration,
                timestamp=datetime.now(),
                last_checked=datetime.now()
            )
            
            # Aggiorna stato nodo
            self.node_health_status[node_info.node_id] = health_status
            
            # Registra performance
            await self.performance_monitor.record_check_performance(
                node_id=node_info.node_id,
                level=level,
                duration=duration,
                success=overall_status
            )
            
            logger.debug(
                "node_health_check_complete",
                node_id=node_info.node_id[:16],
                level=level,
                healthy=overall_status,
                duration=duration
            )
            
            return health_status
            
        except Exception as e:
            logger.error(
                "node_health_check_error",
                node_id=node_info.node_id[:16],
                level=level,
                error=str(e)
            )
            
            # Status di fallback
            return HealthStatus(
                node_id=node_info.node_id,
                level=level,
                overall_healthy=False,
                test_results={'error': str(e)},
                duration=0.0,
                timestamp=datetime.now(),
                last_checked=datetime.now()
            )
    
    async def _execute_test(self, node_info: NodeInfo, test_name: str, timeout: float) -> TestResult:
        """Esegue singolo test di health"""
        
        try:
            if test_name == 'ping':
                return await self._test_ping(node_info, timeout)
            elif test_name == 'find_node':
                return await self._test_find_node(node_info, timeout)
            elif test_name == 'store_get':
                return await self._test_store_get(node_info, timeout)
            elif test_name == 'full_dht_suite':
                return await self._test_full_dht_suite(node_info, timeout)
            else:
                return TestResult(
                    test_name=test_name,
                    success=False,
                    error=f"Test non conosciuto: {test_name}",
                    duration=0.0
                )
                
        except Exception as e:
            return TestResult(
                test_name=test_name,
                success=False,
                error=str(e),
                duration=0.0
            )
    
    async def _test_ping(self, node_info: NodeInfo, timeout: float) -> TestResult:
        """Test ping ottimizzato"""
        
        start_time = datetime.now()
        
        try:
            from kademlia.node import Node
            import binascii
            
            # Crea nodo Kademlia
            kad_node = Node(
                binascii.unhexlify(node_info.node_id),
                node_info.address,
                node_info.port
            )
            
            # Esegui ping con timeout
            result = await asyncio.wait_for(
                self.coordinator.server.protocol.callPing(kad_node),
                timeout=timeout
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            success = result is not None
            
            return TestResult(
                test_name='ping',
                success=success,
                response_time=duration,
                details={'ping_response': result},
                duration=duration
            )
            
        except asyncio.TimeoutError:
            duration = (datetime.now() - start_time).total_seconds()
            return TestResult(
                test_name='ping',
                success=False,
                error=f"Timeout dopo {duration:.2f}s",
                duration=duration
            )
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return TestResult(
                test_name='ping',
                success=False,
                error=str(e),
                duration=duration
            )
    
    async def _test_find_node(self, node_info: NodeInfo, timeout: float) -> TestResult:
        """Test find_node"""
        
        start_time = datetime.now()
        
        try:
            from kademlia.node import Node
            import binascii
            import secrets
            
            # Crea nodo target casuale
            target_id = secrets.token_hex(20)
            target_bytes = binascii.unhexlify(target_id)
            target_node = Node(target_bytes)
            
            # Crea nodo da testare
            kad_node = Node(
                binascii.unhexlify(node_info.node_id),
                node_info.address,
                node_info.port
            )
            
            # Esegui find_node
            result = await asyncio.wait_for(
                self.coordinator.server.protocol.callFindNode(kad_node, target_bytes),
                timeout=timeout
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            success = result is not None and len(result) > 0
            
            return TestResult(
                test_name='find_node',
                success=success,
                response_time=duration,
                details={
                    'nodes_found': len(result) if result else 0,
                    'target_id': target_id[:16] + "..."
                },
                duration=duration
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return TestResult(
                test_name='find_node',
                success=False,
                error=str(e),
                duration=duration
            )
    
    async def _test_store_get(self, node_info: NodeInfo, timeout: float) -> TestResult:
        """Test store/get operations"""
        
        start_time = datetime.now()
        
        try:
            import secrets
            import json
            
            # Dati di test
            test_key = f"health_check_{secrets.token_hex(8)}"
            test_value = {
                'test_id': secrets.token_hex(4),
                'timestamp': datetime.now().isoformat(),
                'node_id': node_info.node_id
            }
            
            # Test store
            store_success = await asyncio.wait_for(
                self.coordinator.server.set(test_key, json.dumps(test_value)),
                timeout=timeout / 2
            )
            
            if not store_success:
                return TestResult(
                    test_name='store_get',
                    success=False,
                    error="Store operation failed",
                    duration=(datetime.now() - start_time).total_seconds()
                )
            
            # Test get
            retrieved_value = await asyncio.wait_for(
                self.coordinator.server.get(test_key),
                timeout=timeout / 2
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            # Verifica valore
            success = False
            if retrieved_value:
                try:
                    parsed_value = json.loads(retrieved_value)
                    success = parsed_value.get('test_id') == test_value['test_id']
                except json.JSONDecodeError:
                    pass
            
            return TestResult(
                test_name='store_get',
                success=success,
                response_time=duration,
                details={
                    'test_key': test_key,
                    'store_success': bool(store_success),
                    'retrieve_success': bool(retrieved_value),
                    'value_match': success
                },
                duration=duration
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return TestResult(
                test_name='store_get',
                success=False,
                error=str(e),
                duration=duration
            )
    
    async def _test_full_dht_suite(self, node_info: NodeInfo, timeout: float) -> TestResult:
        """Suite completa di test DHT"""
        
        start_time = datetime.now()
        test_results = {}
        overall_success = True
        
        # Esegui tutti i test base
        base_tests = ['ping', 'find_node', 'store_get']
        allocated_time = timeout / len(base_tests)
        
        for test_name in base_tests:
            result = await self._execute_test(node_info, test_name, allocated_time)
            test_results[test_name] = result
            
            if not result.success:
                overall_success = False
        
        duration = (datetime.now() - start_time).total_seconds()
        
        return TestResult(
            test_name='full_dht_suite',
            success=overall_success,
            response_time=duration,
            details={
                'individual_tests': {
                    name: {
                        'success': result.success,
                        'duration': result.duration,
                        'error': result.error if not result.success else None
                    }
                    for name, result in test_results.items()
                }
            },
            duration=duration
        )
    
    async def _periodic_health_check(self, level_name: str, level_config: HealthCheckLevel):
        """Esegue health check periodico per livello"""
        
        logger.info(
            "periodic_health_check_started",
            level=level_name,
            interval=level_config.interval
        )
        
        while True:
            try:
                # Ottieni nodi da controllare
                nodes_to_check = await self._get_nodes_for_health_check(level_name)
                
                if not nodes_to_check:
                    await asyncio.sleep(level_config.interval)
                    continue
                
                logger.debug(
                    "health_check_batch_start",
                    level=level_name,
                    nodes_count=len(nodes_to_check)
                )
                
                # Esegui check in parallelo con limitazione
                semaphore = asyncio.Semaphore(10)  # Max 10 check concorrenti
                
                async def check_with_semaphore(node):
                    async with semaphore:
                        return await self.check_node_health(node, level_name)
                
                tasks = [check_with_semaphore(node) for node in nodes_to_check]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Analizza risultati
                healthy_count = sum(1 for r in results if isinstance(r, HealthStatus) and r.overall_healthy)
                unhealthy_count = len(results) - healthy_count
                
                logger.info(
                    "health_check_batch_complete",
                    level=level_name,
                    total=len(nodes_to_check),
                    healthy=healthy_count,
                    unhealthy=unhealthy_count
                )
                
                # Rimuovi nodi persistentemente non sani
                await self._remove_persistently_unhealthy_nodes()
                
                await asyncio.sleep(level_config.interval)
                
            except Exception as e:
                logger.error(
                    "periodic_health_check_error",
                    level=level_name,
                    error=str(e)
                )
                await asyncio.sleep(60)  # Retry dopo 1 minuto
    
    async def _get_nodes_for_health_check(self, level: str) -> List[NodeInfo]:
        """Ottieni lista nodi da controllare per livello"""
        
        try:
            if level == 'fast':
                # Controlla tutti i nodi attivi
                routing_info = self.coordinator.get_routing_table_info()
                all_nodes = routing_info.get("all_nodes", [])
                
                return [
                    NodeInfo(
                        node_id=node["id"],
                        address=node["address"].split(":")[0],
                        port=int(node["address"].split(":")[1]),
                        state=NodeState.ACTIVE
                    )
                    for node in all_nodes
                ]
                
            elif level == 'medium':
                # Controlla solo nodi sospetti o non verificati di recente
                suspicious_nodes = []
                current_time = datetime.now()
                
                for node_id, health_status in self.node_health_status.items():
                    # Controlla nodi non verificati da più di 2 minuti
                    if (current_time - health_status.last_checked).total_seconds() > 120:
                        # Ricostruisci NodeInfo da health_status
                        node_info = await self._reconstruct_node_info(node_id)
                        if node_info:
                            suspicious_nodes.append(node_info)
                
                return suspicious_nodes
                
            elif level == 'deep':
                # Controlla solo nodi critici o con problemi persistenti
                critical_nodes = []
                
                for node_id, health_status in self.node_health_status.items():
                    # Nodi con fallimenti ripetuti
                    if not health_status.overall_healthy:
                        node_info = await self._reconstruct_node_info(node_id)
                        if node_info:
                            critical_nodes.append(node_info)
                
                return critical_nodes
                
        except Exception as e:
            logger.error("get_nodes_for_health_check_error", error=str(e))
            return []
    
    async def _reconstruct_node_info(self, node_id: str) -> Optional[NodeInfo]:
        """Ricostruisci NodeInfo da node_id"""
        
        try:
            # Cerca nella routing table
            routing_info = self.coordinator.get_routing_table_info()
            all_nodes = routing_info.get("all_nodes", [])
            
            for node in all_nodes:
                if node["id"].startswith(node_id[:16]):
                    return NodeInfo(
                        node_id=node["id"],
                        address=node["address"].split(":")[0],
                        port=int(node["address"].split(":")[1]),
                        state=NodeState.ACTIVE
                    )
            
            return None
            
        except Exception as e:
            logger.error("reconstruct_node_info_error", error=str(e))
            return None
    
    async def _remove_persistently_unhealthy_nodes(self):
        """Rimuovi nodi persistentemente non sani"""
        
        try:
            current_time = datetime.now()
            nodes_to_remove = []
            
            for node_id, health_status in self.node_health_status.items():
                # Se un nodo è non sano per più di 10 minuti
                if (not health_status.overall_healthy and 
                    (current_time - health_status.timestamp).total_seconds() > 600):
                    nodes_to_remove.append(node_id)
            
            if nodes_to_remove:
                logger.warning(
                    "removing_persistently_unhealthy_nodes",
                    nodes_count=len(nodes_to_remove),
                    nodes=[node_id[:16] for node_id in nodes_to_remove]
                )
                
                # Rimuovi dalla routing table
                for node_id in nodes_to_remove:
                    await self._remove_node_from_routing_table(node_id)
                    del self.node_health_status[node_id]
                
        except Exception as e:
            logger.error("remove_unhealthy_nodes_error", error=str(e))
    
    async def _remove_node_from_routing_table(self, node_id: str):
        """Rimuovi nodo dalla routing table"""
        
        try:
            from kademlia.node import Node
            import binascii
            
            # Converti node_id in oggetto Node
            node_bytes = binascii.unhexlify(node_id)
            kad_node = Node(node_bytes)
            
            # Rimuovi dalla routing table
            self.coordinator.server.protocol.router.remove_contact(kad_node)
            
            logger.debug(
                "node_removed_from_routing_table",
                node_id=node_id[:16]
            )
            
        except Exception as e:
            logger.error(
                "remove_node_from_routing_table_error",
                node_id=node_id[:16],
                error=str(e)
            )
    
    async def _cleanup_and_optimize(self):
        """Task di cleanup e ottimizzazione"""
        
        while True:
            try:
                await asyncio.sleep(3600)  # Ogni ora
                
                # Cleanup vecchi stati
                cutoff_time = datetime.now() - timedelta(hours=24)
                old_nodes = [
                    node_id for node_id, status in self.node_health_status.items()
                    if status.timestamp < cutoff_time
                ]
                
                for node_id in old_nodes:
                    del self.node_health_status[node_id]
                
                if old_nodes:
                    logger.info(
                        "health_check_cleanup",
                        removed_nodes=len(old_nodes)
                    )
                
                # Ottimizza parametri basati su performance
                await self.performance_monitor.optimize_parameters()
                
            except Exception as e:
                logger.error("health_check_cleanup_error", error=str(e))
```

### 3. **Integrazione con Discovery Strategies**

#### Aggiornamento SmartDiscoveryStrategy
```python
class OptimizedSmartDiscoveryStrategy(SmartDiscoveryStrategy):
    """Smart discovery con health check abilitato e ottimizzato"""
    
    def __init__(
        self,
        coordinator_node: CQKDNode,
        enable_cache: bool = True,
        enable_random_walk: bool = True,
        enable_health_check: bool = True
    ):
        super().__init__(coordinator_node, enable_cache, enable_random_walk)
        
        # Health checker
        self.health_checker = None
        if enable_health_check:
            self.health_checker = HierarchicalHealthChecker(coordinator_node)
            self.health_check_tasks = None
    
    async def start_background_tasks(self):
        """Avvia task background inclusi health check"""
        
        # Avvia task originali
        await super().start_background_tasks()
        
        # Avvia health check se abilitato
        if self.health_checker:
            self.health_check_tasks = await self.health_checker.start_health_monitoring()
            logger.info("smart_discovery_health_check_enabled")
    
    async def stop_background_tasks(self):
        """Ferma task background inclusi health check"""
        
        # Ferma health check tasks
        if self.health_check_tasks:
            for task in self.health_check_tasks:
                task.cancel()
        
        # Ferma task originali
        await super().stop_background_tasks()
    
    async def discover_nodes(
        self,
        required_count: int,
        required_capabilities: Optional[List[NodeRole]] = None,
        prefer_distributed: bool = True,
        max_discovery_time: int = 90,
        verify_health: bool = True  # Nuovo parametro
    ) -> List[str]:
        """Discovery con health check opzionale"""
        
        start_time = datetime.now()
        discovered_node_ids = []
        discovery_deadline = start_time + timedelta(seconds=max_discovery_time)
        
        logger.info(
            "optimized_smart_discovery_start",
            required_count=required_count,
            verify_health=verify_health,
            max_discovery_time=max_discovery_time
        )
        
        # Step 1: Prova dalla cache (con health check se abilitato)
        if self.cache:
            cached_nodes = self.cache.get_by_capabilities(
                required_capabilities or [],
                required_count * 2  # Più nodi per compensare rimozioni
            ) if required_capabilities else self.cache.get_all_active()
            
            if verify_health and self.health_checker:
                # Filtra nodi sani dalla cache
                healthy_cached_nodes = []
                for node in cached_nodes:
                    health_status = self.health_checker.node_health_status.get(node.node_id)
                    if health_status and health_status.overall_healthy:
                        healthy_cached_nodes.append(node)
                
                cached_nodes = healthy_cached_nodes
            
            discovered_node_ids.extend([n.node_id for n in cached_nodes])
            
            logger.debug(
                "healthy_nodes_from_cache",
                count=len(cached_nodes),
                required=required_count
            )
        
        # Step 2: Discovery standard con health check
        remaining = required_count - len(discovered_node_ids)
        if remaining > 0 and datetime.now() < discovery_deadline:
            time_remaining = (discovery_deadline - datetime.now()).total_seconds()
            discovery_timeout = max(30, min(time_remaining * 0.6, 60))
            
            try:
                discovery_result = await asyncio.wait_for(
                    self.discovery.discover_nodes_for_roles(
                        required_count=remaining * 2,  # Più nodi per compensare
                        required_capabilities=required_capabilities
                    ),
                    timeout=discovery_timeout
                )
                
                new_nodes = discovery_result.discovered_nodes
                
                # Health check sui nuovi nodi se richiesto
                if verify_health and self.health_checker and new_nodes:
                    healthy_new_nodes = []
                    
                    # Health check parallelo con limitazione
                    semaphore = asyncio.Semaphore(5)
                    
                    async def check_and_filter(node):
                        async with semaphore:
                            health_status = await self.health_checker.check_node_health(node, 'fast')
                            return node if health_status.overall_healthy else None
                    
                    tasks = [check_and_filter(node) for node in new_nodes]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    healthy_new_nodes = [r for r in results if isinstance(r, NodeInfo)]
                    new_nodes = healthy_new_nodes
                
                discovered_node_ids.extend([n.node_id for n in new_nodes])
                
                # Aggiungi alla cache
                if self.cache:
                    for node in new_nodes:
                        self.cache.add(node)
                
                logger.info(
                    "healthy_nodes_from_discovery",
                    count=len(new_nodes),
                    remaining_before=remaining,
                    total_after=len(discovered_node_ids)
                )
                
            except asyncio.TimeoutError:
                logger.warning("standard_discovery_timeout", remaining=remaining)
            except Exception as e:
                logger.error("standard_discovery_error", error=str(e))
        
        # Continua con gli step rimanenti (random walk, fallback)...
        # ... (codice esistente con aggiunta health check dove necessario)
        
        duration = (datetime.now() - start_time).total_seconds()
        
        # Verifica finale
        if len(discovered_node_ids) < required_count:
            logger.error(
                "insufficient_healthy_nodes",
                found=len(discovered_node_ids),
                required=required_count,
                duration=duration
            )
            raise ValueError(
                f"Nodi sani insufficienti: trovati {len(discovered_node_ids)}, "
                f"richiesti {required_count}. Durata: {duration:.2f}s"
            )
        
        logger.info(
            "optimized_smart_discovery_complete",
            discovered=len(discovered_node_ids),
            required=required_count,
            duration_seconds=duration,
            health_check_enabled=verify_health
        )
        
        return discovered_node_ids
```

### 4. **Configurazione Health Check**

#### Aggiornamento config.py
```python
class Settings(BaseSettings):
    # ... configurazione esistente ...
    
    # Health Check Configuration
    enable_health_check: bool = True
    health_check_levels: List[str] = ["fast", "medium", "deep"]
    
    # Fast Health Check
    fast_check_timeout: float = 2.0
    fast_check_interval: int = 30
    fast_check_tests: List[str] = ["ping"]
    
    # Medium Health Check
    medium_check_timeout: float = 5.0
    medium_check_interval: int = 120
    medium_check_tests: List[str] = ["ping", "find_node", "store_get"]
    
    # Deep Health Check
    deep_check_timeout: float = 15.0
    deep_check_interval: int = 600
    deep_check_tests: List[str] = ["full_dht_suite"]
    
    # Health Check Thresholds
    max_unhealthy_time: int = 600  # 10 minuti
    health_check_concurrency: int = 10
    health_check_cleanup_interval: int = 3600  # 1 ora
    
    # Health Check Performance
    enable_health_check_optimization: bool = True
    health_check_performance_window: int = 100  # ultimi 100 check
    
    @property
    def health_check_config(self) -> dict:
        """Configurazione completa health check"""
        return {
            'enabled': self.enable_health_check,
            'levels': self.health_check_levels,
            'fast': {
                'timeout': self.fast_check_timeout,
                'interval': self.fast_check_interval,
                'tests': self.fast_check_tests
            },
            'medium': {
                'timeout': self.medium_check_timeout,
                'interval': self.medium_check_interval,
                'tests': self.medium_check_tests
            },
            'deep': {
                'timeout': self.deep_check_timeout,
                'interval': self.deep_check_interval,
                'tests': self.deep_check_tests
            },
            'thresholds': {
                'max_unhealthy_time': self.max_unhealthy_time,
                'concurrency': self.health_check_concurrency,
                'cleanup_interval': self.health_check_cleanup_interval
            },
            'performance': {
                'optimization_enabled': self.enable_health_check_optimization,
                'performance_window': self.health_check_performance_window
            }
        }
```

## Vantaggi del Sistema Health Check

1. **Affidabilità**: Rimozione automatica nodi non sani
2. **Performance**: Check gerarchici ottimizzati
3. **Scalabilità**: Concorrenza controllata per 1000+ nodi
4. **Adattabilità**: Parametri configurabili per diverse esigenze
5. **Monitoraggio**: Metriche dettagliate e diagnostica
6. **Compatibilità**: Integrazione trasparente con codice esistente

## Implementazione Incrementale

1. **Fase 1**: Implementazione health check base (ping)
2. **Fase 2**: Aggiunta test find_node e store/get
3. **Fase 3**: Sistema gerarchico completo
4. **Fase 4**: Integrazione con discovery strategies
5. **Fase 5**: Ottimizzazioni performance e monitoraggio