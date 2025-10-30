import math
import secrets
from typing import Dict, Any, Tuple
from core.dht_node import CQKDNode
from core.node_states import NodeRole
from quantum.bg import BaseGenerator
from utils.logging_config import get_logger


logger = get_logger(__name__)


class QuantumPhotonMeter:
    """
    Quantum Photon Meter (QPM)

    Misura la polarizzazione di un fotone secondo la meccanica quantistica.

    La probabilità di misurare 0 o 1 dipende dall'angolo tra la polarizzazione
    del fotone e la base di misurazione:
    P(0) = cos²(θ)
    P(1) = sin²(θ) = 1 - cos²(θ)

    dove θ è l'angolo tra polarizzazione e primo asse della base.
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
        alice_polarization: int,
        bob_base: str,
        bob_addr: str,
        qpc_addr: str
    ) -> Dict[str, Any]:
        """
        Esegue l'operazione QPM

        Args:
            node: Nodo DHT su cui eseguire
            process_id: ID del processo di generazione chiave
            operation_id: ID univoco dell'operazione
            alice_polarization: Polarizzazione da Alice via QPP
            bob_base: Base da Bob via BG
            bob_addr: Indirizzo di Bob
            qpc_addr: Indirizzo del QPC

        Returns:
            dict: Risultato con bit misurato e info confronto basi
        """
        # Verifica ruolo
        if not node.current_role or node.current_role.role != NodeRole.QPM:
            raise ValueError(f"Node {node.node_id} is not in QPM role")

        # Esegui misurazione quantistica
        measured_bit, bases_match = cls.measure(alice_polarization, bob_base)

        logger.info(
            "qpm_measurement_done",
            node_id=node.node_id,
            process_id=process_id,
            operation_id=operation_id,
            alice_polarization=alice_polarization,
            bob_base=bob_base,
            measured_bit=measured_bit,
            bases_match=bases_match
        )

        # Memorizza bit misurato per Bob
        key_to_bob = f"{process_id}:qpm:{operation_id}:to_bob"
        await node.store_data(key_to_bob, {
            "measured_bit": measured_bit,
            "from_node": node.node_id,
            "operation_id": operation_id
        })

        # Memorizza info per QPC (confronto basi)
        key_to_qpc = f"{process_id}:qpm:{operation_id}:to_qpc:{qpc_addr}"
        await node.store_data(key_to_qpc, {
            "alice_polarization": alice_polarization,
            "bob_base": bob_base,
            "bases_match": bases_match,
            "operation_id": operation_id,
            "from_node": node.node_id
        })

        # Rilascia ruolo
        await node.release_role()

        return {
            "operation_id": operation_id,
            "role": NodeRole.QPM.value,
            "measured_bit": measured_bit,
            "bases_match": bases_match,
            "alice_polarization": alice_polarization,
            "bob_base": bob_base,
            "success": True
        }
