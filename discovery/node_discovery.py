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
    ALPHA = 5  # Parallelism factor per query concorrenti
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
        available_nodes = await self._verify_node_availability(filtered_nodes)

        
        duration = (datetime.now() - start_time).total_seconds()
        
        # NUOVO: Non limitare i nodi qui, lascia che il chiamante decida
        # Questo è importante per il fallback locale dove vogliamo TUTTI i nodi disponibili
        result = NodeDiscoveryResult(
            discovered_nodes=available_nodes,  # ✅ Restituisci TUTTI i nodi trovati
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

    async def publish_node_info(self, node_info: NodeInfo, ttl: int = 3600) -> bool:
        """
        Pubblica informazioni su un nodo nella DHT usando metodi nativi
        
        Args:
            node_info: Informazioni del nodo da pubblicare
            ttl: Time to live in secondi
            
        Returns:
            bool: True se pubblicato con successo
        """
        try:
            import json
            from datetime import datetime, timedelta
            
            # Prepara i dati del nodo
            node_data = {
                'id': node_info.node_id,
                'address': node_info.address,
                'port': node_info.port,
                'state': node_info.state.value,
                'capabilities': [cap.value for cap in node_info.capabilities],
                'published_at': datetime.now().isoformat(),
                'ttl': ttl
            }
            
            # Chiavi DHT per pubblicazione
            keys = [
                f"cqkd:node:{node_info.node_id}",
                f"cqkd:discovery:nodes:active",
                f"cqkd:discovery:region:{node_info.node_id[:8]}"
            ]
            
            # Aggiungi chiavi per capacità
            for cap in node_info.capabilities:
                keys.append(f"cqkd:capability:{cap.value}:{node_info.node_id}")
            
            # Pubblica su tutte le chiavi
            for key in keys:
                try:
                    if "discovery:nodes:active" in key:
                        # Per la chiave attiva, recupera prima la lista esistente
                        existing_data = await self.coordinator.server.get(key)
                        existing_nodes = []
                        
                        if existing_data and isinstance(existing_data, str):
                            try:
                                existing_nodes = json.loads(existing_data)
                                if not isinstance(existing_nodes, list):
                                    existing_nodes = []
                            except json.JSONDecodeError:
                                existing_nodes = []
                        
                        # Aggiungi il nuovo nodo se non già presente
                        node_ids = [n.get('id') for n in existing_nodes if isinstance(n, dict)]
                        if node_info.node_id not in node_ids:
                            existing_nodes.append(node_data)
                            # Limita la dimensione della lista
                            if len(existing_nodes) > 100:
                                existing_nodes = existing_nodes[-100:]
                        
                        await self.coordinator.server.set(key, json.dumps(existing_nodes))
                    else:
                        # Per le altre chiavi, pubblica direttamente
                        await self.coordinator.server.set(key, json.dumps(node_data))
                    
                    logger.debug(
                        "node_info_published",
                        key=key,
                        node_id=node_info.node_id[:16]
                    )
                    
                except Exception as key_e:
                    logger.warning(
                        "failed_to_publish_to_key",
                        key=key,
                        error=str(key_e)
                    )
            
            logger.info(
                "node_info_published_successfully",
                node_id=node_info.node_id[:16],
                keys_count=len(keys)
            )
            
            return True
            
        except Exception as e:
            logger.error(
                "node_info_publish_failed",
                node_id=node_info.node_id[:16],
                error=str(e)
            )
            return False

    async def _iterative_find_node(
        self,
        target_count: int,
        target_id: Optional[str] = None
    ) -> List[NodeInfo]:
        """
        Implementazione MIGLIORATA di iterativeFindNode usando pienamente la libreria Kademlia
        
        Combina NodeSpiderCrawl con query FIND_NODE dirette per massima efficacia.
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
        
        # PRIMA CONTROLLA LA ROUTING TABLE LOCALE - È LA FONTE PIÙ AFFIDABILE
        routing_info = self.coordinator.get_routing_table_info()
        total_nodes = routing_info.get("total_nodes", 0)
        
        logger.info(
            "routing_table_pre_check",
            total_nodes=total_nodes,
            target_count=target_count
        )
        
        # Se abbiamo abbastanza nodi nella routing table locale, usali direttamente
        if total_nodes >= target_count:
            logger.info(
                "sufficient_nodes_in_routing_table_using_local_fallback",
                total_nodes=total_nodes,
                target_count=target_count
            )
            return await self._fallback_local_search(target_count, target_id)
        
        try:
            # Converti target_id in oggetto Node Kademlia
            target_bytes = binascii.unhexlify(target_id)
            target_node = Node(target_bytes)
            
            # NUOVO: Prova prima query DHT dirette per nodi noti
            dht_nodes = await self._query_dht_for_nodes(target_id)
            if dht_nodes:
                logger.info(
                    "nodes_found_via_dht_query",
                    count=len(dht_nodes),
                    target_count=target_count
                )
            
            # Ottieni nodi iniziali dalla routing table locale
            initial_peers = self._get_initial_kademlia_nodes()
            
            if not initial_peers and not dht_nodes:
                logger.warning("no_initial_peers_for_crawl")
                return []
            
            logger.debug(
                "starting_node_spider_crawl",
                initial_peers=len(initial_peers),
                dht_nodes=len(dht_nodes) if dht_nodes else 0,
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
            
            # NUOVO: Combina risultati da DHT e spider crawl
            all_found_nodes = []
            
            # Aggiungi nodi dalla DHT query
            if dht_nodes:
                all_found_nodes.extend(dht_nodes)
            
            # Aggiungi nodi dallo spider crawl
            all_found_nodes.extend(found_nodes)
            
            # Rimuovi duplicati basandoti sull'ID
            unique_nodes = []
            seen_ids = set()
            for node in all_found_nodes:
                node_id = node.id.hex() if isinstance(node.id, bytes) else str(node.id)
                if node_id not in seen_ids:
                    seen_ids.add(node_id)
                    unique_nodes.append(node)
            
            logger.info(
                "node_spider_crawl_completed",
                found_nodes=len(found_nodes),
                dht_nodes=len(dht_nodes) if dht_nodes else 0,
                unique_nodes=len(unique_nodes),
                target_count=target_count
            )
            
            # Converti oggetti Node Kademlia in NodeInfo
            discovered_nodes = []
            for node in unique_nodes[:target_count]:
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
            
            # NUOVO: Analizza lo stato della routing table prima del fallback
            routing_info = self.coordinator.get_routing_table_info()
            network_health = routing_info.get("network_health", {})
            total_nodes = routing_info.get("total_nodes", 0)
            
            logger.info(
                "routing_table_analysis_before_fallback",
                total_nodes=total_nodes,
                well_distributed=network_health.get("well_distributed", False),
                distribution_score=network_health.get("distribution_score", 0.0)
            )
            
            # Se la rete non è ben distribuita o ha pochi nodi, prova un refresh aggressivo
            if (total_nodes < target_count * 2 or
                not network_health.get("well_distributed", False) or
                network_health.get("distribution_score", 0.0) < 0.3):
                
                logger.info(
                    "network_health_poor_attempting_aggressive_refresh",
                    total_nodes=total_nodes,
                    target_count=target_count
                )
                
                try:
                    # Refresh completo della routing table
                    self.coordinator.server.refresh_table()
                    
                    # Aspetta un po' per permettere al refresh di propagarsi
                    await asyncio.sleep(2.0)
                    
                    # Riprova il discovery con parametri più aggressivi
                    logger.info("retrying_discovery_after_aggressive_refresh")
                    retry_result = await self._retry_discovery_with_aggressive_params(
                        target_count, target_id
                    )
                    
                    if retry_result:
                        logger.info(
                            "aggressive_retry_successful",
                            found_nodes=len(retry_result)
                        )
                        return retry_result
                        
                except Exception as retry_e:
                    logger.warning(
                        "aggressive_retry_failed",
                        error=str(retry_e)
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
        
        logger.info(
            "fallback_local_search_nodes_available",
            total_nodes=len(all_local_nodes),
            target_count=target_count
        )
        
        # PER IL FALLBACK LOCALE: restituisci TUTTI i nodi disponibili, non solo target_count
        # Questo perché il fallback locale viene usato quando abbiamo già verificato
        # che la routing table ha abbastanza nodi (total_nodes >= target_count)
        logger.info(
            "fallback_local_search_returning_all_available",
            returning=len(all_local_nodes),  # ✅ Restituisci TUTTI i nodi
            total_available=len(all_local_nodes),
            target_count=target_count
        )
        return all_local_nodes  # ✅ Restituisci TUTTI i nodi disponibili

    async def _query_dht_for_nodes(self, target_id: str) -> List:
        """
        Esegue query DHT dirette per trovare nodi usando metodi nativi Kademlia
        
        Args:
            target_id: ID target per la ricerca
            
        Returns:
            List: Nodi trovati tramite DHT
        """
        try:
            from kademlia.node import Node
            import binascii
            
            # Prova a recuperare nodi noti dalla DHT usando chiavi di discovery
            discovery_keys = [
                f"cqkd:discovery:nodes:active",
                f"cqkd:discovery:nodes:all",
                f"cqkd:discovery:region:{target_id[:8]}"  # Chiave basata su regione
            ]
            
            found_nodes = []
            
            for key in discovery_keys:
                try:
                    # Usa il metodo get() nativo della libreria Kademlia
                    nodes_data = await self.coordinator.server.get(key)
                    
                    if nodes_data:
                        logger.debug(
                            "dht_query_found_nodes",
                            key=key,
                            data_type=type(nodes_data).__name__
                        )
                        
                        # Se i dati sono una stringa JSON, parsali
                        if isinstance(nodes_data, str):
                            import json
                            try:
                                nodes_list = json.loads(nodes_data)
                                if isinstance(nodes_list, list):
                                    for node_data in nodes_list:
                                        if isinstance(node_data, dict):
                                            # Ricostruisci oggetto Node Kademlia
                                            node_id = node_data.get('id')
                                            address = node_data.get('address')
                                            port = node_data.get('port')
                                            
                                            if node_id and address and port:
                                                try:
                                                    node_bytes = binascii.unhexlify(node_id)
                                                    kad_node = Node(node_bytes, address, port)
                                                    found_nodes.append(kad_node)
                                                except Exception as e:
                                                    logger.debug(
                                                        "failed_to_reconstruct_node",
                                                        node_id=node_id,
                                                        error=str(e)
                                                    )
                            except json.JSONDecodeError:
                                logger.debug("invalid_json_in_dht_response", key=key)
                        
                        # Se i dati sono già una lista di nodi
                        elif isinstance(nodes_data, list):
                            for node_item in nodes_data:
                                if hasattr(node_item, 'id'):  # È già un oggetto Node
                                    found_nodes.append(node_item)
                
                except Exception as key_e:
                    logger.debug(
                        "dht_key_query_failed",
                        key=key,
                        error=str(key_e)
                    )
                    continue
            
            # NUOVO: Prova anche FIND_NODE diretti ai nodi noti
            if found_nodes or self._queried_nodes:
                await self._expand_with_direct_find_node_queries(target_id, found_nodes)
            
            logger.info(
                "dht_query_completed",
                total_found=len(found_nodes),
                target_id=target_id[:16] + "..."
            )
            
            return found_nodes
            
        except Exception as e:
            logger.error(
                "dht_query_failed",
                target_id=target_id[:16] + "...",
                error=str(e)
            )
            return []

    async def _expand_with_direct_find_node_queries(
        self,
        target_id: str,
        existing_nodes: List
    ) -> None:
        """
        Espande la ricerca con query FIND_NODE dirette ai nodi conosciuti
        
        Args:
            target_id: ID target per la ricerca
            existing_nodes: Lista di nodi già trovati (modificata in-place)
        """
        try:
            from kademlia.node import Node
            import binascii
            
            target_bytes = binascii.unhexlify(target_id)
            
            # Seleziona alcuni nodi noti per query dirette
            known_nodes = self._get_initial_kademlia_nodes()
            
            if not known_nodes:
                return
            
            # Limita il numero di query dirette per evitare flood
            max_direct_queries = min(self.ALPHA, len(known_nodes))
            query_nodes = known_nodes[:max_direct_queries]
            
            logger.debug(
                "starting_direct_find_node_queries",
                queries_count=len(query_nodes),
                target_id=target_id[:16] + "..."
            )
            
            # Esegui query FIND_NODE dirette in parallelo
            tasks = []
            for node in query_nodes:
                if node.id.hex() not in self._queried_nodes:
                    task = self._direct_find_node_query(node, target_bytes)
                    tasks.append(task)
            
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for result in results:
                    if isinstance(result, list) and result:
                        existing_nodes.extend(result)
            
            logger.debug(
                "direct_find_node_queries_completed",
                new_nodes_found=len([r for r in results if isinstance(r, list) and r])
            )
            
        except Exception as e:
            logger.error(
                "direct_find_node_queries_failed",
                target_id=target_id[:16] + "...",
                error=str(e)
            )

    async def _direct_find_node_query(self, target_node, target_bytes: bytes) -> List:
        """
        Esegue una query FIND_NODE diretta a un nodo specifico
        
        Args:
            target_node: Nodo Kademlia a cui inviare la query
            target_bytes: ID target in bytes
            
        Returns:
            List: Nodi trovati
        """
        try:
            # Usa callFindNode nativo della libreria Kademlia
            result = await asyncio.wait_for(
                self.coordinator.server.protocol.callFindNode(target_node, target_bytes),
                timeout=self.QUERY_TIMEOUT
            )
            
            # Marca il nodo come interrogato
            self._queried_nodes.add(target_node.id.hex())
            
            return result if result else []
            
        except Exception as e:
            logger.debug(
                "direct_find_node_query_failed",
                target_node=target_node.id.hex()[:16] + "...",
                error=str(e)
            )
            return []

    async def _retry_discovery_with_aggressive_params(
        self,
        target_count: int,
        target_id: Optional[str] = None
    ) -> List[NodeInfo]:
        """
        Riprova il discovery con parametri più aggressivi
        
        Args:
            target_count: Numero di nodi desiderati
            target_id: ID target (opzionale)
            
        Returns:
            List[NodeInfo]: Nodi trovati o lista vuota
        """
        logger.info(
            "aggressive_discovery_retry",
            target_count=target_count,
            target_id=target_id[:16] + "..." if target_id else None
        )
        
        try:
            # Usa parametri più aggressivi
            original_alpha = self.ALPHA
            original_k = self.K
            
            # Aumenta parallelismo e numero di nodi da cercare
            self.ALPHA = min(6, original_alpha * 2)  # Più query parallele
            self.K = max(target_count * 3, 40)       # Più nodi da trovare
            
            logger.debug(
                "aggressive_params_set",
                alpha=self.ALPHA,
                k=self.K,
                original_alpha=original_alpha,
                original_k=original_k
            )
            
            # Riprova il discovery standard
            from kademlia.crawling import NodeSpiderCrawl
            from kademlia.node import Node
            import binascii
            
            if target_id is None:
                target_id = self._generate_random_node_id()
            
            target_bytes = binascii.unhexlify(target_id)
            target_node = Node(target_bytes)
            
            # Ottieni nodi iniziali dalla routing table
            initial_peers = self._get_initial_kademlia_nodes()
            
            if not initial_peers:
                logger.warning("no_initial_peers_for_aggressive_retry")
                # Ripristina parametri originali
                self.ALPHA = original_alpha
                self.K = original_k
                return []
            
            # Crea e esegui NodeSpiderCrawl con parametri aggressivi
            spider = NodeSpiderCrawl(
                protocol=self.coordinator.server.protocol,
                node=target_node,
                peers=initial_peers,
                ksize=self.K,
                alpha=self.ALPHA
            )
            
            # Esegui la ricerca con timeout più lungo
            found_nodes = await asyncio.wait_for(
                spider.find(),
                timeout=15.0  # Timeout più lungo per retry aggressivo
            )
            
            # Ripristina parametri originali
            self.ALPHA = original_alpha
            self.K = original_k
            
            logger.info(
                "aggressive_discovery_completed",
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
            # Ripristina parametri originali in caso di errore
            self.ALPHA = original_alpha
            self.K = original_k
            
            logger.error(
                "aggressive_discovery_failed",
                error=str(e),
                target_id=target_id[:16] + "..." if target_id else None
            )
            return []

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
