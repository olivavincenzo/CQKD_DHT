from typing import Dict, Any
from core.dht_node import CQKDNode
from core.node_states import NodeRole
from quantum.bg import BaseGenerator
from utils.logging_config import get_logger


logger = get_logger(__name__)


class QuantumPhotonPolarizer:
    """
    Quantum Photon Polarizer (QPP)

    Applica polarizzazione a un "fotone computazionale" basandosi
    su spin (da QSG) e base (da Alice).

    Mappa spin-base -> polarizzazione:
    - spin=0, base='+' -> 0°
    - spin=1, base='+' -> 90°
    - spin=0, base='x' -> 45°
    - spin=1, base='x' -> 135°
    """

    # Mappa (spin, base) -> polarizzazione in gradi
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
        spin: int,
        base: str,
        qpm_addr: str
    ) -> Dict[str, Any]:
        """
        Esegue l'operazione QPP

        Args:
            node: Nodo DHT su cui eseguire
            process_id: ID del processo di generazione chiave
            operation_id: ID univoco dell'operazione
            spin: Spin ricevuto da QSG
            base: Base scelta da Alice
            qpm_addr: Indirizzo del QPM destinatario

        Returns:
            dict: Risultato con polarizzazione
        """
        # Verifica ruolo
        if not node.current_role or node.current_role.role != NodeRole.QPP:
            raise ValueError(f"Node {node.node_id} is not in QPP role")

        # Calcola polarizzazione
        polarization = cls.polarize(spin, base)

        logger.info(
            "qpp_polarization_applied",
            node_id=node.node_id,
            process_id=process_id,
            operation_id=operation_id,
            spin=spin,
            base=base,
            polarization=polarization
        )

        # Memorizza risultato per QPM
        key_to_qpm = f"{process_id}:qpp:{operation_id}:to_qpm:{qpm_addr}"
        await node.store_data(key_to_qpm, {
            "polarization": polarization,
            "spin": spin,
            "alice_base": base,
            "from_node": node.node_id,
            "operation_id": operation_id,
            "target_qpm": qpm_addr
        })

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
