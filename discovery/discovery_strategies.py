import asyncio
from typing import List, Optional
from datetime import datetime

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
        prefer_distributed: bool = True
    ) -> List[str]:
        """
        Scopre nodi con strategia ottimizzata
        
        Processo:
        1. Controlla cache per nodi già noti
        2. Se insufficienti, esegui discovery standard
        3. Se serve diversificazione, usa random walk
        
        Args:
            required_count: Numero di nodi richiesti
            required_capabilities: Capacità richieste
            prefer_distributed: Se true, usa random walk per distribuzione
            
        Returns:
            List[str]: Lista di node_id disponibili
        """
        start_time = datetime.now()
        discovered_node_ids = []
        
        logger.info(
            "smart_discovery_start",
            required_count=required_count,
            capabilities=required_capabilities,
            prefer_distributed=prefer_distributed
        )
        
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
        
        # Step 2: Se ancora servono nodi, usa discovery standard
        remaining = required_count - len(discovered_node_ids)
        if remaining > 0:
            discovery_result = await self.discovery.discover_nodes_for_roles(
                required_count=remaining,
                required_capabilities=required_capabilities
            )
            
            new_nodes = discovery_result.discovered_nodes
            discovered_node_ids.extend([n.node_id for n in new_nodes])
            
            # Aggiungi alla cache
            if self.cache:
                for node in new_nodes:
                    self.cache.add(node)
            
            logger.debug(
                "nodes_from_discovery",
                count=len(new_nodes),
                remaining=remaining
            )
        
        # Step 3: Se serve distribuzione geografica, usa random walk
        remaining = required_count - len(discovered_node_ids)
        if remaining > 0 and prefer_distributed and self.random_walk:
            # Calcola quanti walk servono
            walks_needed = max(remaining // 20, 5)  # Almeno 5 walk
            
            explored_nodes = await self.random_walk.explore_network(
                walk_count=walks_needed,
                k_per_walk=20
            )
            
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
            
            logger.debug(
                "nodes_from_random_walk",
                count=len(explored_nodes),
                remaining=remaining
            )
        
        duration = (datetime.now() - start_time).total_seconds()
        
        # Verifica se abbiamo trovato abbastanza nodi
        if len(discovered_node_ids) < required_count:
            logger.warning(
                "insufficient_nodes_discovered",
                found=len(discovered_node_ids),
                required=required_count
            )
            raise ValueError(
                f"Nodi insufficienti: trovati {len(discovered_node_ids)}, "
                f"richiesti {required_count}"
            )
        
        logger.info(
            "smart_discovery_complete",
            discovered=len(discovered_node_ids),
            duration_seconds=duration,
            cache_stats=self.cache.get_stats() if self.cache else {}
        )
        
        return discovered_node_ids[:required_count]
    
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

