import asyncio
import secrets
from typing import List, Dict, Any, Optional
from core.dht_node import CQKDNode
from core.node_states import NodeRole
from protocol.key_generation import KeyGenerationOrchestrator
from quantum.qsg import QuantumSpinGenerator
from quantum.bg import BaseGenerator
from quantum.qpp import QuantumPhotonPolarizer
from utils.logging_config import get_logger


logger = get_logger(__name__)


class Alice:
    """
    Alice - Implementazione COMPLETA seguendo TUTTI i 19 step del paper
    """
    
    def __init__(self, node: CQKDNode, bob_address: str):
        self.node = node
        self.bob_address = bob_address
        self.orchestrator = KeyGenerationOrchestrator(node)
        self.alice_bases: List[str] = []
        self.alice_bits: List[int] = []
        self.sorting_rule: List[int] = []
        
    async def generate_key(
        self,
        desired_length_bits: int,
        available_nodes: Optional[List[str]] = None
    ) -> bytes:
        """
        Genera chiave seguendo esattamente i 19 step del paper (Sezione 4)
        
        Args:
            desired_length_bits: lc - lunghezza chiave desiderata
            available_nodes: Nodi disponibili (opzionale)
            
        Returns:
            bytes: Chiave generata
        """
        process_id = self.orchestrator.process_id
        
        logger.info(
            "alice_key_generation_start_19steps",
            process_id=process_id,
            desired_length=desired_length_bits
        )
        
        # ========== STEP 1: Alice calcola lk = |2.5 * lc| ==========
        requirements = self.orchestrator.calculate_required_nodes(desired_length_bits)
        lk = requirements['initial_key_length']
        lc = desired_length_bits
        
        logger.info("step_1_complete", lc=lc, lk=lk, alpha=requirements['total'])
        
        # ========== STEP 2-3: Alice ping nodi e verifica #(n) >= 5lk ==========
        if available_nodes is None:
            available_nodes = await self.orchestrator.discover_available_nodes(
                required_count=requirements['total']
            )
        
        if len(available_nodes) < requirements['total']:
            raise ValueError(
                f"Nodi insufficienti: richiesti {requirements['total']}, "
                f"disponibili {len(available_nodes)}"
            )
        
        logger.info("step_2_3_complete", available_nodes=len(available_nodes))
        
        # ========== STEP 4-6: Alice alloca nodi QSG, BG, QPP ==========
        allocation = await self.orchestrator.allocate_nodes(
            available_nodes,
            requirements
        )
        
        logger.info(
            "step_4_5_6_complete",
            qsg_count=len(allocation[NodeRole.QSG]),
            bg_count=len(allocation[NodeRole.BG]),
            qpp_count=len(allocation[NodeRole.QPP])
        )
        
        # ========== STEP 7: Alice apre process_id unico ==========
        logger.info("step_7_complete", process_id=process_id)
        
        # ========== STEP 8-9: Alice comanda nodi e riceve risultati ==========
        self.alice_bases = BaseGenerator.generate_base_sequence(lk)
        
        # Genera fotoni computazionali in parallelo
        tasks = []
        for i in range(lk):
            task = self._execute_qsg_bg_qpp_chain(
                i,
                allocation[NodeRole.QSG][i],
                allocation[NodeRole.QPP][i],
                allocation[NodeRole.QPM][i],
                self.alice_bases[i]
            )
            tasks.append(task)
        
        photon_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verifica errori
        errors = [r for r in photon_results if isinstance(r, Exception)]
        if errors:
            raise RuntimeError(f"Errori durante generazione fotoni: {len(errors)}")
        
        # Estrai bit di Alice
        self.alice_bits = [r['alice_bit'] for r in photon_results]
        
        logger.info("step_8_9_complete", photons_generated=len(self.alice_bits))
        
        # ========== STEP 10: Alice genera NUOVO ORDINE CASUALE ==========
        original_indices = list(range(lk))
        shuffled_indices = original_indices.copy()
        secrets.SystemRandom().shuffle(shuffled_indices)

        self.sorting_rule = shuffled_indices
        self.alice_bits_original = self.alice_bits.copy()  # ✅ SALVA ORIGINALE
        shuffled_alice_bits = [self.alice_bits[i] for i in shuffled_indices]
        self.alice_bits = shuffled_alice_bits
                
        logger.info("step_10_complete", sorting_rule_sample=self.sorting_rule[:10])
        
        # ========== STEP 11: Alice notifica Bob ==========
        await self._notify_bob(
            process_id=process_id,
            lk=lk,
            lc=lc,
            sorting_rule=self.sorting_rule,
            qpm_addresses=[allocation[NodeRole.QPM][i] for i in range(lk)]
        )
        
        logger.info("step_11_complete", notified_bob=True)
        
        # ========== STEP 12-15: Attendi che Bob completi le misurazioni ==========
        logger.info("waiting_for_bob_measurements")
        await asyncio.sleep(2)  # Dai tempo a Bob di misurare
        
        # ========== STEP 16-17: Raccogli measurements e ATTIVA QPC ==========
        logger.info("step_16_17_collecting_measurements")

        import json  # ✅ Aggiungi import se non c'è già

        measurements_for_qpc = []

        max_retries = 10  # Aumenta tentativi
        retry_delay = 1.0  # Secondi tra tentativi

        for i in range(lk):
            key_from_qpm = f"{process_id}:qpm:{i}:measurement"
            measurement_str = None
            
            # ✅ Retry loop per ogni measurement
            for attempt in range(max_retries):
                measurement_str = await self.node.retrieve_data(key_from_qpm)
                if measurement_str:
                    break  # Trovato!
                
                if attempt < max_retries - 1:
                    logger.debug(
                        "measurement_not_ready_retrying",
                        index=i,
                        attempt=attempt + 1
                    )
                    await asyncio.sleep(retry_delay)
            
            if measurement_str:
                measurement = json.loads(measurement_str)
                measurements_for_qpc.append(measurement)
            else:
                logger.warning(
                    "measurement_missing_after_retries",
                    index=i,
                    max_retries=max_retries
                )

        # ✅ Verifica che abbiamo TUTTE le measurements
        if len(measurements_for_qpc) < lk:
            raise ValueError(
                f"Measurements incomplete: expected {lk}, got {len(measurements_for_qpc)}. "
                f"Missing: {lk - len(measurements_for_qpc)}"
            )

        logger.info("measurements_collected", count=len(measurements_for_qpc))

        
        # ESEGUI QPC SIFTING
        qpc_node_info = allocation[NodeRole.QPC][0]
        valid_positions = await self._execute_qpc_sifting(
            process_id=process_id,
            qpc_node=qpc_node_info,
            measurements=measurements_for_qpc
        )
        
        logger.info(
            "step_16_17_complete",
            valid_positions_count=len(valid_positions),
            sift_ratio=len(valid_positions) / lk if lk > 0 else 0
        )
        
        # ========== STEP 18-19: Alice riordina e genera chiave finale ==========
        sifted_bits = [self.alice_bits_original[i] for i in valid_positions if i < len(self.alice_bits)]
        
        if len(sifted_bits) < lc:
            raise ValueError(
                f"Bit insufficienti dopo sifting: "
                f"richiesti {lc}, ottenuti {len(sifted_bits)}"
            )
        
        final_key_bits = sifted_bits[:lc]
        key_bytes = self.orchestrator.bits_to_bytes(final_key_bits)
        
        logger.info(
            "step_18_19_complete",
            final_key_length_bits=len(final_key_bits),
            final_key_length_bytes=len(key_bytes)
        )
        
        logger.info(
            "alice_key_generation_complete_19steps",
            process_id=process_id,
            all_steps_executed=True
        )
        
        return key_bytes
    
    async def _execute_qsg_bg_qpp_chain(
        self,
        index: int,
        qsg_node_id: str,
        qpp_node_id: str,
        qpm_node_id: str,
        alice_base: str
    ) -> Dict[str, Any]:
        """Esegue catena QSG → QPP → QPM per un singolo fotone"""
        process_id = self.orchestrator.process_id
        operation_id = f"photon_{index}"
        
        # QSG genera spin
        spin = QuantumSpinGenerator.generate_spin()
        
        # QPP applica polarizzazione con base di Alice
        polarization = QuantumPhotonPolarizer.polarize(spin, alice_base)
        
        # ✅ Serializza il dict in JSON string
        import json
        data_to_store = {
            "polarization": polarization,
            "alice_base": alice_base,
            "from_qpp": qpp_node_id,
            "operation_id": operation_id
        }
        
        key_to_qpm = f"{process_id}:qpp:{operation_id}:to_qpm:{qpm_node_id}"
        await self.node.store_data(key_to_qpm, json.dumps(data_to_store))  # ✅ Converte in string
        
        return {
            "index": index,
            "alice_bit": spin,
            "alice_base": alice_base,
            "polarization": polarization,
            "qsg_node": qsg_node_id,
            "qpp_node": qpp_node_id,
            "qpm_node": qpm_node_id
        }

    async def _notify_bob(
        self,
        process_id: str,
        lk: int,
        lc: int,
        sorting_rule: List[int],
        qpm_addresses: List[str]
    ):
        """STEP 11: Alice notifica Bob"""
        import json  # ✅ Aggiungi import
        
        key = f"{process_id}:alice_to_bob:notification"
        
        # ✅ Serializza il dict in JSON string
        notification_data = {
            "lk": lk,
            "lc": lc,
            "sorting_rule": sorting_rule,
            "qpm_addresses": qpm_addresses,
            "from": self.node.node_id,
            "to": self.bob_address
        }
        
        await self.node.store_data(key, json.dumps(notification_data))  # ✅ Converti in string
        
        logger.info("alice_notified_bob", process_id=process_id, lk=lk)


    async def _execute_qpc_sifting(
        self,
        process_id: str,
        qpc_node,
        measurements: List[Dict[str, Any]]
    ) -> List[int]:
        """
        STEP 16-17: Esegue il sifting tramite QPC
        
        Returns:
            List[int]: Posizioni valide (basi coincidenti)
        """
        from quantum.qpc import QuantumPhotonCollider
        
        operation_id = f"sifting_{process_id}"
        
        logger.info("executing_qpc_sifting", measurements_count=len(measurements))
        
        # ✅ Costruisci address da port (CQKDNode ha solo port, non address)
        alice_address = f"127.0.0.1:{self.node.port}"  # Usa port del nodo
        bob_address = self.bob_address  # Già una stringa "IP:PORT"
        
        # Esegui QPC
        result = await QuantumPhotonCollider.execute(
            node=self.node,
            process_id=process_id,
            operation_id=operation_id,
            measurements=measurements,
            alice_addr=alice_address,  # ✅ Usa la stringa costruita
            bob_addr=bob_address
        )
        
        logger.info("qpc_sifting_complete", valid_positions=len(result.get('valid_positions', [])))
        
        return result.get('valid_positions', [])
