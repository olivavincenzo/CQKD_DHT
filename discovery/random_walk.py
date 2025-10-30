import asyncio
import secrets
from typing import List, Set
from datetime import datetime

from core.dht_node import CQKDNode
from core.node_states import NodeInfo
from discovery.node_discovery import NodeDiscoveryService
from utils.logging_config import get_logger


logger = get_logger(__name__)


class RandomWalkExplorer:
    """
    Esplora la DHT con random walk per scoprire nodi diversificati
    
    Utilizzato per CQKD per garantire distribuzione geografica
    e ridurre rischio di clustering dei nodi.
    """
    
    def __init__(self, coordinator_node: CQKDNode):
        self.coordinator = coordinator_node
        self.discovery = NodeDiscoveryService(coordinator_node)
        self._explored_regions: Set[str] = set()
    
    async def explore_network(
        self,
        walk_count: int = 10,
        k_per_walk: int = 20
    ) -> List[NodeInfo]:
        """
        Esegue random walk sulla DHT per scoprire nodi distribuiti
        
        Args:
            walk_count: Numero di walk da eseguire
            k_per_walk: Nodi da trovare per ogni walk
            
        Returns:
            List[NodeInfo]: Nodi scoperti (diversificati)
        """
        start_time = datetime.now()
        
        logger.info(
            "random_walk_exploration_start",
            walk_count=walk_count,
            k_per_walk=k_per_walk
        )
        
        # Esegui walk in parallelo per velocità
        tasks = []
        for i in range(walk_count):
            task = self._single_random_walk(i, k_per_walk)
            tasks.append(task)
        
        walk_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combina risultati e rimuovi duplicati
        discovered_nodes = {}
        for result in walk_results:
            if isinstance(result, list):
                for node in result:
                    discovered_nodes[node.node_id] = node
        
        duration = (datetime.now() - start_time).total_seconds()
        
        logger.info(
            "random_walk_exploration_complete",
            walks_completed=len([r for r in walk_results if isinstance(r, list)]),
            unique_nodes_discovered=len(discovered_nodes),
            duration_seconds=duration
        )
        
        return list(discovered_nodes.values())
    
    async def _single_random_walk(
        self,
        walk_id: int,
        k: int
    ) -> List[NodeInfo]:
        """
        Esegue un singolo random walk
        
        Args:
            walk_id: ID del walk (per logging)
            k: Numero di nodi da trovare
            
        Returns:
            List[NodeInfo]: Nodi scoperti in questo walk
        """
        # Genera ID casuale come target
        random_target_id = self._generate_random_target()
        
        # Memorizza regione esplorata (primi 32 bit)
        region = random_target_id[:8]
        self._explored_regions.add(region)
        
        logger.debug(
            "random_walk_start",
            walk_id=walk_id,
            target_region=region
        )
        
        try:
            # Usa iterativeFindNode verso target casuale
            nodes = await self.discovery._iterative_find_node(
                target_count=k,
                target_id=random_target_id
            )
            
            logger.debug(
                "random_walk_complete",
                walk_id=walk_id,
                nodes_found=len(nodes)
            )
            
            return nodes
            
        except Exception as e:
            logger.error(
                "random_walk_failed",
                walk_id=walk_id,
                error=str(e)
            )
            return []
    
    def _generate_random_target(self) -> str:
        """
        Genera ID target casuale per il walk
        
        Usa CSPRNG per garantire distribuzione uniforme
        sullo spazio ID Kademlia (160 bit)
        """
        return secrets.token_hex(20)  # 20 bytes = 160 bit
    
    def get_explored_regions(self) -> Set[str]:
        """Ottieni regioni DHT già esplorate"""
        return self._explored_regions.copy()
    
    def get_coverage_percentage(self) -> float:
        """
        Stima percentuale di copertura della DHT
        
        Returns:
            float: Percentuale approssimativa (0.0 - 1.0)
        """
        # 160 bit ID space diviso in regioni di 32 bit
        # = 2^32 regioni possibili
        total_regions = 2**32
        explored = len(self._explored_regions)
        
        return min(explored / total_regions, 1.0)
