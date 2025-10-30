import asyncio
import secrets
from typing import List, Dict, Any, Tuple, Optional
from core.dht_node import CQKDNode
from core.node_states import NodeRole
from config import settings
from utils.logging_config import get_logger
from discovery.discovery_strategies import SmartDiscoveryStrategy
import os
import math

logger = get_logger(__name__)

class KeyGenerationOrchestrator:
    """Orchestratore per la generazione distribuita di chiavi CQKD"""

    def __init__(self, coordinator_node: CQKDNode):
        self.coordinator = coordinator_node
        self.process_id = self._generate_process_id()

        self.smart_discovery = SmartDiscoveryStrategy(
            coordinator_node,
            enable_cache=True,
            enable_random_walk=True
        )

        # Flag per gestione automatica background tasks
        self._background_tasks_started = False

    @staticmethod
    def _generate_process_id() -> str:
        """Genera un ID univoco per il processo di generazione chiave"""
        return os.getenv("SESSION_ID", "default_session")
        #return f"cqkd_{secrets.token_hex(16)}"
    

    def calculate_required_nodes(self, desired_key_length: int) -> Dict[str, int]:
        """
        Calcola il numero di nodi necessari

        Args:
            desired_key_length: Lunghezza chiave desiderata in bit

        Returns:
            dict: Numero di nodi per ogni ruolo
        """
        # lk = 2.5 * lc (lunghezza chiave iniziale)
        lk = math.ceil(settings.key_length_multiplier * desired_key_length)

        # Protocollo ottimizzato: 5lk nodi totali
        return {
            "qsg": lk,
            "bg": lk,
            "qpp": lk,
            "qpm": lk,
            "qpc": lk,
            "total": 5 * lk,
            "initial_key_length": lk
        }
    
    async def discover_available_nodes(
        self,
        required_count: int,
        required_capabilities: Optional[List[NodeRole]] = None
    ) -> List[str]:
        """
        Scopre nodi disponibili nella rete DHT usando strategia intelligente
        
        Questa implementazione usa:
        1. Cache per nodi già noti (veloce)
        2. Discovery standard se cache insufficiente
        3. Random walk per nodi distribuiti geograficamente
        
        Args:
            required_count: Numero di nodi necessari
            required_capabilities: Capacità richieste opzionali
            
        Returns:
            list[str]: Lista di node_id disponibili
        """

        # AVVIO AUTOMATICO: Se è la prima chiamata, avvia background tasks
        if not self._background_tasks_started:
            await self._ensure_background_tasks_started()

        logger.info(
            "discovering_nodes_smart",
            process_id=self.process_id,
            required_count=required_count,
            capabilities=required_capabilities
        )
        
        # Usa SmartDiscoveryStrategy (con cache + random walk)
        available_node_ids = await self.smart_discovery.discover_nodes(
            required_count=required_count,
            required_capabilities=required_capabilities,
            prefer_distributed=True  # Importante per CQKD!
        )
        
        logger.info(
            "nodes_discovered_smart",
            process_id=self.process_id,
            found_count=len(available_node_ids)
        )
        
        return available_node_ids
    
    async def _ensure_background_tasks_started(self):
        """
        Avvia background tasks se non già avviati
        
        Chiamato automaticamente alla prima discover_available_nodes,
        quindi trasparente per Alice e Bob.
        """
        if not self._background_tasks_started:
            try:
                await self.smart_discovery.start_background_tasks()
                self._background_tasks_started = True
                logger.info(
                    "orchestrator_background_tasks_auto_started",
                    process_id=self.process_id
                )
            except Exception as e:
                logger.warning(
                    "failed_to_start_background_tasks",
                    error=str(e),
                    note="Continuing without background refresh"
                )

    
    async def allocate_nodes(
        self,
        available_nodes: List[str],
        requirements: Dict[str, int]
    ) -> Dict[NodeRole, List[str]]:
        """
        Alloca nodi ai ruoli quantistici

        Args:
            available_nodes: Lista di nodi disponibili
            requirements: Requisiti per ogni ruolo

        Returns:
            dict: Mapping ruolo -> lista node_id
        """
        if len(available_nodes) < requirements['total']:
            raise ValueError(
                f"Nodi insufficienti: richiesti {requirements['total']}, "
                f"disponibili {len(available_nodes)}"
            )

        allocation = {}
        idx = 0

        for role_name, count in requirements.items():
            if role_name in ['total', 'initial_key_length']:
                continue

            role = NodeRole[role_name.upper()]
            allocation[role] = available_nodes[idx:idx + count]
            idx += count

        logger.info(
            "nodes_allocated",
            process_id=self.process_id,
            allocation_summary={
                role.value: len(nodes)
                for role, nodes in allocation.items()
            }
        )

        return allocation
    
    @staticmethod
    def bits_to_bytes(bits: List[int]) -> bytes:
        """
        Converte una lista di bit in bytes

        Args:
            bits: Lista di bit (0 o 1)

        Returns:
            bytes: Rappresentazione binaria
        """
        # Pad to multiple of 8
        while len(bits) % 8 != 0:
            bits.append(0)

        byte_array = bytearray()
        for i in range(0, len(bits), 8):
            byte = 0
            for j in range(8):
                byte = (byte << 1) | bits[i + j]
            byte_array.append(byte)

        return bytes(byte_array)
    

    @staticmethod
    def bytes_to_bits(data: bytes) -> List[int]:
        """
        Converte bytes in lista di bit

        Args:
            data: Dati binari

        Returns:
            list[int]: Lista di bit
        """
        bits = []
        for byte in data:
            for i in range(7, -1, -1):
                bits.append((byte >> i) & 1)
        return bits
    
    async def cleanup(self):
        """
        Cleanup opzionale per fermare background tasks
        
        Può essere chiamato da Alice alla fine se vuoi cleanup esplicito,
        ma NON è obbligatorio. I task verranno fermati automaticamente
        quando il processo termina.
        """
        if self._background_tasks_started:
            await self.smart_discovery.stop_background_tasks()
            self._background_tasks_started = False
            logger.info(
                "orchestrator_cleanup_executed",
                process_id=self.process_id
            )