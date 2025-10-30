import asyncio
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
        self.server = Server(ksize=100)
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
        return f"node_{secrets.token_hex(8)}"
    
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
            
            await self.server.bootstrap(bootstrap_nodes)
            
            # Aspetta che il routing table sia popolato
            max_attempts = 20  # 10 secondi totali
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
                
                # Aspetta un po' prima di riprovare
                await asyncio.sleep(0.5)
            
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
        """Memorizza dati nella DHT"""
        try:
            await self.server.set(key, value)
            logger.debug("data_stored", node_id=self.node_id, key=key)
        except Exception as e:
            logger.error(
                "data_store_failed",
                node_id=self.node_id,
                key=key,
                error=str(e)
            )
            raise
        
    async def retrieve_data(self, key: str) -> Optional[Any]:
        """Recupera dati dalla DHT"""
        try:
            value = await self.server.get(key)
            logger.debug(
                "data_retrieved",
                node_id=self.node_id,
                key=key,
                found=value is not None
            )
            return value
        except Exception as e:
            logger.error(
                "data_retrieve_failed",
                node_id=self.node_id,
                key=key,
                error=str(e)
            )
            return None
            
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
                "buckets_detail": [],
                "all_nodes": []
            }
            
            for i, bucket in enumerate(router.buckets):
                nodes = bucket.get_nodes()
                if len(nodes) > 0:
                    info["active_buckets"] += 1
                    info["total_nodes"] += len(nodes)
                    
                    bucket_info = {
                        "bucket_index": i,
                        "node_count": len(nodes),
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