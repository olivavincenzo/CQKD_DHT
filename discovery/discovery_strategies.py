import asyncio
from typing import List, Optional, Tuple, Dict
from datetime import datetime, timedelta

from core.dht_node import CQKDNode
from core.node_states import NodeRole, NodeInfo
from discovery.node_cache import NodeCache
from discovery.node_discovery import NodeDiscoveryService
from discovery.random_walk import RandomWalkExplorer
from discovery.health_check_manager import HealthCheckManager
from utils.logging_config import get_logger
from config import settings


logger = get_logger(__name__)


class SmartDiscoveryStrategy:
    """
    Strategia intelligente che combina cache + discovery + random walk
    
    Ottimizzato per il protocollo CQKD che richiede molti nodi distribuiti
    """
    
    def __init__(
        self,
        coordinator_node: CQKDNode,
        enable_cache: bool = True,
        enable_random_walk: bool = True
    ):
        self.coordinator = coordinator_node
        
        # Componenti
        self.cache = NodeCache() if enable_cache else None
        self.discovery = NodeDiscoveryService(coordinator_node)
        self.random_walk = RandomWalkExplorer(coordinator_node) if enable_random_walk else None
        self.health_check = HealthCheckManager(coordinator_node, self.cache) if settings.enable_health_check else None
        
        # Background tasks
        self._refresh_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def start_background_tasks(self):
        """Avvia task di background per refresh e cleanup"""
        if self.cache:
            self._refresh_task = asyncio.create_task(self._periodic_refresh())
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        
        # Avvia health check se abilitato
        if self.health_check:
            self.health_check.start_background_tasks()
            
            logger.info("smart_discovery_background_tasks_started")
    
    async def stop_background_tasks(self):
        """Ferma task di background"""
        if self._refresh_task:
            self._refresh_task.cancel()
        if self._cleanup_task:
            self._cleanup_task.cancel()
        
        # Ferma health check se abilitato
        if self.health_check:
            await self.health_check.stop_background_tasks()
        
        logger.info("smart_discovery_background_tasks_stopped")
    
    async def discover_nodes(
        self,
        required_count: int,
        required_capabilities: Optional[List[NodeRole]] = None,
        prefer_distributed: bool = True,
        max_discovery_time: Optional[int] = None  # Sarà calcolato adattivamente
    ) -> List[str]:
        """
        Scopre nodi con strategia ottimizzata e robusta
        
        Processo migliorato:
        1. Analizza stato della rete con get_routing_table_info()
        2. Controlla cache per nodi già noti
        3. Se insufficienti, esegui discovery standard con retry
        4. Se serve diversificazione, usa random walk
        5. Fallback aggressivo se ancora insufficienti
        
        Args:
            required_count: Numero di nodi richiesti
            required_capabilities: Capacità richieste
            prefer_distributed: Se true, usa random walk per distribuzione
            max_discovery_time: Timeout massimo per il discovery (aumentato)
            
        Returns:
            List[str]: Lista di node_id disponibili
        """
        start_time = datetime.now()
        discovered_node_ids = []
        
        # Calcola timeout adattivo se non specificato
        if max_discovery_time is None:
            # Ottieni dimensione della rete per calcolo adattivo
            try:
                routing_info = self.coordinator.get_routing_table_info()
                network_size = routing_info.get("total_nodes", 0)
                
                # Usa parametri adattivi dalla configurazione
                adaptive_params = settings.calculate_adaptive_kademlia_params(network_size)
                max_discovery_time = adaptive_params['discovery_timeout']
                
                logger.info(
                    "adaptive_discovery_timeout_calculated",
                    network_size=network_size,
                    network_category=adaptive_params.get('network_category', 'unknown'),
                    timeout=max_discovery_time
                )
            except Exception as e:
                logger.warning(
                    "failed_to_calculate_adaptive_timeout",
                    error=str(e),
                    using_default=True
                )
                max_discovery_time = settings.max_discovery_time
        
        discovery_deadline = start_time + timedelta(seconds=max_discovery_time)
        
        logger.info(
            "smart_discovery_start",
            required_count=required_count,
            capabilities=required_capabilities,
            prefer_distributed=prefer_distributed,
            max_discovery_time=max_discovery_time,
            adaptive_enabled=settings.enable_adaptive_kademlia
        )
        
        # NUOVO: Analizza lo stato della rete all'inizio
        try:
            routing_info = self.coordinator.get_routing_table_info()
            network_health = routing_info.get("network_health", {})
            total_nodes = routing_info.get("total_nodes", 0)
            
            logger.info(
                "initial_network_analysis",
                total_nodes=total_nodes,
                well_distributed=network_health.get("well_distributed", False),
                distribution_score=network_health.get("distribution_score", 0.0),
                active_buckets=routing_info.get("active_buckets", 0)
            )
            
            # Se la rete è in cattivo stato, aumenta il timeout adattivamente
            if (total_nodes < required_count):
                
                # Calcola estensione adattiva basata sulla dimensione della rete
                adaptive_params = settings.calculate_adaptive_kademlia_params(total_nodes)
                base_extension = int(adaptive_params['query_timeout'] * 3)  # 3x il timeout di query
                
                # Estendi il timeout per reti in cattivo stato
                additional_time = min(base_extension, max_discovery_time // 2)
                discovery_deadline += timedelta(seconds=additional_time)
                
                logger.info(
                    "poor_network_detected_extending_timeout",
                    total_nodes=total_nodes,
                    network_category=adaptive_params.get('network_category', 'unknown'),
                    additional_time=additional_time,
                    new_deadline=discovery_deadline,
                    extended_timeout_seconds=(discovery_deadline - start_time).total_seconds()
                )
                
        except Exception as e:
            logger.warning("failed_to_analyze_network_state", error=str(e))
        
        # Step 1: Prova dalla cache
        if self.cache:
            cached_nodes = self.cache.get_by_capabilities(
                required_capabilities or [],
                required_count
            ) if required_capabilities else self.cache.get_all_active()
            
            discovered_node_ids.extend([n.node_id for n in cached_nodes])
            
            logger.debug(
                "nodes_from_cache",
                count=len(cached_nodes),
                required=required_count
            )
        
        # Step 2: Se ancora servono nodi, usa discovery standard con retry e timeout
        remaining = required_count - len(discovered_node_ids)
        if remaining > 0 and datetime.now() < discovery_deadline:
            # Calcola timeout adattivo basato sul tempo rimanente
            time_remaining = (discovery_deadline - datetime.now()).total_seconds()
            discovery_timeout = max(30, min(time_remaining * 0.6, 60))  # 60% del tempo rimanente
            
            try:
                logger.info(
                    "starting_standard_discovery",
                    remaining=remaining,
                    timeout=discovery_timeout
                )
                
                discovery_result = await asyncio.wait_for(
                    self.discovery.discover_nodes_for_roles(
                        required_count=remaining * 2,  # Cerca più nodi del necessario
                        required_capabilities=required_capabilities
                    ),
                    timeout=discovery_timeout
                )
            except asyncio.TimeoutError:
                logger.warning("standard_discovery_timeout", remaining=remaining)
                discovery_result = type('DiscoveryResult', (), {'discovered_nodes': []})()
            except Exception as e:
                logger.error("standard_discovery_error", error=str(e))
                discovery_result = type('DiscoveryResult', (), {'discovered_nodes': []})()
            
            new_nodes = discovery_result.discovered_nodes
            discovered_node_ids.extend([n.node_id for n in new_nodes])
            
            # Aggiungi alla cache
            if self.cache:
                for node in new_nodes:
                    self.cache.add(node)
            
            logger.info(
                "nodes_from_standard_discovery",
                count=len(new_nodes),
                remaining_before=remaining,
                total_after=len(discovered_node_ids)
            )
        
        # Step 3: Se ancora servono nodi, prova random walk con timeout
        remaining = required_count - len(discovered_node_ids)
        if remaining > 0 and prefer_distributed and self.random_walk and datetime.now() < discovery_deadline:
            time_remaining = (discovery_deadline - datetime.now()).total_seconds()
            
            # Calcola timeout adattivo per random walk basato sui parametri correnti
            current_params = self.discovery._get_current_parameters()
            base_walk_timeout = current_params['query_timeout'] * 4  # 4x il timeout di query
            walk_timeout = max(base_walk_timeout, min(time_remaining * 0.7, 60))
            
            # Calcola parametri adattivi per random walk basati sulla dimensione della rete
            network_size = current_params['network_size']
            if network_size <= settings.small_network_threshold:
                walks_needed = max(min(remaining // 10, 15), 5)
                k_per_walk = min(60, max(20, remaining // walks_needed))
            elif network_size <= settings.medium_network_threshold:
                walks_needed = max(min(remaining // 12, 20), 6)
                k_per_walk = min(80, max(25, remaining // walks_needed))
            elif network_size <= settings.large_network_threshold:
                walks_needed = max(min(remaining // 15, 25), 8)
                k_per_walk = min(100, max(30, remaining // walks_needed))
            else:
                walks_needed = max(min(remaining // 20, 30), 10)
                k_per_walk = min(120, max(40, remaining // walks_needed))

            try:
                logger.info(
                    "starting_random_walk",
                    remaining=remaining,
                    walks_needed=walks_needed,
                    k_per_walk=k_per_walk,
                    timeout=walk_timeout
                )
                
                explored_nodes = await asyncio.wait_for(
                    self.random_walk.explore_network(
                        walk_count=walks_needed,
                        k_per_walk=k_per_walk
                    ),
                    timeout=walk_timeout
                )
            except asyncio.TimeoutError:
                logger.warning("random_walk_timeout", remaining=remaining)
                explored_nodes = []
            except Exception as e:
                logger.error("random_walk_error", error=str(e))
                explored_nodes = []
            
            # Filtra per capacità se richieste
            if required_capabilities:
                explored_nodes = [
                    node for node in explored_nodes
                    if all(cap in node.capabilities for cap in required_capabilities)
                ]
            
            # Aggiungi nodi non già scoperti
            for node in explored_nodes:
                if node.node_id not in discovered_node_ids:
                    discovered_node_ids.append(node.node_id)
                    
                    # Aggiungi alla cache
                    if self.cache:
                        self.cache.add(node)
                    
                    if len(discovered_node_ids) >= required_count:
                        break
            
            logger.info(
                "nodes_from_random_walk",
                count=len(explored_nodes),
                remaining_before=remaining,
                total_after=len(discovered_node_ids)
            )
        
        # Step 4: Fallback aggressivo se ancora insufficienti
        remaining = required_count - len(discovered_node_ids)
        if remaining > 0 and datetime.now() < discovery_deadline:
            logger.warning(
                "attempting_aggressive_fallback",
                remaining=remaining,
                time_left=(discovery_deadline - datetime.now()).total_seconds()
            )
            
            try:
                # Calcola timeout adattivo per fallback
                current_params = self.discovery._get_current_parameters()
                fallback_timeout = min(
                    current_params['query_timeout'] * 3,
                    settings.max_query_timeout
                )
                
                # Prova discovery senza filtri e con parametri massimi
                fallback_result = await asyncio.wait_for(
                    self.discovery.discover_nodes_for_roles(
                        required_count=remaining * 3,  # Massimo sforzo
                        required_capabilities=None  # Senza filtri
                    ),
                    timeout=fallback_timeout
                )
                
                fallback_nodes = fallback_result.discovered_nodes
                discovered_node_ids.extend([n.node_id for n in fallback_nodes])
                
                # Aggiungi alla cache
                if self.cache:
                    for node in fallback_nodes:
                        self.cache.add(node)
                
                logger.info(
                    "nodes_from_aggressive_fallback",
                    count=len(fallback_nodes),
                    total_after=len(discovered_node_ids)
                )
                
            except Exception as e:
                logger.error("aggressive_fallback_failed", error=str(e))
        
        duration = (datetime.now() - start_time).total_seconds()
        
        # Verifica finale se abbiamo trovato abbastanza nodi
        if len(discovered_node_ids) < required_count:
            logger.error(
                "insufficient_nodes_after_all_strategies",
                found=len(discovered_node_ids),
                required=required_count,
                duration=duration,
                strategies_used=["cache", "standard_discovery", "random_walk", "aggressive_fallback"]
            )
            raise ValueError(
                f"Nodi insufficienti dopo tutte le strategie: trovati {len(discovered_node_ids)}, "
                f"richiesti {required_count}. Durata: {duration:.2f}s"
            )
        
        logger.info(
            "smart_discovery_complete",
            discovered=len(discovered_node_ids),
            required=required_count,
            duration_seconds=duration,
            cache_stats=self.cache.get_stats() if self.cache else {}
        )
        
        # NUOVO: Restituisci TUTTI i nodi trovati, non solo quelli richiesti
        # Questo permette al chiamante di decidere come usare i nodi extra
        logger.info(
            "smart_discovery_returning_all_nodes",
            returning=len(discovered_node_ids),
            required=required_count
        )
        return discovered_node_ids
    
    async def _periodic_refresh(self):
        """Task periodico per refresh dei nodi in cache"""
        while True:
            try:
                await asyncio.sleep(300)  # Ogni 5 minuti (come Kademlia standard)
                
                if not self.cache:
                    continue
                
                nodes_to_refresh = self.cache.get_nodes_needing_refresh()
                
                if not nodes_to_refresh:
                    continue
                
                logger.info(
                    "periodic_refresh_start",
                    nodes_count=len(nodes_to_refresh)
                )
                
                # Verifica disponibilità dei nodi con health check manager
                if self.health_check:
                    # Usa il health check manager per verifica batch
                    await self._batch_verify_nodes(nodes_to_refresh)
                else:
                    # Fallback: verifica manuale con timeout appropriati
                    await self._manual_verify_nodes(nodes_to_refresh)
                
                logger.info(
                    "periodic_refresh_complete",
                    refreshed=len(nodes_to_refresh)
                )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("periodic_refresh_error", error=str(e))
    
    async def _periodic_cleanup(self):
        """Task periodico per cleanup cache"""
        while True:
            try:
                await asyncio.sleep(600)  # Ogni 10 minuti
                
                if not self.cache:
                    continue
                
                removed = self.cache.cleanup_expired()
                
                if removed > 0:
                    logger.info("cache_cleanup_executed", removed=removed)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("cache_cleanup_error", error=str(e))
    
    async def _batch_verify_nodes(self, nodes: List[NodeInfo]):
        """Verifica disponibilità nodi usando health check manager"""
        try:
            params = settings.calculate_health_check_params(len(nodes))
            
            # Esegui verifica batch con timeout appropriati
            from discovery.health_check_manager import HealthCheckLevel
            
            # Usa fast check per refresh periodico
            results = await self.health_check._execute_batch_health_check(
                nodes,
                HealthCheckLevel.FAST,
                params['fast_timeout'],
                params['batch_size']
            )
            
            # Aggiorna cache basandosi sui risultati
            for result in results:
                self.cache.update_verification(result.node_id, result.success)
            
            logger.info(
                "batch_node_verification_completed",
                total_nodes=len(nodes),
                successful=sum(1 for r in results if r.success),
                failed=sum(1 for r in results if not r.success)
            )
            
        except Exception as e:
            logger.error("batch_node_verification_failed", error=str(e))
            # Fallback a verifica manuale
            await self._manual_verify_nodes(nodes)
    
    async def _manual_verify_nodes(self, nodes: List[NodeInfo]):
        """Verifica manuale dei nodi con timeout appropriati"""
        params = settings.calculate_health_check_params(len(nodes))
        timeout = params['fast_timeout']
        
        # Esegui verifica in parallelo con limite di concorrenza
        semaphore = asyncio.Semaphore(params['concurrent_batches'])
        
        async def verify_single_node(node: NodeInfo) -> Tuple[str, bool]:
            async with semaphore:
                return node.node_id, await self._ping_node(node, timeout)
        
        tasks = [verify_single_node(node) for node in nodes]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Processa risultati
        successful = 0
        for result in results:
            if isinstance(result, tuple) and len(result) == 2:
                node_id, is_available = result
                self.cache.update_verification(node_id, is_available)
                if is_available:
                    successful += 1
        
        logger.info(
            "manual_node_verification_completed",
            total_nodes=len(nodes),
            successful=successful,
            failed=len(nodes) - successful
        )
    
    async def _ping_node(self, node: NodeInfo, timeout: Optional[float] = None) -> bool:
        """Ping un nodo per verificare disponibilità con timeout configurabile"""
        try:
            from kademlia.node import Node
            import binascii
            
            # Usa timeout appropriato se non specificato
            if timeout is None:
                params = settings.calculate_health_check_params(0)
                timeout = params['fast_timeout']
            
            kad_node = Node(
                binascii.unhexlify(node.node_id),
                node.address,
                node.port
            )
            
            # ✅ CORRETTO: usa callPing con timeout appropriato
            result = await asyncio.wait_for(
                self.coordinator.server.protocol.callPing(kad_node),
                timeout=timeout
            )
            
            return result is not None
            
        except Exception as e:
            logger.debug(
                "ping_node_failed",
                node_id=node.node_id[:16],
                timeout=timeout,
                error=str(e)
            )
            return False
    
    def get_health_stats(self) -> Dict:
        """Ottieni statistiche del health check"""
        if self.health_check:
            return self.health_check.get_stats()
        return {"enabled": False}
    
    def get_node_health_status(self, node_id: str) -> Optional[Dict]:
        """Ottieni stato di salute di un nodo specifico"""
        if self.health_check:
            status = self.health_check.get_health_status(node_id)
            if status:
                return {
                    "node_id": status.node_id,
                    "consecutive_failures": status.consecutive_failures,
                    "last_success": status.last_success.isoformat() if status.last_success else None,
                    "last_failure": status.last_failure.isoformat() if status.last_failure else None,
                    "last_check": status.last_check.isoformat() if status.last_check else None,
                    "last_level": status.last_level.value,
                    "availability_score": status.availability_score,
                    "is_critical": status.is_critical,
                    "total_checks": status.total_checks,
                    "successful_checks": status.successful_checks
                }
        return None

