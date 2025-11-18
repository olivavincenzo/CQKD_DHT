import json
import asyncio
from typing import Dict, Any

from core.dht_node import CQKDNode
from core.node_states import NodeRole
from utils.logging_config import get_logger

logger = get_logger(__name__)

class QuantumPhotonPolarizer:
    """
    Quantum Photon Polarizer (QPP)
    
    RUOLO (dal Paper Sezione 3-4):
    - Applica polarizzazione a "fotone computazionale"
    - Usa: spin (da QSG) + base (da BG di Alice)
    - Calcola polarizzazione secondo mappa quantum
    
    Mappa (spin, base) → polarizzazione:
    - (0, '+') → 0°
    - (1, '+') → 90°
    - (0, 'x') → 45°
    - (1, 'x') → 135°
    """
    
    POLARIZATION_MAP = {
        (0, '+'): 0,
        (1, '+'): 90,
        (0, 'x'): 45,
        (1, 'x'): 135
    }
    
    @classmethod
    def polarize(cls, spin: int, base: str) -> int:
        """
        Calcola la polarizzazione basata su spin e base
        
        Args:
            spin: Bit di spin (0 o 1)
            base: Base usata ('+' o 'x')
            
        Returns:
            int: Angolo di polarizzazione in gradi
        """
        return cls.POLARIZATION_MAP.get((spin, base), 0)
    
    @classmethod
    async def execute(
        cls,
        node: CQKDNode,
        process_id: str,
        operation_id: str,
        qpm_addr: str
    ) -> Dict[str, Any]:
        """
        Esegue l'operazione QPP secondo il paper (Step 8-9).
        
        FLUSSO (Sezione 4):
        1. QPP ATTENDE spin da QSG
        2. QPP ATTENDE base da BG (di Alice)
        3. QPP calcola polarizzazione = f(spin, base)
        4. QPP memorizza polarizzazione per QPM
        
        Args:
            node: Nodo DHT su cui eseguire
            process_id: ID del processo
            operation_id: ID univoco dell'operazione
            qpm_addr: Indirizzo del QPM destinatario
            
        Returns:
            dict: Risultato con polarizzazione calcolata
        """
        # Verifica ruolo
        if not node.current_role or node.current_role.role != NodeRole.QPP:
            raise ValueError(f"Node {node.node_id} is not in QPP role")
        
        # ✅ STEP 8-9: QPP recupera spin da QSG
        spin_key = f"{process_id}:qsg_to_qpp:{operation_id}"
        spin_data = await cls._wait_for_data(node, spin_key, "spin from QSG")
        spin = spin_data.get("spin")
        
        logger.info("qpp_received_spin", spin=spin, operation_id=operation_id)
        
        # ✅ STEP 8-9: QPP recupera base da BG (di Alice)
        base_key = f"{process_id}:bg_to_qpp:{operation_id}"
        base_data = await cls._wait_for_data(node, base_key, "base from BG")
        base = base_data.get("base")
        
        logger.info("qpp_received_base", base=base, operation_id=operation_id)
        
        # ✅ Calcola polarizzazione
        polarization = cls.polarize(spin, base)
        
        logger.info(
            "qpp_polarization_calculated",
            node_id=node.node_id,
            process_id=process_id,
            operation_id=operation_id,
            spin=spin,
            base=base,
            polarization=polarization
        )
        
        # ✅ STEP 8-9: QPP invia polarizzazione A QPM
        key_to_qpm = f"{process_id}:qpp_to_qpm:{operation_id}"
        await node.store_data(key_to_qpm, {
            "polarization": polarization,
            "alice_base": base,
            "spin": spin,
            "from_node": node.node_id,
            "operation_id": operation_id
        })
        
        logger.info("qpp_sent_to_qpm", qpm_addr=qpm_addr, polarization=polarization)
        
        # Rilascia ruolo
        await node.release_role()
        
        return {
            "operation_id": operation_id,
            "role": NodeRole.QPP.value,
            "polarization": polarization,
            "spin": spin,
            "base": base,
            "success": True
        }
    
    @staticmethod
    async def _wait_for_data(
        node: CQKDNode,
        key: str,
        description: str,
        timeout: int = 60
    ) -> Dict[str, Any]:
        """
        Attende che un dato sia disponibile nella DHT.
        
        Args:
            node: Nodo DHT
            key: Chiave da attendere
            description: Descrizione per logging
            timeout: Timeout in secondi
            
        Returns:
            dict: Dati recuperati
        """
        for attempt in range(timeout * 10):
            data = await node.retrieve_data(key)
            if data:
                return data
            
            await asyncio.sleep(0.5)
            
            if (attempt + 1) % 20 == 0:
                logger.debug(
                    f"qpp_waiting_for_{description}",
                    key=key,
                    attempt=attempt + 1
                )
        
        raise TimeoutError(f"Timeout waiting for {description}: {key}")
