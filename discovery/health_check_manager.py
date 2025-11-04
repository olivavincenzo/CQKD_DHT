import asyncio
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import threading
from collections import defaultdict

from core.dht_node import CQKDNode
from core.node_states import NodeInfo, NodeState, NodeRole
from discovery.node_cache import NodeCache, CachedNode
from utils.logging_config import get_logger
from config import settings


logger = get_logger(__name__)


class HealthCheckLevel(Enum):
    """Livelli di health check"""
    FAST = "fast"      # 1s timeout per ping base
    MEDIUM = "medium"  # 2s timeout per verifica completa
    DEEP = "deep"      # 5s timeout per nodi critici


@dataclass
class HealthCheckResult:
    """Risultato di un health check"""
    node_id: str
    level: HealthCheckLevel
    success: bool
    response_time: float
    timestamp: datetime
    error: Optional[str] = None


@dataclass
class NodeHealthStatus:
    """Stato di salute di un nodo"""
    node_id: str
    consecutive_failures: int = 0
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    last_check: Optional[datetime] = None
    last_level: HealthCheckLevel = HealthCheckLevel.FAST
    availability_score: float = 1.0
    is_critical: bool = False
    total_checks: int = 0
    successful_checks: int = 0
    
    def update_success(self, result: HealthCheckResult):
        """Aggiorna stato dopo check riuscito"""
        self.consecutive_failures = 0
        self.last_success = result.timestamp
        self.last_check = result.timestamp
        self.last_level = result.level
        self.total_checks += 1
        self.successful_checks += 1
        self._update_availability_score()
    
    def update_failure(self, result: HealthCheckResult):
        """Aggiorna stato dopo check fallito"""
        self.consecutive_failures += 1
        self.last_failure = result.timestamp
        self.last_check = result.timestamp
        self.last_level = result.level
        self.total_checks += 1
        self._update_availability_score()
    
    def _update_availability_score(self):
        """Calcola score di disponibilità"""
        if self.total_checks > 0:
            self.availability_score = self.successful_checks / self.total_checks
    
    def needs_removal(self, failure_threshold: int, min_score: float) -> bool:
        """Verifica se il nodo deve essere rimosso"""
        return (self.consecutive_failures >= failure_threshold or 
                self.availability_score < min_score)


