from typing import Dict, Any, List
from core.dht_node import CQKDNode
from core.node_states import NodeRole
from utils.logging_config import get_logger


logger = get_logger(__name__)


class QuantumPhotonCollider:
    """
    Quantum Photon Collider (QPC)

    Confronta le basi usate da Alice e Bob e identifica le posizioni
    in cui le basi coincidono. Solo questi bit vengono mantenuti
    nella chiave finale (sift in BB84).
    """

    @classmethod
    def sift_keys(
        cls,
        measurements: List[Dict[str, Any]]
    ) -> List[int]:
        """
        Esegue il sifting: identifica posizioni con basi coincidenti

        Args:
            measurements: Lista di misurazioni da QPM

        Returns:
            list[int]: Indici delle posizioni valide
        """
        valid_positions = []

        for idx, measurement in enumerate(measurements):
            if measurement.get('bases_match', False):
                valid_positions.append(idx)

        return valid_positions

    @classmethod
    async def execute(
        cls,
        node: CQKDNode,
        process_id: str,
        operation_id: str,
        measurements: List[Dict[str, Any]],
        alice_addr: str,
        bob_addr: str
    ) -> Dict[str, Any]:
        """
        Esegue QPC: confronta basi e identifica posizioni valide
        """
        # ❌ RIMUOVI QUESTO CHECK (non serve più)
        # if not node.current_role or node.current_role.role != NodeRole.QPC:
        #     raise ValueError(f"Node {node.node_id} is not in QPC role")
        
        # ✅ Esegui sifting direttamente
        valid_positions = cls.sift_keys(measurements)
        
        logger.info(
            "qpc_sifting_complete",
            process_id=process_id,
            total_measurements=len(measurements),
            valid_positions=len(valid_positions),
            efficiency=len(valid_positions) / len(measurements) if measurements else 0
        )
        
        # Memorizza risultati per Alice
        result = {
            "valid_positions": valid_positions,
            "total_measurements": len(measurements),
            "process_id": process_id
        }
        
        key_alice = f"{process_id}:qpc:collision:valid_positions_alice"
        await node.store_data(key_alice, str(valid_positions))  # Store come string
        
        # Memorizza anche per Bob
        key_bob = f"{process_id}:qpc:collision:valid_positions_bob"
        await node.store_data(key_bob, str(valid_positions))
        
        return result
