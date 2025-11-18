import asyncio
import json
from typing import List, Dict, Any

from core.dht_node import CQKDNode
from core.node_states import NodeRole
from utils.logging_config import get_logger
import datetime

logger = get_logger(__name__)

class Bob:
    """
    Bob - Ricevente nel protocollo CQKD
    Segue STEP 12-19 del paper (Sezione 4)
    
    IMPORTANTE: Bob conosce SOLO:
    - BG_nodes (per generare le sue basi)
    - La DHT (per leggere i dati)
    
    Bob NON conosce: QPM, QPP, QSG, QPC
    """
    
    def __init__(self, node: CQKDNode):
        self.node = node
        self.bob_bases: List[str] = []
        self.bob_bits: List[int] = []
        self.process_id: str = None
    
    async def receive_key(self, process_id: str) -> bytes:
        """
        Bob riceve e genera chiave seguendo STEP 12-19
        
        Args:
            process_id: ID del processo (Alice lo comunica)
            
        Returns:
            bytes: Chiave generata
        """
        try:
            logger.info("bob_waiting_for_alice_notification", process_id=process_id)
            self.process_id = process_id
            
            # ========== STEP 12: Bob attende notifica da Alice ==========
            notification = await self._wait_for_alice_notification(process_id)
            
            lk = notification['lk']
            lc = notification.get('lc')
            sorting_rule = notification["sorting_rule"]
            bg_nodes = notification.get("bg_nodes", [])
            
            logger.info(
                "step_12_notification_received",
                process_id=process_id,
                lc=lc,
                lk=lk
            )
            
            # ========== STEP 13-14: Bob ping nodi e verifica disponibilità ==========
            # (Semplificato: assumiamo nodi già disponibili)
            logger.info("step_13_14_nodes_available")
            
            # ========== STEP 15: Bob comanda nodi BG_B per generare le sue basi ==========
            await self._dispatch_base_generation(lk, bg_nodes)
            logger.info("step_15_base_generation_dispatched")
            
            # ========== STEP 15 (continuazione): Raccogli basi da BG_B ==========
            logger.info("step_15_collecting_bob_bases", lk=lk)
            self.bob_bases = await self._collect_bob_bases(lk)
            logger.info("step_15_bob_bases_collected", count=len(self.bob_bases))
            
            # ========== STEP 16-17: QPM esegue misurazioni ==========
            # Alice ha già comandato QPM in Step 8
            # QPM legge automaticamente da QPP e BG_B dalla DHT
            # Bob non sa e non deve sapere dei dettagli di QPM
            
            logger.info("bob_waiting_for_qpm_measurements", lk=lk)
            
            # Raccogli bit misurati da DHT
            # (sono stati memorizzati da QPM, ma Bob non sa né dove né come)
            self.bob_bits = await self._collect_measurements(lk)
            logger.info(
                "step_16_17_measurements_complete",
                measurements=len(self.bob_bits)
            )
            
            # ========== STEP 18: QPC esegue collision ==========
            # QPC è stato configurato da Alice
            # Bob aspetta che QPC memorizzi i risultati nella DHT
            
            valid_positions = await self._wait_for_qpc_sifting()
            logger.info(
                "step_18_qpc_sifting_received",
                valid_positions=len(valid_positions),
                sift_ratio=len(valid_positions) / lk if lk > 0 else 0
            )
            
            # ========== STEP 19: Bob estrae la chiave finale ==========
            sifted_bits = [
                self.bob_bits[i] for i in valid_positions
                if i < len(self.bob_bits)
            ]
            
            if len(sifted_bits) < lc:
                logger.warning(
                    "insufficient_bits_after_sifting",
                    required=lc,
                    available=len(sifted_bits)
                )
                final_key_bits = sifted_bits
            else:
                final_key_bits = sifted_bits[:lc]
            
            from protocol.key_generation import KeyGenerationOrchestrator
            key_bytes = KeyGenerationOrchestrator.bits_to_bytes(final_key_bits)
            
            logger.info(
                "step_19_final_key_extracted",
                key_bits=len(final_key_bits),
                key_bytes=len(key_bytes)
            )
            
            logger.info(
                "bob_19step_protocol_complete",
                process_id=self.process_id,
                key_length=len(key_bytes)
            )
            
            return key_bytes
            
        except Exception as e:
            logger.error(
                "bob_protocol_failed",
                error=str(e),
                process_id=self.process_id,
                exc_info=True
            )
            raise
    
    async def _wait_for_alice_notification(self, process_id: str) -> Dict[str, Any]:
        """
        STEP 12: Bob attende notifica da Alice.
        
        Riceve SOLO:
        - lk, lc: lunghezze
        - sorting_rule: ordine casuale di Alice
        - bg_nodes: nodi BG per generare le sue basi
        
        NON riceve: qpm_nodes, qpp, qsg (Bob non ha bisogno di sapere)
        """
        key = f"{process_id}:alice_to_bob"
        
        for attempt in range(60):
            notification_data = await self.node.retrieve_data(key)
            if notification_data:
                if isinstance(notification_data, dict):
                    notification = notification_data
                else:
                    notification = json.loads(notification_data)
                
                logger.info("alice_notification_received", lk=notification.get('lk'))
                return notification
            
            await asyncio.sleep(0.5)
        
        raise TimeoutError("Timeout waiting for Alice notification")
    
    async def _dispatch_base_generation(self, lk: int, bg_nodes: List[Dict[str, Any]]):
        """
        STEP 15: Bob comanda nodi BG_B per generare le sue basi.
        
        ✅ Bob conosce SOLO BG_nodes
        ✅ Bob NON conosce QPM - la comunicazione con QPM avviene via DHT
        """
        logger.info("step_15_dispatching_base_generation", lk=lk)
        
        if not bg_nodes:
            raise ValueError("BG nodes not provided in Alice notification")
        
        dispatch_tasks = []
        
        for i in range(lk):
            bg_node_id = bg_nodes[i % len(bg_nodes)]
            
            bg_cmd = {
                "cmd_id": f"{self.process_id}_bg_bob_{i}",
                "process_id": self.process_id,
                "role": NodeRole.BG.value,
                "operation_id": i,
                "params": {
                    "process_id": self.process_id,
                    "operation_id": i,
                    "owner": "bob",
                    "bob_addr": self.node.node_id
                }
            }
            
            bg_node_key = f"cmd:{bg_node_id.get('id') if isinstance(bg_node_id, dict) else bg_node_id}"
            
            dispatch_tasks.append(
                self.node.store_data(bg_node_key, json.dumps(bg_cmd))
            )
        
        await asyncio.gather(*dispatch_tasks)
        
        logger.info("step_15_base_generation_commands_dispatched", count=len(dispatch_tasks))
    
    async def _collect_bob_bases(self, lk: int) -> List[str]:
        """
        STEP 15 (continuazione): Raccogli basi generate da BG_B.
        
        Legge dalla DHT: {process_id}:bg_bob_result:{i}
        """
        logger.info("collecting_bob_bases", lk=lk)
        
        bases = []
        for i in range(lk):
            result = await self._wait_for_result(
                f"{self.process_id}:bg_bob_result:{i}",
                timeout=30
            )
            
            bases.append(result.get("base", "+"))
        
        return bases
    
    async def _collect_measurements(self, lk: int) -> List[int]:
        """
        STEP 16-17: Raccogli bit misurati.
        
        Legge dalla DHT: {process_id}:qpm_result:{i}
        (Bob non sa che sono stati generati da QPM)
        """
        logger.info("collecting_measurements", lk=lk)
        
        bits = []
        for i in range(lk):
            result = await self._wait_for_result(
                f"{self.process_id}:qpm_result:{i}",
                timeout=60
            )
            
            bits.append(result.get("bit", 0))
        
        return bits
    
    async def _wait_for_qpc_sifting(self) -> List[int]:
        """
        STEP 18: Attendi che QPC memorizzi i risultati nella DHT.
        
        (Bob non sa che è QPC, legge solo dalla DHT)
        """
        logger.info("bob_waiting_for_qpc_sifting", process_id=self.process_id)
        
        for attempt in range(120):
            result = await self.node.retrieve_data(
                f"{self.process_id}:qpc_sifting_result"
            )
            
            if result and "valid_positions" in result:
                logger.info(
                    "bob_received_qpc_sifting",
                    valid_positions=len(result["valid_positions"])
                )
                return result["valid_positions"]
            
            await asyncio.sleep(0.5)
        
        raise TimeoutError("Timeout waiting for QPC sifting results")
    
    async def _wait_for_result(
        self,
        key: str,
        timeout: int = 30
    ) -> Dict[str, Any]:
        """Wait for a specific result to appear in DHT."""
        for attempt in range(timeout * 2):
            result = await self.node.retrieve_data(key)
            if result:
                return result
            
            await asyncio.sleep(0.5)
            
            if (attempt + 1) % 10 == 0:
                logger.debug("still_waiting_for_result", key=key, attempt=attempt + 1)
        
        raise TimeoutError(f"Timeout waiting for result: {key}")
