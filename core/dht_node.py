import asyncio
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from kademlia.network import Server
import secrets

from config import settings
from core.node_states import (
    NodeState, NodeRole, NodeRoleAssignment, NodeInfo
)
from core.message_protocol import (
    CQKDMessage, MessageType, RoleRequestMessage
)
from utils.logging_config import get_logger


logger = get_logger(__name__)


class CQKDNode:
    """Nodo DHT per il protocollo CQKD"""

    def __init__(
        self,
        port: int,
        node_id: Optional[str] = None,
        capabilities: Optional[List[NodeRole]] = None
    ):
        self.port = port
        self.node_id = node_id or self._generate_node_id()
        # Configurazione ottimizzata per alte scalabilità
        self.server = Server(ksize=settings.dht_ksize)  # Usa configurazione da settings
        self.state = NodeState.OFF
        self.current_role: Optional[NodeRoleAssignment] = None
        self.capabilities = capabilities or [
            NodeRole.QSG, NodeRole.BG, NodeRole.QPP,
            NodeRole.QPM, NodeRole.QPC
        ]
        self._message_handlers = {}
        self._operation_results: Dict[str, Any] = {}
        self._lock = asyncio.Lock()

        logger.info(
            "node_initialized",
            node_id=self.node_id,
            port=self.port,
            capabilities=[r.value for r in self.capabilities]
        )

    @staticmethod
    def _generate_node_id() -> str:
        """Genera un ID univoco per il nodo"""
        return f"node_{secrets.token_hex(20)}"
    
    async def _resolve_bootstrap_nodes(self, bootstrap_nodes: List[tuple]) -> List[tuple]:
        """
        Risolve hostnames in indirizzi IP per evitare socket family mismatch
        
        Args:
            bootstrap_nodes: Lista di (hostname, port) tuples
            
        Returns:
            List[tuple]: Lista di (ip_address, port) tuples
        """
        import socket
        
        resolved_nodes = []
        for host, port in bootstrap_nodes:
            try:
                # Try to resolve hostname to IP address
                ip_address = socket.gethostbyname(host)
                resolved_nodes.append((ip_address, port))
                logger.info(
                    "bootstrap_node_resolved",
                    node_id=self.node_id,
                    original=f"{host}:{port}",
                    resolved=f"{ip_address}:{port}"
                )
            except socket.gaierror as e:
                logger.error(
                    "bootstrap_resolution_failed",
                    node_id=self.node_id,
                    host=host,
                    port=port,
                    error=str(e)
                )
                # If resolution fails, keep original (might be already an IP)
                resolved_nodes.append((host, port))
        
        return resolved_nodes
    
    async def start(self):
        """Avvia il nodo DHT"""
        try:
            await self.server.listen(self.port)
            self.state = NodeState.ACTIVE
            logger.info("node_started", node_id=self.node_id, port=self.port)
        except Exception as e:
            self.state = NodeState.ERROR
            logger.error(
                "node_start_failed",
                node_id=self.node_id,
                error=str(e)
            )
            raise

    async def bootstrap(self, bootstrap_nodes: List[tuple]):
        """Bootstrap del nodo alla rete DHT"""
        if not bootstrap_nodes:
            logger.warning("no_bootstrap_nodes", node_id=self.node_id)
            return
        try:
            print(f"[{self.node_id}] Inizio bootstrap verso {bootstrap_nodes}...")
            
            # Resolve hostnames to IP addresses to avoid socket family mismatch issues
            resolved_nodes = await self._resolve_bootstrap_nodes(bootstrap_nodes)
            print(f"[{self.node_id}] Nodi risolti: {resolved_nodes}")
            
            await self.server.bootstrap(resolved_nodes)
            
            # Aspetta che il routing table sia popolato
            max_attempts = 120  # 60 secondi totali per reti molto grandi
            for attempt in range(max_attempts):
                # Controlla se ci sono nodi nel routing table
                router = self.server.protocol.router
                
                # Conta nodi per bucket
                nodes_per_bucket = []
                total_nodes = 0
                for i, bucket in enumerate(router.buckets):
                    bucket_nodes = bucket.get_nodes()
                    nodes_count = len(bucket_nodes)
                    if nodes_count > 0:
                        nodes_per_bucket.append(f"bucket_{i}: {nodes_count}")
                    total_nodes += nodes_count
                
                # Stampa progresso
                if attempt == 0 or total_nodes > 0:
                    print(f"[{self.node_id}] Tentativo {attempt + 1}/{max_attempts}: "
                        f"{total_nodes} nodi in routing table")
                    
                    if nodes_per_bucket:
                        print(f"  └─ Distribuzione: {', '.join(nodes_per_bucket)}")
                
                if total_nodes > 0:
                    # Routing table popolata!
                    print(f"✓ [{self.node_id}] Bootstrap completato con successo!")
                    print(f"  └─ Routing table: {total_nodes} nodi totali in {len([b for b in router.buckets if len(b.get_nodes()) > 0])} bucket attivi")
                    
                    logger.info(
                        "node_bootstrapped",
                        node_id=self.node_id,
                        bootstrap_nodes=bootstrap_nodes,
                        routing_table_size=total_nodes,
                        active_buckets=len([b for b in router.buckets if len(b.get_nodes()) > 0]),
                        attempts=attempt + 1
                    )
                    return
                
                # Aspetta un po' prima di riprovare (aumento per reti grandi)
                await asyncio.sleep(1.0)  # 1 secondo per dare tempo alla rete
            
            # Timeout raggiunto senza nodi
            print(f"⚠ [{self.node_id}] Bootstrap timeout: routing table ancora vuota dopo {max_attempts} tentativi")
            logger.warning(
                "bootstrap_completed_empty_routing_table",
                node_id=self.node_id,
                bootstrap_nodes=bootstrap_nodes
            )
            
        except Exception as e:
            print(f"✗ [{self.node_id}] Errore durante bootstrap: {e}")
            logger.error(
                "bootstrap_failed",
                node_id=self.node_id,
                error=str(e)
            )
            raise

    async def request_role(
        self,
        role: NodeRole,
        process_id: str,
        timeout_seconds: int = 300
    ) -> bool:
        """Richiedi un ruolo quantistico per questo nodo"""
        async with self._lock:
            if self.state != NodeState.ACTIVE:
                logger.warning(
                    "role_request_denied_state",
                    node_id=self.node_id,
                    state=self.state.value
                )
                return False

            if role not in self.capabilities:
                logger.warning(
                    "role_request_denied_capability",
                    node_id=self.node_id,
                    role=role.value
                )
                return False

            if self.current_role and not self.current_role.is_expired():
                logger.warning(
                    "role_request_denied_busy",
                    node_id=self.node_id,
                    current_role=self.current_role.role.value
                )
                return False

            # Assegna il ruolo
            self.current_role = NodeRoleAssignment(
                role=role,
                process_id=process_id,
                assigned_at=datetime.now(),
                expires_at=datetime.now() + timedelta(seconds=timeout_seconds),
                metadata={}
            )
            self.state = NodeState.BUSY

            logger.info(
                "role_assigned",
                node_id=self.node_id,
                role=role.value,
                process_id=process_id
            )
            return True
        
    async def release_role(self):
        """Rilascia il ruolo corrente"""
        async with self._lock:
            if self.current_role:
                logger.info(
                    "role_released",
                    node_id=self.node_id,
                    role=self.current_role.role.value,
                    process_id=self.current_role.process_id
                )
                self.current_role = None

            self.state = NodeState.ACTIVE

    async def store_data(self, key: str, value: Any):
        """Memorizza dati nella DHT, serializzando se necessario."""
        try:
            # Se il valore è un dizionario o una lista, serializzalo in JSON
            if isinstance(value, (dict, list)):
                value_to_store = json.dumps(value)
            else:
                value_to_store = value

            await self.server.set(key, value_to_store)
            logger.debug("data_stored", node_id=self.node_id, key=key)
            
        except ValueError as e:
            if "socket family mismatch" in str(e) or "DNS lookup is required" in str(e):
                logger.warning("dns_hostname_issue_detected", node_id=self.node_id, issue=str(e))
                try:
                    self.server.refresh_table()
                    logger.info("routing_table_refresh_completed", node_id=self.node_id)
                    await self.server.set(key, value_to_store)
                    logger.info("data_stored_after_refresh", node_id=self.node_id, key=key)
                except Exception as retry_e:
                    logger.error(
                        "data_store_failed_after_retry",
                        node_id=self.node_id,
                        key=key,
                        error=str(retry_e)
                    )
                    raise
            else:
                logger.error(
                    "data_store_failed",
                    node_id=self.node_id,
                    key=key,
                    error=str(e)
                )
                raise
        except Exception as e:
            logger.error(
                "data_store_failed",
                node_id=self.node_id,
                key=key,
                error=str(e)
            )
            raise
        
    async def retrieve_data(self, key: str) -> Optional[Any]:
        """Recupera dati dalla DHT, deserializzando se necessario."""
        try:
            value = await self.server.get(key)
            logger.debug(
                "data_retrieved",
                node_id=self.node_id,
                key=key,
                found=value is not None
            )

            if isinstance(value, str):
                try:
                    # Prova a deserializzare da JSON
                    return json.loads(value)
                except json.JSONDecodeError:
                    # Se non è JSON valido, ritorna la stringa originale
                    return value
            
            return value

        except Exception as e:
            logger.error(
                "data_retrieve_failed",
                node_id=self.node_id,
                key=key,
                error=str(e)
            )
            return None

    async def delete_data(self, key: str):
        """Rimuove una chiave dalla DHT impostando il suo valore a None."""
        try:
            # In Kademlia, non c'è un 'delete' esplicito.
            # Impostare il valore a None o a un marcatore con scadenza
            # è l'approccio comune. Qui sovrascriviamo con None.
            await self.server.set(key, "__DELETED__")
            logger.debug("data_deleted", node_id=self.node_id, key=key)
        except Exception as e:
            logger.error(
                "data_delete_failed",
                node_id=self.node_id,
                key=key,
                error=str(e)
            )
            # Non rilanciamo l'eccezione per non interrompere il flusso principale
            
    async def stop(self):
        """Ferma il nodo DHT"""
        await self.release_role()
        self.server.stop()
        self.state = NodeState.OFF
        logger.info("node_stopped", node_id=self.node_id)


    def get_routing_table_info(self) -> Dict[str, Any]:
        """
        Ottieni informazioni dettagliate sulla routing table

        Returns:
            Dict con statistiche e dettagli nodi
        """
        try:
            router = self.server.protocol.router

            info = {
                "total_nodes": 0,
                "active_buckets": 0,
                "total_buckets": len(router.buckets),
                "bucket_capacity": self.server.ksize,
                "buckets_detail": [],
                "all_nodes": [],
                "bucket_distribution": {},  # Nuovo: distribuzione nodi per bucket
                "network_health": {
                    "well_distributed": False,
                    "single_bucket_overload": False,
                    "distribution_score": 0.0
                }
            }

            nodes_per_bucket = []

            for i, bucket in enumerate(router.buckets):
                nodes = bucket.get_nodes()
                nodes_count = len(nodes)

                if nodes_count > 0:
                    info["active_buckets"] += 1
                    info["total_nodes"] += nodes_count
                    nodes_per_bucket.append(nodes_count)

                    bucket_info = {
                        "bucket_index": i,
                        "node_count": nodes_count,
                        "capacity_usage": nodes_count / self.server.ksize,
                        "nodes": []
                    }

                    for node in nodes:
                        node_data = {
                            "id": node.id.hex()[:16] + "...",
                            "address": f"{node.ip}:{node.port}"
                        }
                        bucket_info["nodes"].append(node_data)
                        info["all_nodes"].append(node_data)

                    info["buckets_detail"].append(bucket_info)
                    info["bucket_distribution"][i] = nodes_count

            # Calcola metriche di salute della rete
            if nodes_per_bucket:
                max_nodes = max(nodes_per_bucket)
                avg_nodes = sum(nodes_per_bucket) / len(nodes_per_bucket)

                # Bucket overload detection
                info["network_health"]["single_bucket_overload"] = max_nodes > self.server.ksize * 0.8

                # Distribution score (0-1, 1 = perfetto)
                if max_nodes > 0:
                    variance = sum((x - avg_nodes) ** 2 for x in nodes_per_bucket) / len(nodes_per_bucket)
                    info["network_health"]["distribution_score"] = max(0, 1 - (variance / (max_nodes ** 2)))

                # Well distributed se abbiamo bucket in più intervalli e nessuno sovraccarico
                info["network_health"]["well_distributed"] = (
                    len(nodes_per_bucket) >= 3 and  # Almeno 3 bucket attivi
                    not info["network_health"]["single_bucket_overload"] and
                    info["network_health"]["distribution_score"] > 0.5
                )

            return info
        except Exception as e:
            logger.error("failed_to_get_routing_table_info", error=str(e))
            return {"error": str(e)}


    def get_info(self) -> NodeInfo:
        """Ottieni informazioni sul nodo"""
        return NodeInfo(
            node_id=self.node_id,
            address="127.0.0.1",  # TODO: detect real address
            port=self.port,
            state=self.state,
            current_role=self.current_role,
            last_seen=datetime.now(),
            capabilities=self.capabilities
        )