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
import datetime

logger = get_logger(__name__)

class KeyGenerationOrchestrator:
    """Orchestratore per la generazione distribuita di chiavi CQKD"""

    def __init__(self, coordinator_node: CQKDNode):
        self.coordinator = coordinator_node
        self.process_id = self._generate_process_id()
        self.allocated_nodes: Dict[NodeRole, List[str]] = {}
        self._lock = asyncio.Lock()
        
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
        return f"cqkd_{secrets.token_hex(16)}"
    

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
        required_capabilities: Optional[List[NodeRole]] = None,
        max_retries: int = 2  # NUOVO: Numero di tentativi massimi
    ) -> List[str]:
        """
        Scopre nodi disponibili nella rete DHT usando strategia intelligente e robusta
        
        Questa implementazione migliorata usa:
        1. Analisi dello stato della rete con get_routing_table_info()
        2. Cache per nodi già noti (veloce)
        3. Discovery standard con retry se cache insufficiente
        4. Random walk per nodi distribuiti geograficamente
        5. Fallback aggressivo con retry multipli
        
        Args:
            required_count: Numero di nodi necessari
            required_capabilities: Capacità richieste opzionali
            max_retries: Numero massimo di tentativi di discovery
            
        Returns:
            list[str]: Lista di node_id disponibili
        """

        # AVVIO AUTOMATICO: Se è la prima chiamata, avvia background tasks
        if not self._background_tasks_started:
            await self._ensure_background_tasks_started()

        logger.info(
            "discovering_nodes_smart_with_retry",
            process_id=self.process_id,
            required_count=required_count,
            capabilities=required_capabilities,
            max_retries=max_retries
        )
        
        # NUOVO: Analisi preliminare dello stato della rete
        try:
            routing_info = self.coordinator.get_routing_table_info()
            network_health = routing_info.get("network_health", {})
            total_nodes = routing_info.get("total_nodes", 0)
            all_node_id = routing_info.get("all_nodes")
            
            logger.info(
                "pre_discovery_network_analysis",
                process_id=self.process_id,
                total_nodes=total_nodes,
                well_distributed=network_health.get("well_distributed", False),
                distribution_score=network_health.get("distribution_score", 0.0)
            )
            
            # Se la rete è in cattivo stato, aumenta i tentativi
            if (total_nodes < required_count):
                
                max_retries = max(max_retries + 1, 3)
                logger.info(
                    "poor_network_detected_increasing_retries",
                    process_id=self.process_id,
                    new_max_retries=max_retries
                )
                
        except Exception as e:
            logger.warning(
                "pre_discovery_analysis_failed",
                process_id=self.process_id,
                error=str(e)
            )
        
        # # NUOVO: Ciclo di retry con strategie diverse
        # last_exception = None
        # available_node_ids = []
        
        # for attempt in range(max_retries + 1):  # +1 per il tentativo iniziale
        #     try:
        #         logger.info(
        #             "discovery_attempt",
        #             process_id=self.process_id,
        #             attempt=attempt + 1,
        #             max_attempts=max_retries + 1,
        #             required_count=required_count
        #         )
                
        #         # Usa SmartDiscoveryStrategy con parametri adattivi
        #         available_node_ids = await self.smart_discovery.discover_nodes(
        #             required_count=required_count,
        #             required_capabilities=required_capabilities,
        #             prefer_distributed=True,  # Importante per CQKD!
        #             max_discovery_time=60 + (attempt * 30)  # Aumenta timeout per ogni retry
        #         )
                
        #         # Se abbiamo trovato abbastanza nodi, esci dal ciclo
        #         if len(available_node_ids) >= required_count:
        #             logger.info(
        #                 "discovery_successful",
        #                 process_id=self.process_id,
        #                 attempt=attempt + 1,
        #                 found_count=len(available_node_ids),
        #                 required_count=required_count
        #             )
        #             break
                    
        #     except Exception as e:
        #         last_exception = e
        #         logger.warning(
        #             "discovery_attempt_failed",
        #             process_id=self.process_id,
        #             attempt=attempt + 1,
        #             error=str(e),
        #             will_retry=(attempt < max_retries)
        #         )
                
        #         # Se non è l'ultimo tentativo, aspetta un po' prima di riprovare
        #         if attempt < max_retries:
        #             # Refresh della routing table tra i tentativi
        #             try:
        #                 logger.info(
        #                     "refreshing_routing_table_between_attempts",
        #                     process_id=self.process_id,
        #                     attempt=attempt + 1
        #                 )
        #                 self.coordinator.server.refresh_table()
        #                 await asyncio.sleep(2.0)  # Dai tempo al refresh
        #             except Exception as refresh_e:
        #                 logger.warning(
        #                     "routing_table_refresh_failed",
        #                     process_id=self.process_id,
        #                     error=str(refresh_e)
        #                 )
                    
        #             # Aspetta prima del prossimo tentativo
        #             await asyncio.sleep(3.0 + (attempt * 2))  # Backoff esponenziale
        
        # # Verifica finale dopo tutti i tentativi
        # if len(available_node_ids) < required_count:
        #     error_msg = (
        #         f"Nodi insufficienti dopo {max_retries + 1} tentativi: "
        #         f"trovati {len(available_node_ids)}, richiesti {required_count}"
        #     )
            
        #     logger.error(
        #         "discovery_failed_after_all_retries",
        #         process_id=self.process_id,
        #         found=len(available_node_ids),
        #         required=required_count,
        #         max_attempts=max_retries + 1,
        #         last_error=str(last_exception) if last_exception else None
        #     )
            
        #     # Aggiungi informazioni diagnostiche
        #     try:
        #         final_routing_info = self.coordinator.get_routing_table_info()
        #         logger.error(
        #             "final_network_state",
        #             process_id=self.process_id,
        #             routing_info=final_routing_info
        #         )
        #     except Exception as diag_e:
        #         logger.error("failed_to_get_final_network_state", error=str(diag_e))
            
        #     raise ValueError(error_msg)
        
        # logger.info(
        #     "nodes_discovered_smart_with_retry",
        #     process_id=self.process_id,
        #     found_count=len(available_node_ids),
        #     required_count=required_count,
        #     attempts_used=min(max_retries + 1, 4)  # Corretto: max 4 tentativi
        # )
        
        return all_node_id
    
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

    async def stop(self):
        """
        Stop the key generation orchestrator and background tasks.
        
        This method should be called when the orchestrator is no longer
        needed to properly clean up resources.
        """
        logger.info(
            "stopping_orchestrator",
            node_id=self.coordinator.node_id if self.coordinator else "standalone"
        )
        
        if self.smart_discovery and self._background_tasks_started:
            try:
                await self.smart_discovery.stop_background_tasks()
                self._background_tasks_started = False
                logger.info(
                    "background_tasks_stopped",
                    node_id=self.coordinator.node_id if self.coordinator else "standalone"
                )
            except Exception as e:
                logger.error(
                            "failed_to_stop_background_tasks",
                            error=str(e),
                            node_id=self.coordinator.node_id if self.coordinator else "standalone"
                        )
        
        logger.info(
            "orchestrator_stopped",
            node_id=self.coordinator.node_id if self.coordinator else "standalone"
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

        self.allocated_nodes = allocation

        logger.info(
            "nodes_allocated",
            process_id=self.process_id,
            allocation_summary={
                role.value: len(nodes)
                for role, nodes in allocation.items()
            }
        )

        return allocation

    def _calculate_reduced_requirements(
        self,
        available_nodes: int,
        original_requirements: Dict[str, int]
    ) -> Dict[str, int]:
        """
        Calcola requisiti ridotti basati sui nodi disponibili
        
        Args:
            available_nodes: Numero di nodi disponibili
            original_requirements: Requisiti originali
            
        Returns:
            Dict[str, int]: Requisiti ridotti proporzionalmente
        """
        if available_nodes <= 0:
            return original_requirements
        
        # Calcola il fattore di riduzione (conservativo)
        reduction_factor = available_nodes / original_requirements['total']
        
        # Assicura un minimo ragionevole per ogni ruolo
        min_per_role = max(1, int(original_requirements['qsg'] * 0.3))  # Almeno 30% per ruolo
        
        reduced_requirements = {}
        for role_name, original_count in original_requirements.items():
            if role_name in ['total', 'initial_key_length']:
                continue
            
            # Calcola il numero ridotto
            reduced_count = max(
                min_per_role,
                int(original_count * reduction_factor)
            )
            
            # Arrotonda per eccesso (non dovrebbe superare gli originali)
            reduced_count = min(reduced_count, original_count)
            
            reduced_requirements[role_name] = reduced_count
        
        # Ricalcola il totale
        reduced_requirements['total'] = sum(reduced_requirements.values())
        
        logger.debug(
            "requirements_reduced",
            available_nodes=available_nodes,
            original_total=original_requirements['total'],
            reduced_total=reduced_requirements['total'],
            reduction_factor=reduction_factor
        )
        
        return reduced_requirements

    async def complete_process(
        self,
        success: bool = True,
        error_message: Optional[str] = None
    ):
        """
        Mark process as completed.
        
        IMPORTANT: Keep stored data small (< 8KB for Kademlia UDP limit).
        """
        if not self.process_id:
            return
        
        status = "completed" if success else "failed"
        
        # DON'T store full allocated_nodes list - it's too big!
        # Just store summary statistics
        allocation_summary = {}
        if self.allocated_nodes:
            for role, nodes in self.allocated_nodes.items():
                allocation_summary[role.value] = {
                    "count": len(nodes),
                    # Store only first 3 node IDs for verification
                    "sample": [str(n)[:16] for n in list(nodes)[:3]] if nodes else []
                }
        
        completion_data = {
            "status": status,
            "timestamp": datetime.datetime.now().isoformat(),
            "orchestrator": self.coordinator.node_id if self.coordinator else "standalone",
            "allocation_summary": allocation_summary  # Summary instead of full list
        }
        
        if error_message:
            # Truncate error if too long
            completion_data["error"] = error_message[:500]
        
        if self.coordinator:
            try:
                await self.coordinator.store_data(
                    f"{self.process_id}:completion",
                    completion_data
                )
            except Exception as e:
                logger.error(
                    "completion_store_failed",
                    error=str(e),
                    data_size=len(str(completion_data))
                )
                # Don't fail the whole process if storing completion fails
        
        logger.info(
            "process_completed",
            process_id=self.process_id,
            status=status,
            error_message=error_message
        )

    @staticmethod
    def bits_to_bytes(bits: List[int]) -> bytes:
        """
        Converte una lista di bit in bytes

        Args:
            bits: Lista di bit (0 o 1)

        Returns:
            bytes: Rappresentazione binaria
        """
        # Crea una copia per evitare side effects
        bits_copy = bits.copy()
        
        # Pad to multiple of 8
        while len(bits_copy) % 8 != 0:
            bits_copy.append(0)
        
        byte_array = bytearray()
        for i in range(0, len(bits_copy), 8):
            byte = 0
            for j in range(8):
                byte = (byte << 1) | bits_copy[i + j]
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