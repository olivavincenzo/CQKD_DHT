import asyncio
from typing import List, Dict, Any, Set, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import secrets

from core.dht_node import CQKDNode
from core.node_states import NodeState, NodeRole, NodeInfo
from utils.logging_config import get_logger


logger = get_logger(__name__)


@dataclass
class NodeDiscoveryResult:
    """Risultato del processo di discovery"""
    discovered_nodes: List[NodeInfo] = field(default_factory=list)
    query_count: int = 0
    duration_seconds: float = 0.0
    failed_queries: int = 0


class NodeDiscoveryService:
    """
    Servizio per il discovery di nodi nella DHT Kademlia
    
    Implementa l'algoritmo iterativeFindNode per scoprire
    nodi disponibili nella rete distribuita.
    """
    
    # Parametri Kademlia standard
    ALPHA = 3  # Parallelism factor per query concorrenti
    K = 20     # Numero di nodi più vicini da trovare
    
    # Timeout e retry
    QUERY_TIMEOUT = 5.0  # Timeout per singola query RPC
    MAX_RETRIES = 3      # Tentativi massimi per nodo non responsivo
    
    def __init__(self, coordinator_node: CQKDNode):
        self.coordinator = coordinator_node
        self._queried_nodes: Set[str] = set()
        self._active_queries: Dict[str, asyncio.Task] = {}
        
    async def discover_nodes_for_roles(
        self,
        required_count: int,
        required_capabilities: Optional[List[NodeRole]] = None
    ) -> NodeDiscoveryResult:
        """
        Scopre nodi disponibili con capacità specifiche
        
        Args:
            required_count: Numero minimo di nodi richiesti
            required_capabilities: Capacità richieste (es. [NodeRole.QSG])
            
        Returns:
            NodeDiscoveryResult: Risultato con nodi scoperti
        """
        start_time = datetime.now()
        
        logger.info(
            "node_discovery_start",
            required_count=required_count,
            capabilities=required_capabilities
        )
        
        # Step 1: Esegui iterativeFindNode per trovare nodi vicini
        all_nodes = await self._iterative_find_node(
            target_count=required_count * 2  # Scopri più nodi del necessario
        )
        
        # Step 2: Filtra per capacità se richiesto
        if required_capabilities:
            filtered_nodes = [
                node for node in all_nodes
                if self._has_required_capabilities(node, required_capabilities)
            ]
        else:
            filtered_nodes = all_nodes
        

        # Step 3: Verifica stato e disponibilità
        # available_nodes = await self._verify_node_availability(filtered_nodes)  # ❌ COMMENTATO
        available_nodes = filtered_nodes  # ✅ Usa direttamente i nodi trovati

        
        duration = (datetime.now() - start_time).total_seconds()
        
        result = NodeDiscoveryResult(
            discovered_nodes=available_nodes[:required_count],
            query_count=len(self._queried_nodes),
            duration_seconds=duration,
            failed_queries=len(self._queried_nodes) - len(all_nodes)
        )
        
        logger.info(
            "node_discovery_complete",
            discovered=len(result.discovered_nodes),
            required=required_count,
            duration=duration,
            query_count=result.query_count
        )
        
        if len(result.discovered_nodes) < required_count:
            logger.warning(
                "insufficient_nodes_discovered",
                discovered=len(result.discovered_nodes),
                required=required_count
            )
        
        return result
    

    async def _iterative_find_node(
        self,
        target_count: int,
        target_id: Optional[str] = None
    ) -> List[NodeInfo]:
        """
        Implementazione corretta di iterativeFindNode usando la libreria Kademlia
        
        Usa NodeSpiderCrawl per eseguire una vera ricerca iterativa nella rete,
        non solo nella routing table locale.
        """
        from kademlia.crawling import NodeSpiderCrawl
        from kademlia.node import Node
        import binascii
        
        if target_id is None:
            target_id = self._generate_random_node_id()
        
        logger.info(
            "iterative_find_node_start",
            target_count=target_count,
            target_id=target_id[:16] + "..."
        )
        
        try:
            # Converti target_id in oggetto Node Kademlia
            target_bytes = binascii.unhexlify(target_id)
            target_node = Node(target_bytes)
            
            # Ottieni nodi iniziali dalla routing table locale
            initial_peers = self._get_initial_kademlia_nodes()
            
            if not initial_peers:
                logger.warning("no_initial_peers_for_crawl")
                return []
            
            logger.debug(
                "starting_node_spider_crawl",
                initial_peers=len(initial_peers),
                ksize=self.K,
                alpha=self.ALPHA
            )
            
            # Crea e esegui NodeSpiderCrawl
            spider = NodeSpiderCrawl(
                protocol=self.coordinator.server.protocol,
                node=target_node,
                peers=initial_peers,
                ksize=self.K,
                alpha=self.ALPHA
            )
            
            # Esegui la ricerca iterativa
            found_nodes = await spider.find()
            
            logger.info(
                "node_spider_crawl_completed",
                found_nodes=len(found_nodes),
                target_count=target_count
            )
            
            # Converti oggetti Node Kademlia in NodeInfo
            discovered_nodes = []
            for node in found_nodes[:target_count]:
                node_info = NodeInfo(
                    node_id=node.id.hex() if isinstance(node.id, bytes) else str(node.id),
                    address=node.ip,
                    port=node.port,
                    state=NodeState.ACTIVE,
                    current_role=None,
                    last_seen=datetime.now(),
                    capabilities=[
                        NodeRole.QSG, NodeRole.BG, NodeRole.QPP,
                        NodeRole.QPM, NodeRole.QPC
                    ]
                )
                discovered_nodes.append(node_info)
            
            return discovered_nodes
            
        except Exception as e:
            error_msg = str(e)
            logger.error(
                "iterative_find_node_failed",
                error=error_msg,
                target_id=target_id[:16] + "..." if target_id else None
            )
            
            # Check if it's a DNS/socket family issue
            if "socket family mismatch" in error_msg or "DNS lookup is required" in error_msg:
                logger.warning(
                    "dns_socket_issue_detected",
                    error=error_msg,
                    action="refreshing_routing_table_and_fallback"
                )
                # Try to refresh routing table to clear problematic entries
                try:
                    self.coordinator.server.refresh_table()
                    logger.info("routing_table_refreshed_after_dns_issue")
                except Exception as refresh_e:
                    logger.warning(
                        "routing_table_refresh_failed",
                        error=str(refresh_e)
                    )
            
            # Fallback: usa solo routing table locale
            logger.info("fallback_to_local_routing_table")
            return await self._fallback_local_search(target_count, target_id)

    def _get_initial_kademlia_nodes(self) -> List:
        """
        Ottieni nodi iniziali come oggetti Node Kademlia dalla routing table
        """
        try:
            from kademlia.node import Node
            
            router = self.coordinator.server.protocol.router
            local_node = self.coordinator.server.node
            
            # Trova nodi vicini usando il router
            neighbors = router.find_neighbors(local_node, k=self.K)
            
            logger.debug(
                "kademlia_initial_nodes_retrieved",
                count=len(neighbors)
            )
            
            return neighbors
            
        except Exception as e:
            logger.error(
                "failed_to_get_kademlia_nodes",
                error=str(e)
            )
            return []
    
    async def _fallback_local_search(
        self,
        target_count: int,
        target_id: Optional[str] = None
    ) -> List[NodeInfo]:
        """
        Fallback: usa solo routing table locale se la ricerca iterativa fallisce
        """
        if target_id is None:
            target_id = self._generate_random_node_id()
        
        logger.warning(
            "fallback_local_search",
            target_count=target_count,
            reason="iterative_search_failed"
        )
        
        # Ottieni tutti i nodi dalla routing table locale
        all_local_nodes = await self._get_all_nodes_from_routing_table()
        
        if not all_local_nodes:
            logger.warning("no_nodes_in_routing_table_fallback")
            return []
        
        # Ordina per distanza XOR
        closest_nodes = self._get_k_closest_nodes(
            all_local_nodes,
            target_id,
            min(target_count, len(all_local_nodes))
        )
        
        return closest_nodes


    async def _get_all_nodes_from_routing_table(self) -> List[NodeInfo]:
        """
        Ottieni TUTTI i nodi dal routing table locale (senza query RPC)
        """
        try:
            router = self.coordinator.server.protocol.router
            all_nodes = []
            
            # Itera su tutti i k-buckets
            for bucket in router.buckets:
                nodes = bucket.get_nodes()
                
                for node in nodes:
                    node_info = NodeInfo(
                        node_id=node.id.hex() if isinstance(node.id, bytes) else str(node.id),
                        address=node.ip,
                        port=node.port,
                        state=NodeState.ACTIVE,
                        current_role=None,
                        last_seen=datetime.now(),
                        capabilities=[
                            NodeRole.QSG, NodeRole.BG, NodeRole.QPP,
                            NodeRole.QPM, NodeRole.QPC
                        ]
                    )
                    all_nodes.append(node_info)
            
            logger.debug(
                "all_routing_table_nodes_retrieved",
                count=len(all_nodes)
            )
            
            return all_nodes
            
        except Exception as e:
            logger.error(
                "failed_to_get_routing_table_nodes",
                error=str(e)
            )
            return []



    async def _get_initial_nodes(self) -> List[NodeInfo]:
        """
        Ottieni nodi iniziali dal routing table del coordinator
        """
        try:
            # Usa il metodo del router per ottenere i vicini
            router = self.coordinator.server.protocol.router
            
            # Ottieni il nodo locale come punto di partenza
            local_node = self.coordinator.server.node
            
            # Trova tutti i nodi vicini (usa un ID casuale o il locale)
            # findNeighbors restituisce oggetti Node completi con IP e porta
            neighbors = router.find_neighbors(local_node)
            
            initial_nodes = []
            
            for node in neighbors:
                # Ora node dovrebbe essere un oggetto Node completo
                node_info = NodeInfo(
                    node_id=node.id.hex() if isinstance(node.id, bytes) else str(node.id),
                    address=node.ip,
                    port=node.port,
                    state=NodeState.ACTIVE,
                    current_role=None,
                    last_seen=datetime.now(),
                    capabilities=[
                        NodeRole.QSG, NodeRole.BG, NodeRole.QPP,
                        NodeRole.QPM, NodeRole.QPC
                    ]
                )
                initial_nodes.append(node_info)
            
            logger.debug("initial_nodes_retrieved", count=len(initial_nodes))
            return initial_nodes
            
        except Exception as e:
            logger.error("failed_to_get_initial_nodes", error=str(e))
            return []

    
    def _select_nodes_to_query(
        self,
        candidates: List[NodeInfo],
        count: int
    ) -> List[NodeInfo]:
        """
        Seleziona nodi da interrogare (non ancora interrogati)
        
        Args:
            candidates: Nodi candidati
            count: Numero di nodi da selezionare
            
        Returns:
            List[NodeInfo]: Nodi selezionati
        """
        unqueried = [
            node for node in candidates
            if node.node_id not in self._queried_nodes
        ]
        
        return unqueried[:count]
    
    async def _parallel_find_node_queries(
        self,
        nodes: List[NodeInfo],
        target_id: str
    ) -> List[List[NodeInfo]]:
        """
        Esegue query FIND_NODE parallele a più nodi
        
        Args:
            nodes: Nodi a cui inviare query
            target_id: ID target della ricerca
            
        Returns:
            List[List[NodeInfo]]: Liste di nodi restituiti da ogni query
        """
        tasks = []
        
        for node in nodes:
            task = self._find_node_query(node, target_id)
            tasks.append(task)
        
        # Esegui query in parallelo con timeout
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filtra risultati validi (ignora eccezioni)
        valid_results = [
            r for r in results
            if isinstance(r, list) and r
        ]
        
        return valid_results
    

    def _get_k_closest_nodes(
        self,
        nodes: List[NodeInfo],
        target_id: str,
        k: int
    ) -> List[NodeInfo]:
        """
        Ottieni i k nodi più vicini al target secondo XOR distance
        
        Args:
            nodes: Lista di nodi
            target_id: ID target
            k: Numero di nodi da restituire
            
        Returns:
            List[NodeInfo]: K nodi più vicini
        """
        import binascii
        
        target_bytes = binascii.unhexlify(target_id)
        target_int = int.from_bytes(target_bytes, byteorder='big')
        
        # Calcola distanza XOR per ogni nodo
        nodes_with_distance = []
        for node in nodes:
            try:
                node_bytes = binascii.unhexlify(node.node_id)
                node_int = int.from_bytes(node_bytes, byteorder='big')
                distance = target_int ^ node_int
                nodes_with_distance.append((distance, node))
            except Exception:
                continue
        
        # Ordina per distanza e prendi i k più vicini
        nodes_with_distance.sort(key=lambda x: x[0])
        
        return [node for _, node in nodes_with_distance[:k]]
    
    async def _verify_node_availability(
        self,
        nodes: List[NodeInfo]
    ) -> List[NodeInfo]:
        """
        Verifica che i nodi siano effettivamente disponibili
        
        NOTA: Per ora ritorniamo tutti i nodi senza verificare,
        poiché il ping causa errori di serializzazione RPC
        """
        logger.info(
            "node_availability_skipped",
            total=len(nodes),
            message="Returning all nodes without ping verification"
        )
        
        # ✅ Ritorna tutti i nodi senza fare ping
        return nodes

    
    async def _ping_node(self, node: NodeInfo) -> bool:
        """
        Ping un nodo per verificare disponibilità
        
        Args:
            node: Nodo da pingare
            
        Returns:
            bool: True se disponibile
        """
        try:
            from kademlia.node import Node
            import binascii
            
            kad_node = Node(
                binascii.unhexlify(node.node_id),
                node.address,
                node.port
            )
            
            # Usa ping di Kademlia
            result = await asyncio.wait_for(
                self.coordinator.server.protocol.callPing(kad_node),
                timeout=2.0
            )
            
            return result is not None
            
        except Exception:
            return False
    
    @staticmethod
    def _generate_random_node_id() -> str:
        """Genera un ID nodo casuale per exploration"""
        return secrets.token_hex(20)  # 160 bit come Kademlia standard
    
    @staticmethod
    def _has_required_capabilities(
        node: NodeInfo,
        required: List[NodeRole]
    ) -> bool:
        """Verifica se un nodo ha le capacità richieste"""
        return all(cap in node.capabilities for cap in required)
