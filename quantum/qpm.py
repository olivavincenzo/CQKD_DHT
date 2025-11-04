import math
import secrets
import json
import asyncio
from typing import Dict, Any, Tuple

from core.dht_node import CQKDNode
from core.node_states import NodeRole
from quantum.bg import BaseGenerator
from utils.logging_config import get_logger

logger = get_logger(__name__)

class QuantumPhotonMeter:
    """
    Quantum Photon Meter (QPM)
    
    RUOLO (dal Paper Sezione 3-4):
    - Misura la polarizzazione di un fotone secondo meccanica quantistica
    - Riceve: polarizzazione (da QPP) + base di Bob (da BG_B)
    - Calcola probabilità secondo: P(0) = cos²(θ), P(1) = sin²(θ)
    - Invia: bit misurato a Bob + dati a QPC per collision
    """
    
    @classmethod
    def measure(
        cls,
        alice_polarization: int,
        bob_base: str
    ) -> Tuple[int, bool]:
        """
        Simula misurazione quantistica
        
        Args:
            alice_polarization: Polarizzazione inviata da Alice (gradi)
            bob_base: Base usata da Bob per misurare ('+' o 'x')
            
        Returns:
            tuple: (bit_misurato, basi_coincidono)
        """
        bob_angles = BaseGenerator.get_angles_for_base(bob_base)
        
        # Calcola angolo tra polarizzazione e primo asse della base
        angle_diff_0 = abs(alice_polarization - bob_angles[0])
        angle_diff_1 = abs(alice_polarization - bob_angles[1])
        
        # Normalizza a [0, 90] per simmetria
        angle_diff_0 = min(angle_diff_0, 180 - angle_diff_0)
        angle_diff_1 = min(angle_diff_1, 180 - angle_diff_1)
        
        # Calcola probabilità secondo meccanica quantistica
        # P(0) = cos²(θ)
        prob_0 = math.cos(math.radians(angle_diff_0)) ** 2
        
        # Misurazione probabilistica
        random_value = secrets.randbelow(10000) / 10000.0
        measured_bit = 0 if random_value < prob_0 else 1
        
        # Determina se le basi coincidono
        alice_base = '+' if alice_polarization in [0, 90] else 'x'
        bases_match = (alice_base == bob_base)
        
        return measured_bit, bases_match
    
    @classmethod
    async def execute(
        cls,
        node: CQKDNode,
        process_id: str,
        operation_id: str,
        bob_addr: str
    ) -> Dict[str, Any]:
        """
        Esegue l'operazione QPM secondo il paper (Step 16-17).
        
        FLUSSO (Sezione 4):
        1. QPM ATTENDE polarizzazione da QPP (di Alice)
        2. QPM ATTENDE base da BG_B (di Bob)
        3. QPM misura secondo meccanica quantistica
        4. QPM invia bit misurato A BOB
        5. QPM invia dati (polarization_alice, base_bob, bit_bob) A QPC
        
        Args:
            node: Nodo DHT su cui eseguire
            process_id: ID del processo
            operation_id: ID univoco dell'operazione
            bob_addr: Indirizzo di Bob
            qpc_addr: Indirizzo del QPC
            
        Returns:
            dict: Risultato con bit misurato e info sifting
        """
        # Verifica ruolo
        if not node.current_role or node.current_role.role != NodeRole.QPM:
            raise ValueError(f"Node {node.node_id} is not in QPM role")
        
        # ✅ STEP 16: QPM recupera polarizzazione da QPP
        pol_key = f"{process_id}:qpp_to_qpm:{operation_id}"
        pol_data = await cls._wait_for_data(node, pol_key, "polarization from QPP")
        alice_polarization = pol_data.get("polarization")
        alice_base = pol_data.get("alice_base")
        
        logger.info(
            "qpm_received_polarization",
            alice_polarization=alice_polarization,
            alice_base=alice_base,
            operation_id=operation_id
        )
        
        # ✅ STEP 16: QPM recupera base di Bob da BG_B
        bob_base_key = f"{process_id}:bg_bob_result:{operation_id}"
        bob_base_data = await cls._wait_for_data(node, bob_base_key, "base from BG_B")
        bob_base = bob_base_data.get("base")
        
        logger.info("qpm_received_bob_base", bob_base=bob_base, operation_id=operation_id)
        
        # ✅ STEP 17: QPM esegue misurazione quantistica
        measured_bit, bases_match = cls.measure(alice_polarization, bob_base)
        
        logger.info(
            "qpm_measurement_done",
            node_id=node.node_id,
            process_id=process_id,
            operation_id=operation_id,
            alice_polarization=alice_polarization,
            alice_base=alice_base,
            bob_base=bob_base,
            measured_bit=measured_bit,
            bases_match=bases_match
        )
        
        # ✅ STEP 17: QPM invia bit misurato A BOB
        key_to_bob = f"{process_id}:qpm_result:{operation_id}"
        await node.store_data(key_to_bob, {
            "bit": measured_bit,
            "from_node": node.node_id,
            "operation_id": operation_id
        })
        
        logger.info("qpm_sent_to_bob", bob_addr=bob_addr, measured_bit=measured_bit)
        
        # ✅ STEP 17: QPM invia dati A QPC per collision (step 18)
        key_to_qpc = f"{process_id}:qpm_to_qpc:{operation_id}"
        await node.store_data(key_to_qpc, {
            "alice_base": alice_base,
            "bob_base": bob_base,
            "bases_match": bases_match,
            "operation_id": operation_id,
            "from_node": node.node_id
        })
        
        logger.info("qpm_sent_to_qpc", bases_match=bases_match)
        
        # Rilascia ruolo
        await node.release_role()
        
        return {
            "operation_id": operation_id,
            "role": NodeRole.QPM.value,
            "measured_bit": measured_bit,
            "bases_match": bases_match,
            "alice_base": alice_base,
            "bob_base": bob_base,
            "success": True
        }
    
    @staticmethod
    async def _wait_for_data(
        node: CQKDNode,
        key: str,
        description: str,
        timeout: int = 60
    ) -> Dict[str, Any]:
        """Attende che un dato sia disponibile nella DHT."""
        for attempt in range(timeout * 10):
            data = await node.retrieve_data(key)
            if data:
                return data
            
            await asyncio.sleep(0.5)
            
            if (attempt + 1) % 20 == 0:
                logger.debug(
                    f"qpm_waiting_for_{description}",
                    key=key,
                    attempt=attempt + 1
                )
        
        raise TimeoutError(f"Timeout waiting for {description}: {key}")
