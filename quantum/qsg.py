import secrets
from typing import Dict, Any
from core.dht_node import CQKDNode
from core.node_states import NodeRole
from utils.logging_config import get_logger


logger = get_logger(__name__)


class QuantumSpinGenerator:
    """
    Quantum Spin Generator (QSG)

    Genera bit casuali simulando spin quantistico:
    - Spin UP = 1
    - Spin DOWN = 0

    Utilizza CSPRNG (Cryptographically Secure Pseudo-Random Number Generator)
    per garantire casualità crittografica.
    """

    @staticmethod
    def generate_spin() -> int:
        """
        Genera un singolo bit casuale (0 o 1)

        Returns:
            int: 0 (spin down) o 1 (spin up)
        """
        return secrets.randbelow(2)

    @staticmethod
    def generate_spin_sequence(length: int) -> list[int]:
        """
        Genera una sequenza di spin casuali

        Args:
            length: Lunghezza della sequenza

        Returns:
            list[int]: Sequenza di spin (0 o 1)
        """
        return [QuantumSpinGenerator.generate_spin() for _ in range(length)]

    @classmethod
    async def execute(
        cls,
        node: CQKDNode,
        process_id: str,
        operation_id: str,
        alice_addr: str,
        qpp_addr: str
    ) -> Dict[str, Any]:
        """
        Esegue l'operazione QSG

        Args:
            node: Nodo DHT su cui eseguire
            process_id: ID del processo di generazione chiave
            operation_id: ID univoco dell'operazione
            alice_addr: Indirizzo di Alice
            qpp_addr: Indirizzo del QPP destinatario

        Returns:
            dict: Risultato con spin generato
        """
        # Verifica ruolo
        if not node.current_role or node.current_role.role != NodeRole.QSG:
            raise ValueError(f"Node {node.node_id} is not in QSG role")

        # Genera spin
        spin = cls.generate_spin()

        logger.info(
            "qsg_spin_generated",
            node_id=node.node_id,
            process_id=process_id,
            operation_id=operation_id,
            spin=spin
        )

        # Memorizza risultato per Alice
        key_to_alice = f"{process_id}:qsg:{operation_id}:to_alice"
        await node.store_data(key_to_alice, {
            "spin": spin,
            "from_node": node.node_id,
            "operation_id": operation_id
        })

        # Memorizza risultato per QPP
        key_to_qpp = f"{process_id}:qsg:{operation_id}:to_qpp:{qpp_addr}"
        await node.store_data(key_to_qpp, {
            "spin": spin,
            "from_node": node.node_id,
            "operation_id": operation_id,
            "target_qpp": qpp_addr
        })

        # Rilascia ruolo
        await node.release_role()

        return {
            "operation_id": operation_id,
            "role": NodeRole.QSG.value,
            "spin": spin,
            "success": True
        }
