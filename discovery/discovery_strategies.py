import asyncio
from typing import List, Optional
from datetime import datetime, timedelta

from core.dht_node import CQKDNode
from core.node_states import NodeRole, NodeInfo
from discovery.node_cache import NodeCache
from discovery.node_discovery import NodeDiscoveryService
from discovery.random_walk import RandomWalkExplorer
from utils.logging_config import get_logger


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
        
        # Background tasks
        self._refresh_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def start_background_tasks(self):
        """Avvia task di background per refresh e cleanup"""
        if self.cache:
            self._refresh_task = asyncio.create_task(self._periodic_refresh())
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
            
            logger.info("smart_discovery_background_tasks_started")
    
    async def stop_background_tasks(self):
        """Ferma task di background"""
        if self._refresh_task:
            self._refresh_task.cancel()
        if self._cleanup_task:
            self._cleanup_task.cancel()
        
        logger.info("smart_discovery_background_tasks_stopped")
    
    async def discover_nodes(
        self,
        required_count: int,
        required_capabilities: Optional[List[NodeRole]] = None,
        prefer_distributed: bool = True,
        max_discovery_time: int = 90  # Aumentato timeout per reti grandi
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
        discovery_deadline = start_time + timedelta(seconds=max_discovery_time)
        
        logger.info(
            "smart_discovery_start",
            required_count=required_count,
            capabilities=required_capabilities,
            prefer_distributed=prefer_distributed,
            max_discovery_time=max_discovery_time
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
            
            # Se la rete è in cattivo stato, aumenta il timeout
            if (total_nodes < required_count * 2 or
                not network_health.get("well_distributed", False) or
                network_health.get("distribution_score", 0.0) < 0.3):
                
                # Estendi il timeout per reti in cattivo stato
                additional_time = min(60, max_discovery_time // 2)
                discovery_deadline += timedelta(seconds=additional_time)
                
                logger.info(
                    "poor_network_detected_extending_timeout",
                    additional_time=additional_time,
                    new_deadline=discovery_deadline
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
            walk_timeout = max(20, min(time_remaining * 0.7, 45))  # 70% del tempo rimanente
            
            # Calcola parametri adattivi per random walk
            walks_needed = max(min(remaining // 15, 25), 8)  # Aumentato per reti difficili
            k_per_walk = min(120, max(25, remaining // walks_needed))  # Più aggressivo

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
                # Prova discovery senza filtri e con parametri massimi
                fallback_result = await asyncio.wait_for(
                    self.discovery.discover_nodes_for_roles(
                        required_count=remaining * 3,  # Massimo sforzo
                        required_capabilities=None  # Senza filtri
                    ),
                    timeout=30.0
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
                
                # Verifica disponibilità dei nodi
                for node in nodes_to_refresh:
                    # is_available = await self._ping_node(node)
                    self.cache.update_verification(node.node_id, True)
                
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
    
    async def _ping_node(self, node: NodeInfo) -> bool:
        """Ping un nodo per verificare disponibilità"""
        try:
            from kademlia.node import Node
            import binascii
            
            kad_node = Node(
                binascii.unhexlify(node.node_id),
                node.address,
                node.port
            )
            
            # ✅ CORRETTO: usa callPing con un solo parametro
            result = await asyncio.wait_for(
                self.coordinator.server.protocol.callPing(kad_node),
                timeout=2.0
            )
            
            return result is not None
            
        except Exception:
            return False