class HealthCheckManager:
    """
    Gestore centralizzato per health check gerarchico dei nodi
    
    Implementa un sistema a 3 livelli con timeout adattivi:
    - Fast check: 1s timeout per ping base
    - Medium check: 2s timeout per verifica completa  
    - Deep check: 5s timeout per nodi critici
    """
    
    def __init__(self, coordinator_node: CQKDNode, node_cache: Optional[NodeCache] = None):
        self.coordinator = coordinator_node
        self.node_cache = node_cache
        
        # Stato di salute dei nodi
        self._health_status: Dict[str, NodeHealthStatus] = {}
        
        # Lock per thread-safety
        self._lock = threading.RLock()
        
        # Task di background
        self._fast_check_task: Optional[asyncio.Task] = None
        self._medium_check_task: Optional[asyncio.Task] = None
        self._deep_check_task: Optional[asyncio.Task] = None
        
        # Statistiche
        self.stats = {
            "fast_checks": 0,
            "medium_checks": 0,
            "deep_checks": 0,
            "successful_checks": 0,
            "failed_checks": 0,
            "nodes_removed": 0,
            "avg_response_time": 0.0
        }
        
        # Cache parametri adattivi
        self._cached_params: Optional[Dict] = None
        self._params_cache_time: Optional[datetime] = None
        self._params_cache_ttl = timedelta(minutes=5)
        
        logger.info("health_check_manager_initialized")
    
    def start_background_tasks(self):
        """Avvia task di background per health check"""
        if not settings.enable_health_check:
            logger.info("health_check_disabled")
            return
        
        params = self._get_current_params()
        
        self._fast_check_task = asyncio.create_task(
            self._periodic_health_check(
                HealthCheckLevel.FAST,
                params['fast_interval']
            )
        )
        
        self._medium_check_task = asyncio.create_task(
            self._periodic_health_check(
                HealthCheckLevel.MEDIUM,
                params['medium_interval']
            )
        )
        
        self._deep_check_task = asyncio.create_task(
            self._periodic_health_check(
                HealthCheckLevel.DEEP,
                params['deep_interval']
            )
        )
        
        logger.info(
            "health_check_background_tasks_started",
            fast_interval=params['fast_interval'],
            medium_interval=params['medium_interval'],
            deep_interval=params['deep_interval']
        )
    
    async def stop_background_tasks(self):
        """Ferma task di background"""
        for task in [self._fast_check_task, self._medium_check_task, self._deep_check_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        logger.info("health_check_background_tasks_stopped")
    
    def _get_current_params(self) -> Dict:
        """Ottiene parametri correnti, aggiornandoli se necessario"""
        now = datetime.now()
        
        if (self._params_cache_time is None or
            now - self._params_cache_time > self._params_cache_ttl):
            
            # Calcola dimensione della rete
            try:
                routing_info = self.coordinator.get_routing_table_info()
                network_size = routing_info.get("total_nodes", 0)
            except Exception:
                network_size = settings.small_network_threshold
            
            # Calcola parametri adattivi
            self._cached_params = settings.calculate_health_check_params(network_size)
            self._params_cache_time = now
            
            logger.info(
                "health_check_params_updated",
                network_size=network_size,
                params=self._cached_params
            )
        
        return self._cached_params
    
    async def _periodic_health_check(self, level: HealthCheckLevel, interval: int):
        """Task periodico per health check di un livello specifico"""
        while True:
            try:
                await asyncio.sleep(interval)
                
                if not settings.enable_health_check:
                    continue
                
                await self._execute_health_check_level(level)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "periodic_health_check_error",
                    level=level.value,
                    error=str(e)
                )
    
    async def _execute_health_check_level(self, level: HealthCheckLevel):
        """Esegue health check per un livello specifico"""
        start_time = datetime.now()
        
        # Ottieni nodi da controllare
        nodes_to_check = self._get_nodes_for_level(level)
        
        if not nodes_to_check:
            return
        
        params = self._get_current_params()
        timeout = self._get_timeout_for_level(level, params)
        
        logger.info(
            "health_check_started",
            level=level.value,
            nodes_count=len(nodes_to_check),
            timeout=timeout,
            batch_size=params['batch_size']
        )
        
        # Esegui check in batch
        results = await self._execute_batch_health_check(
            nodes_to_check, level, timeout, params['batch_size']
        )
        
        # Processa risultati
        await self._process_health_check_results(results)
        
        duration = (datetime.now() - start_time).total_seconds()
        self.stats[f"{level.value}_checks"] += len(results)
        
        logger.info(
            "health_check_completed",
            level=level.value,
            nodes_checked=len(results),
            successful=sum(1 for r in results if r.success),
            failed=sum(1 for r in results if not r.success),
            duration=duration
        )
    
    def _get_nodes_for_level(self, level: HealthCheckLevel) -> List[NodeInfo]:
        """Ottieni nodi da controllare per un livello specifico"""
        nodes_to_check = []
        
        if level == HealthCheckLevel.FAST:
            # Fast check: tutti i nodi attivi
            if self.node_cache:
                nodes_to_check = self.node_cache.get_all_active()
            else:
                nodes_to_check = self._get_all_routing_table_nodes()
        
        elif level == HealthCheckLevel.MEDIUM:
            # Medium check: nodi con score basso o non verificati di recente
            with self._lock:
                for node_id, status in self._health_status.items():
                    if (status.availability_score < 0.7 or
                        (status.last_check and 
                         datetime.now() - status.last_check > timedelta(minutes=10))):
                        node_info = self._get_node_info(node_id)
                        if node_info:
                            nodes_to_check.append(node_info)
        
        elif level == HealthCheckLevel.DEEP:
            # Deep check: nodi critici o con fallimenti consecutivi
            with self._lock:
                for node_id, status in self._health_status.items():
                    if (status.is_critical or
                        status.consecutive_failures > 0 or
                        status.availability_score < 0.5):
                        node_info = self._get_node_info(node_id)
                        if node_info:
                            nodes_to_check.append(node_info)
        
        return nodes_to_check
    
    def _get_timeout_for_level(self, level: HealthCheckLevel, params: Dict) -> float:
        """Ottieni timeout per un livello specifico"""
        if level == HealthCheckLevel.FAST:
            return params['fast_timeout']
        elif level == HealthCheckLevel.MEDIUM:
            return params['medium_timeout']
        else:  # DEEP
            return params['deep_timeout']
    
    async def _execute_batch_health_check(
        self,
        nodes: List[NodeInfo],
        level: HealthCheckLevel,
        timeout: float,
        batch_size: int
    ) -> List[HealthCheckResult]:
        """Esegue health check in batch"""
        results = []
        params = self._get_current_params()
        concurrent_batches = params['concurrent_batches']
        
        # Dividi nodi in batch
        batches = [
            nodes[i:i + batch_size] 
            for i in range(0, len(nodes), batch_size)
        ]
        
        # Esegui batch in parallelo
        semaphore = asyncio.Semaphore(concurrent_batches)
        
        async def process_batch(batch: List[NodeInfo]) -> List[HealthCheckResult]:
            async with semaphore:
                batch_results = []
                
                # Esegui check nel batch in parallelo
                tasks = [
                    self._check_single_node(node, level, timeout)
                    for node in batch
                ]
                
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Filtra risultati validi
                valid_results = []
                for result in batch_results:
                    if isinstance(result, HealthCheckResult):
                        valid_results.append(result)
                    else:
                        logger.warning(
                            "health_check_exception",
                            error=str(result)
                        )
                
                return valid_results
        
        # Esegui tutti i batch
        all_batch_tasks = [process_batch(batch) for batch in batches]
        all_batch_results = await asyncio.gather(*all_batch_tasks, return_exceptions=True)
        
        # Raccogli tutti i risultati
        for batch_result in all_batch_results:
            if isinstance(batch_result, list):
                results.extend(batch_result)
        
        return results
    
    async def _check_single_node(
        self,
        node: NodeInfo,
        level: HealthCheckLevel,
        timeout: float
    ) -> HealthCheckResult:
        """Esegue health check su un singolo nodo"""
        start_time = datetime.now()
        
        try:
            if level == HealthCheckLevel.FAST:
                success = await self._fast_ping_node(node, timeout)
            elif level == HealthCheckLevel.MEDIUM:
                success = await self._medium_check_node(node, timeout)
            else:  # DEEP
                success = await self._deep_check_node(node, timeout)
            
            response_time = (datetime.now() - start_time).total_seconds()
            
            result = HealthCheckResult(
                node_id=node.node_id,
                level=level,
                success=success,
                response_time=response_time,
                timestamp=start_time
            )
            
            return result
            
        except Exception as e:
            response_time = (datetime.now() - start_time).total_seconds()
            
            result = HealthCheckResult(
                node_id=node.node_id,
                level=level,
                success=False,
                response_time=response_time,
                timestamp=start_time,
                error=str(e)
            )
            
            return result
    
    async def _fast_ping_node(self, node: NodeInfo, timeout: float) -> bool:
        """Ping rapido del nodo"""
        try:
            from kademlia.node import Node
            import binascii
            
            kad_node = Node(
                binascii.unhexlify(node.node_id),
                node.address,
                node.port
            )
            
            result = await asyncio.wait_for(
                self.coordinator.server.protocol.callPing(kad_node),
                timeout=timeout
            )
            
            return result is not None
            
        except Exception:
            return False
    
    async def _medium_check_node(self, node: NodeInfo, timeout: float) -> bool:
        """Check completo del nodo"""
        try:
            # Prima fai ping base
            ping_success = await self._fast_ping_node(node, timeout * 0.5)
            if not ping_success:
                return False
            
            # Poi verifica routing table
            from kademlia.node import Node
            import binascii
            
            kad_node = Node(
                binascii.unhexlify(node.node_id),
                node.address,
                node.port
            )
            
            # Try FIND_NODE per verificare che il nodo sia responsive
            result = await asyncio.wait_for(
                self.coordinator.server.protocol.callFindNode(
                    kad_node,
                    binascii.unhexlify(self.coordinator.server.node.id)
                ),
                timeout=timeout * 0.5
            )
            
            return result is not None
            
        except Exception:
            return False
    
    async def _deep_check_node(self, node: NodeInfo, timeout: float) -> bool:
        """Check approfondito per nodi critici"""
        try:
            # Esegui check completo
            medium_success = await self._medium_check_node(node, timeout * 0.7)
            if not medium_success:
                return False
            
            # Verifica aggiuntive per nodi critici
            # Potrebbe includere verifica delle capacità, stato, etc.
            
            return True
            
        except Exception:
            return False
    
    async def _process_health_check_results(self, results: List[HealthCheckResult]):
        """Processa risultati dei health check"""
        params = self._get_current_params()
        nodes_to_remove = []
        
        with self._lock:
            for result in results:
                # Ottieni o crea stato di salute
                if result.node_id not in self._health_status:
                    self._health_status[result.node_id] = NodeHealthStatus(
                        node_id=result.node_id,
                        is_critical=self._is_critical_node(result.node_id)
                    )
                
                status = self._health_status[result.node_id]
                
                # Aggiorna stato
                if result.success:
                    status.update_success(result)
                    self.stats["successful_checks"] += 1
                    
                    # Aggiorna cache se disponibile
                    if self.node_cache:
                        self.node_cache.update_verification(result.node_id, True)
                else:
                    status.update_failure(result)
                    self.stats["failed_checks"] += 1
                    
                    # Aggiorna cache se disponibile
                    if self.node_cache:
                        self.node_cache.mark_unavailable(result.node_id)
                    
                    # Verifica se rimuovere il nodo
                    if status.needs_removal(
                        params['failure_threshold'],
                        params['min_availability_score']
                    ):
                        nodes_to_remove.append(result.node_id)
        
        # Rimuovi nodi non sani
        if nodes_to_remove:
            await self._remove_unhealthy_nodes(nodes_to_remove)
        
        # Aggiorna statistiche
        self._update_stats(results)
    
    def _is_critical_node(self, node_id: str) -> bool:
        """Verifica se un nodo è critico"""
        try:
            # Controlla se il nodo ha ruoli critici
            if self.node_cache:
                cached = self.node_cache._cache.get(node_id)
                if cached and cached.node_info.capabilities:
                    priority_roles = settings.health_check_priority_roles
                    for role in priority_roles:
                        if NodeRole(role) in cached.node_info.capabilities:
                            return True
            
            return False
            
        except Exception:
            return False
    
    def _get_node_info(self, node_id: str) -> Optional[NodeInfo]:
        """Ottieni NodeInfo per un node_id"""
        if self.node_cache:
            cached = self.node_cache.get(node_id)
            if cached:
                return cached
        
        # Fallback: cerca nella routing table
        try:
            from kademlia.node import Node
            import binascii
            
            router = self.coordinator.server.protocol.router
            target_bytes = binascii.unhexlify(node_id)
            
            for bucket in router.buckets:
                for node in bucket.get_nodes():
                    if node.id == target_bytes:
                        return NodeInfo(
                            node_id=node_id,
                            address=node.ip,
                            port=node.port,
                            state=NodeState.ACTIVE,
                            current_role=None,
                            last_seen=datetime.now(),
                            capabilities=[]
                        )
        except Exception:
            pass
        
        return None
    
    def _get_all_routing_table_nodes(self) -> List[NodeInfo]:
        """Ottieni tutti i nodi dalla routing table"""
        try:
            from kademlia.node import Node
            import binascii
            
            router = self.coordinator.server.protocol.router
            nodes = []
            
            for bucket in router.buckets:
                for node in bucket.get_nodes():
                    node_info = NodeInfo(
                        node_id=node.id.hex() if isinstance(node.id, bytes) else str(node.id),
                        address=node.ip,
                        port=node.port,
                        state=NodeState.ACTIVE,
                        current_role=None,
                        last_seen=datetime.now(),
                        capabilities=[]
                    )
                    nodes.append(node_info)
            
            return nodes
            
        except Exception as e:
            logger.error("failed_to_get_routing_table_nodes", error=str(e))
            return []
    
    async def _remove_unhealthy_nodes(self, node_ids: List[str]):
        """Rimuovi nodi non sani dalla cache e routing table"""
        for node_id in node_ids:
            try:
                # Rimuovi dalla cache
                if self.node_cache:
                    self.node_cache._remove(node_id)
                
                # Rimuovi dalla routing table
                self.coordinator.server.protocol.router.remove_contact(
                    binascii.unhexlify(node_id)
                )
                
                # Rimuovi dallo stato di salute
                with self._lock:
                    self._health_status.pop(node_id, None)
                
                self.stats["nodes_removed"] += 1
                
                logger.info(
                    "unhealthy_node_removed",
                    node_id=node_id[:16]
                )
                
            except Exception as e:
                logger.warning(
                    "failed_to_remove_unhealthy_node",
                    node_id=node_id[:16],
                    error=str(e)
                )
    
    def _update_stats(self, results: List[HealthCheckResult]):
        """Aggiorna statistiche"""
        if results:
            avg_time = sum(r.response_time for r in results) / len(results)
            self.stats["avg_response_time"] = avg_time
    
    def get_health_status(self, node_id: str) -> Optional[NodeHealthStatus]:
        """Ottieni stato di salute di un nodo"""
        with self._lock:
            return self._health_status.get(node_id)
    
    def get_all_health_status(self) -> Dict[str, NodeHealthStatus]:
        """Ottieni stato di salute di tutti i nodi"""
        with self._lock:
            return self._health_status.copy()
    
    def get_stats(self) -> Dict:
        """Ottieni statistiche del health check manager"""
        with self._lock:
            stats = self.stats.copy()
            stats["monitored_nodes"] = len(self._health_status)
            
            # Calcola statistiche aggiuntive
            if stats["monitored_nodes"] > 0:
                healthy_nodes = sum(
                    1 for status in self._health_status.values()
                    if status.consecutive_failures == 0
                )
                stats["healthy_nodes"] = healthy_nodes
                stats["health_rate"] = healthy_nodes / stats["monitored_nodes"]
            else:
                stats["healthy_nodes"] = 0
                stats["health_rate"] = 0.0
            
            return stats