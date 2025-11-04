import secrets
import json
from typing import Dict, Any, List

from core.dht_node import CQKDNode
from core.node_states import NodeRole
from utils.logging_config import get_logger

logger = get_logger(__name__)

class BaseGenerator:
    """
    Base Generator (BG)
    
    RUOLO (dal Paper Sezione 3-4):
    - Genera basi casuali per misurazione quantistica
    - '+' (rectilinear): angoli 0° e 90°
    - 'x' (diagonal): angoli 45° e 135°
    - Nel protocollo BB84, Alice e Bob usano basi casuali
    """
    
    BASES = {
        '+': [0, 90],      # Base rettilinea
        'x': [45, 135]     # Base diagonale
    }
    
    @staticmethod
    def generate_base() -> str:
        """
        Genera una base casuale
        
        Returns:
            str: '+' o 'x'
        """
        return secrets.choice(['+', 'x'])
    
    @staticmethod
    def generate_base_sequence(length: int) -> List[str]:
        """
        Genera una sequenza di basi casuali
        
        Args:
            length: Lunghezza della sequenza
            
        Returns:
            list[str]: Sequenza di basi ('+' o 'x')
        """
        return [BaseGenerator.generate_base() for _ in range(length)]
    
    @staticmethod
    def get_angles_for_base(base: str) -> List[int]:
        """
        Ritorna gli angoli per una data base
        
        Args:
            base: '+' o 'x'
            
        Returns:
            list[int]: Angoli in gradi
        """
        return BaseGenerator.BASES.get(base, [0, 90])
    
    @classmethod
    async def execute(
        cls,
        node: CQKDNode,
        process_id: str,
        operation_id: str,
        owner: str,
        alice_addr: str = None,
        qpp_addr: str = None,
        bob_addr: str = None,
        qpm_addr: str = None
    ) -> Dict[str, Any]:
        """
        Esegue l'operazione BG secondo il paper (Step 8-9 o Step 15).
        
        FLUSSO (Sezione 4):
        - Se owner="alice" (Step 8-9):
          1. BG genera base casuale
          2. BG invia base AD ALICE (per step 10)
          3. BG invia COMANDO a QPP (con base)
          
        - Se owner="bob" (Step 15):
          1. BG genera base casuale
          2. BG invia COMANDO a QPM (con base di Bob)
        
        Args:
            node: Nodo DHT su cui eseguire
            process_id: ID del processo
            operation_id: ID univoco dell'operazione
            owner: "alice" o "bob"
            alice_addr: Indirizzo di Alice (se owner="alice")
            qpp_addr: Indirizzo QPP (se owner="alice")
            bob_addr: Indirizzo di Bob (se owner="bob")
            qpm_addr: Indirizzo QPM (se owner="bob")
            
        Returns:
            dict: Risultato con base generata
        """
        # Verifica ruolo
        if not node.current_role or node.current_role.role != NodeRole.BG:
            raise ValueError(f"Node {node.node_id} is not in BG role")
        
        # Genera base casuale
        base = cls.generate_base()
        angles = cls.get_angles_for_base(base)
        
        logger.info(
            "bg_base_generated",
            node_id=node.node_id,
            process_id=process_id,
            operation_id=operation_id,
            base=base,
            owner=owner
        )
        
        if owner == "alice":
            # ✅ STEP 8-9: BG invia base AD ALICE
            key_to_alice = f"{process_id}:bg_alice_result:{operation_id}"
            await node.store_data(key_to_alice, {
                "base": base,
                "angles": angles,
                "from_node": node.node_id,
                "operation_id": operation_id
            })
            
            logger.info("bg_sent_to_alice", alice_addr=alice_addr, base=base)
            
            # ✅ STEP 8-9: BG invia COMANDO a QPP con base
            if qpp_addr:
                # Memorizza base per QPP
                key_to_qpp = f"{process_id}:bg_to_qpp:{operation_id}"
                await node.store_data(key_to_qpp, {
                    "base": base,
                    "angles": angles,
                    "from_node": node.node_id,
                    "operation_id": operation_id
                })
                
                # QPP verrà invocato da Alice separatamente
                # QPP leggerà sia da QSG che da BG
                
                logger.info("bg_sent_to_qpp", qpp_addr=qpp_addr, base=base)
        
        elif owner == "bob":
            # ✅ STEP 15: BG invia base A QPM (per misurazione di Bob)
            key_to_qpm = f"{process_id}:bg_bob_result:{operation_id}"
            await node.store_data(key_to_qpm, {
                "base": base,
                "angles": angles,
                "from_node": node.node_id,
                "operation_id": operation_id
            })
            
            logger.info("bg_sent_to_qpm", qpm_addr=qpm_addr, base=base)
        
        # Rilascia ruolo
        await node.release_role()
        
        return {
            "operation_id": operation_id,
            "role": NodeRole.BG.value,
            "base": base,
            "angles": angles,
            "owner": owner,
            "success": True
        }
