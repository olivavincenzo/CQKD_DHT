import secrets
from typing import Dict, Any, List
from core.dht_node import CQKDNode
from core.node_states import NodeRole
from utils.logging_config import get_logger
import json

logger = get_logger(__name__)


class BaseGenerator:
    """
    Base Generator (BG)

    Genera basi casuali per la misurazione quantistica:
    - '+' (rectilinear): angoli 0° e 90°
    - 'x' (diagonal): angoli 45° e 135°

    Nel protocollo BB84, Alice e Bob usano basi casuali
    per codificare e misurare i qubit.
    """

    # Basi disponibili
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

    @classmethod
    def get_angles_for_base(cls, base: str) -> List[int]:
        """
        Ottieni gli angoli associati a una base

        Args:
            base: Base ('+' o 'x')

        Returns:
            list[int]: Lista di angoli in gradi
        """
        return cls.BASES.get(base, cls.BASES['+'])

    @classmethod
    async def execute(
        cls,
        node: CQKDNode,
        process_id: str,
        operation_id: str,
        bob_addr: str,
        qpm_addr: str
    ) -> Dict[str, Any]:
        """
        Esegue l'operazione BG

        Args:
            node: Nodo DHT su cui eseguire
            process_id: ID del processo di generazione chiave
            operation_id: ID univoco dell'operazione
            bob_addr: Indirizzo di Bob
            qpm_addr: Indirizzo del QPM destinatario

        Returns:
            dict: Risultato con base generata
        """
        # Verifica ruolo
        if not node.current_role or node.current_role.role != NodeRole.BG:
            raise ValueError(f"Node {node.node_id} is not in BG role")

        # Genera base
        base = cls.generate_base()
        angles = cls.get_angles_for_base(base)

        logger.info(
            "bg_base_generated",
            node_id=node.node_id,
            process_id=process_id,
            operation_id=operation_id,
            base=base,
            angles=angles
        )

        # Memorizza risultato per Bob
        key_to_bob = f"{process_id}:bg_bob_result:{operation_id}"
        key_to_alice= f"{process_id}:bg_alice_result:{operation_id}"
        key_to_qpm = f"{process_id}:bg:{operation_id}:to_qpm:{qpm_addr}"

        await node.store_data(key_to_alice, {
            "base": base,
            "angles": angles,
            "from_node": node.node_id,
            "operation_id": operation_id
        })

        await node.store_data(key_to_bob, {
            "base": base,
            "angles": angles,
            "from_node": node.node_id,
            "operation_id": operation_id
        })
        
        await node.store_data(key_to_qpm , {
            "base": base,
            "angles": angles,
            "from_node": node.node_id,
            "operation_id": operation_id,
            "target_qpm": qpm_addr
        })

        # Rilascia ruolo
        await node.release_role()

        return {
            "operation_id": operation_id,
            "role": NodeRole.BG.value,
            "base": base,
            "angles": angles,
            "success": True
        }
