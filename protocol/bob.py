import asyncio
import json
from typing import List, Dict, Any
from core.dht_node import CQKDNode
from core.node_states import NodeRole
from quantum.bg import BaseGenerator
from quantum.qpm import QuantumPhotonMeter
from utils.logging_config import get_logger
import datetime

logger = get_logger(__name__)


class Bob:
    """
    Bob - Ricevente nel protocollo CQKD
    Segue STEP 12-17 del paper
    """
    
    def __init__(self, node: CQKDNode):
        self.node = node
        self.bob_bases: List[str] = []
        self.bob_bits: List[int] = []
        self.process_id: None
    async def receive_key(self, process_id: str) -> bytes:
        """
        Bob riceve e genera chiave seguendo STEP 12-17
        
        Args:
            process_id: ID del processo (Alice lo comunica)
            
        Returns:
            bytes: Chiave generata
        """

        try:
            logger.info("bob_waiting_for_alice_notification", process_id=process_id)
            self.process_id= process_id
            
            
            # ========== STEP 12: Bob attende notifica da Alice ==========
            notification = await self._wait_for_alice_notification(process_id)
            
            lk = notification['lk']
            lc = notification.get('lc') 
            alice_bases = notification["alice_bases"]
            qpm_nodes = notification["qpm_nodes"]
 

            logger.info(
                "step_11_notification_received",
                process_id=process_id,
                lc=lc,
                lk=lk
            )
            
            # ===== STEP 15: DISPATCH commands to BG nodes for Bob's bases =====
            await self._dispatch_base_generation(lk, qpm_nodes)
            # Collect Bob's bases from workers
            self.bob_bases = await self._collect_bob_bases(lk)

            logger.info("step_15_bases_generated_by_workers", count=len(self.bob_bases))
                
            # ===== STEP 16-17: DISPATCH commands to QPM nodes for measurements =====
            await self._dispatch_measurements(lk, qpm_nodes)

            # Collect Bob's measurements from workers
            self.bob_bits = await self._collect_measurements(lk)
            
            logger.info(
                "step_16_17_measurements_complete_from_workers",
                measurements=len(self.bob_bits)
            )



            # ===== STEP 18: Perform sifting with base comparison =====
            valid_positions = []
            for i in range(min(len(alice_bases), len(self.bob_bases))):
                if alice_bases[i] == self.bob_bases[i]:
                    valid_positions.append(i)
            
            logger.info(
                "step_18_base_comparison_sifting",
                total_bits=lk,
                matching_bases=len(valid_positions),
                sift_ratio=len(valid_positions) / lk if lk > 0 else 0
            )
            
            # Store sifting results for Alice
            sifting_result = {
                "process_id": self.process_id,
                "valid_positions": valid_positions,
                "total_bits": lk,
                "sift_ratio": len(valid_positions) / lk if lk > 0 else 0,
                "timestamp": datetime.now().isoformat()
            }
            
            await self.node.store_data(
                f"{self.process_id}:qpc_sifting_result",
                 json.dumps(sifting_result)
            )
            await self.node.store_data(
                "latest_qpc_sifting_result",
                 json.dumps(sifting_result)
            )
            
            logger.info(
                "step_18_sifting_complete_stored",
                valid_positions=len(valid_positions)
            )
            
            # ===== STEP 19: Extract final key =====
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
        STEP 12: Attende notifica da Alice
        
        Returns:
            Dict con lk, sorting_rule, qpm_addresses
        """
        key = f"{process_id}:alice_to_bob:notification"
        
        # Polling con timeout
        max_attempts = 30
        for attempt in range(max_attempts):
            notification_str = await self.node.retrieve_data(key)
            if notification_str:
                notification = json.loads(notification_str)
                logger.info("alice_notification_received", lk=notification.get('lk'))
                return notification
            
            await asyncio.sleep(0.5)
        
        raise TimeoutError("Timeout waiting for Alice notification")


    async def _dispatch_base_generation(self, lk: int, qpm_nodes: List[str]):
        """
        STEP 15: Dispatch commands to BG nodes to generate Bob's bases.
        """
        logger.info(
            "dispatching_base_generation_to_workers",
            process_id=self.process_id,
            lk=lk
        )
        
        dispatch_tasks = []
        
        for i in range(lk):
            # Reuse some nodes or use available BG nodes
            # In practice, you'd have a pool of BG nodes
            bg_cmd = {
                "cmd_id": f"{self.process_id}_bg_bob_{i}",
                "process_id": self.process_id,
                "role": NodeRole.BG.value,
                "operation_id": i,
                "params": {
                    "process_id": self.process_id,
                    "operation_id": i,
                    "bob_addr": self.node.node_id,
                    "qpm_addr": qpm_nodes[i % len(qpm_nodes)] if qpm_nodes else None
                }
            }
            
            # Note: In real implementation, you'd get BG node IDs from allocation
            # For now, we'll store with a generic key pattern
            dispatch_tasks.append(
                self.node.store_data(
                    f"{self.process_id}:cmd_bg_bob:{i}",
                     json.dumps(bg_cmd)
                )
            )
        
        await asyncio.gather(*dispatch_tasks)
        
        logger.info("base_generation_dispatched", commands=len(dispatch_tasks))

    async def _collect_bob_bases(self, lk: int) -> List[str]:
        """
        Collect Bob's bases generated by BG worker nodes.
        """
        logger.info("collecting_bob_bases_from_workers", lk=lk)
        
        bases = []
        
        for i in range(lk):
            result = await self._wait_for_result(
                f"{self.process_id}:bg_bob_result:{i}",
                timeout=30
            )
            bases.append(result.get("base", "+"))
        
        return bases

    async def _dispatch_measurements(
        self, 
        lk: int, 
        qpm_nodes: List[str]
    ):
        """
        STEP 16-17: Dispatch commands to QPM nodes for measurements.
        """
        logger.info("dispatching_measurements_to_workers", lk=lk)
        
        dispatch_tasks = []
        
        for i in range(lk):
            qpm_node_id = qpm_nodes[i % len(qpm_nodes)]
            
            qpm_cmd = {
                "cmd_id": f"{self.process_id}_qpm_{i}",
                "process_id": self.process_id,
                "role": NodeRole.QPM.value,
                "operation_id": i,
                "params": {
                    "process_id": self.process_id,
                    "operation_id": i,
                    "alice_polarization_key": f"{self.process_id}:polarization:{i}",
                    "bob_base_key": f"{self.process_id}:bg_bob_result:{i}",
                    "bob_addr": self.node.node_id,
                    "qpc_addr": None
                }
            }
            
            dispatch_tasks.append(
                self.node.store_data(f"cmd:{qpm_node_id}", json.dumps(qpm_cmd))
            )
        
        await asyncio.gather(*dispatch_tasks)
        
        logger.info("measurements_dispatched", commands=len(dispatch_tasks))

    async def _collect_measurements(self, lk: int) -> List[int]:
        """
        Collect measurements from QPM worker nodes.
        """
        logger.info("collecting_measurements_from_workers", lk=lk)
        
        bits = []
        
        for i in range(lk):
            result = await self._wait_for_result(
                f"{self.process_id}:qpm_result:{i}",
                timeout=30
            )
            bits.append(result.get("bit", 0))
        
        return bits

    async def _wait_for_result(
        self, 
        key: str, 
        timeout: int = 30
    ) -> Dict[str, Any]:
        """
        Wait for a specific result to appear in DHT.
        """
        for attempt in range(timeout * 2):
            result = await self.node.retrieve_data(key)
            
            if result:
                return result
            
            await asyncio.sleep(0.5)
            
            if (attempt + 1) % 10 == 0:
                logger.debug("still_waiting_for_result", key=key, attempt=attempt + 1)
        
        raise TimeoutError(f"Timeout waiting for result: {key}")