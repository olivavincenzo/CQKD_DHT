import json
from typing import Dict, Any, List

from core.dht_node import CQKDNode
from core.node_states import NodeRole
from utils.logging_config import get_logger

logger = get_logger(__name__)

class QuantumPhotonCollider:
    """
    Quantum Photon Collider (QPC)
    
    RUOLO (dal Paper Sezione 3-4):
    - Riceve dati da TUTTI i QPM (polarizzazione_alice, base_bob, bit_bob, bases_match)
    - Confronta le basi usate da Alice e Bob
    - Identifica posizioni dove le basi coincidono (collision)
    - Restituisce posizioni valide per il sifting finale
    
    IMPORTANTE: QPC è invocato da una logica coordinatrice (Alice o Bob),
    NON riceve comandi diretti dai nodi worker.
    """
    
    @classmethod
    def sift_keys(
        cls,
        measurements: List[Dict[str, Any]]
    ) -> List[int]:
        """
        Esegue il sifting: identifica posizioni con basi coincidenti.
        
        Implementa l'algoritmo BB84 sifting:
        - Solo i bit dove alice_base == bob_base sono mantenuti
        - Gli altri bit vengono scartati
        
        Args:
            measurements: Lista di misurazioni da QPM, ogni elemento contiene:
                - alice_base: base usata da Alice
                - bob_base: base usata da Bob
                - bases_match: bool indicante se le basi coincidono
                - operation_id: indice dell'operazione
        
        Returns:
            list[int]: Indici (operation_id) delle posizioni valide
        """
        valid_positions = []
        
        for idx, measurement in enumerate(measurements):
            # ✅ Controlla se le basi coincidono
            if measurement.get('bases_match', False):
                valid_positions.append(measurement.get('operation_id', idx))
        
        return valid_positions
    
    @classmethod
    async def execute(
        cls,
        node: CQKDNode,
        process_id: str,
        lk: int,
        alice_addr: str,
        bob_addr: str
    ) -> Dict[str, Any]:
        """
        Esegue l'operazione QPC: raccoglie dati da tutti i QPM e fa sifting.
        
        FLUSSO (Step 18):
        1. QPC raccoglie dati da TUTTI i QPM
           - chiave: {process_id}:qpm_to_qpc:{operation_id}
           - contiene: alice_base, bob_base, bases_match
        
        2. QPC esegue sifting (collision):
           - identifica posizioni dove alice_base == bob_base
        
        3. QPC memorizza risultati:
           - chiave: {process_id}:qpc_sifting_result
           - contiene: valid_positions (lista di indici)
        
        Args:
            node: Nodo DHT (non ha ruolo QPC assegnato, è coordinatore)
            process_id: ID del processo di generazione chiave
            lk: Numero totale di operazioni (lk)
            alice_addr: Indirizzo di Alice
            bob_addr: Indirizzo di Bob
        
        Returns:
            dict: Risultato con posizioni valide e statistiche
        """
        logger.info(
            "qpc_execute_start",
            process_id=process_id,
            lk=lk
        )
        
        # ✅ STEP 18.1: Raccogli dati da TUTTI i QPM
        measurements = []
        
        for operation_id in range(lk):
            # Attendi che QPM_i abbia memorizzato i dati
            logger.info(f"qpc sta aspettando per operation_id {operation_id}")
            qpm_key = f"{process_id}:qpm_to_qpc:{operation_id}"
            
            # Poll con timeout
            for attempt in range(240):  # 60 secondi
                measurement_data = await node.retrieve_data(qpm_key)
                
                if measurement_data:
                    # Converte da string se necessario
                    if isinstance(measurement_data, str):
                        measurement = json.loads(measurement_data)
                    else:
                        measurement = measurement_data
                    
                    measurements.append(measurement)
                    
                    logger.debug(
                        "qpc_received_measurement",
                        operation_id=operation_id,
                        bases_match=measurement.get('bases_match')
                    )
                    break
                
                # Attendi prima di ritentare
                import asyncio
                await asyncio.sleep(0.5)
            else:
                # Timeout
                logger.warning(
                    "qpc_timeout_measurement",
                    operation_id=operation_id,
                    process_id=process_id
                )
                # Aggiungi misura vuota per mantenere allineamento indici
                measurements.append({
                    "operation_id": operation_id,
                    "bases_match": False
                })
        
        logger.info(
            "qpc_all_measurements_collected",
            process_id=process_id,
            total_measurements=len(measurements)
        )
        
        # ✅ STEP 18.2: Esegui sifting (collision)
        valid_positions = cls.sift_keys(measurements)
        
        logger.info(
            "qpc_sifting_complete",
            process_id=process_id,
            total_measurements=len(measurements),
            valid_positions=len(valid_positions),
            sift_efficiency=len(valid_positions) / lk if lk > 0 else 0
        )
        
        # ✅ STEP 18.3: Memorizza risultati per Alice e Bob
        result = {
            "process_id": process_id,
            "valid_positions": valid_positions,
            "total_measurements": len(measurements),
            "sift_efficiency": len(valid_positions) / lk if lk > 0 else 0
        }
        
        # Memorizza con chiave che Alice e Bob aspettano
        sifting_key = f"{process_id}:qpc_sifting_result"
        await node.store_data(sifting_key, result)
        
        logger.info(
            "qpc_result_stored",
            process_id=process_id,
            key=sifting_key,
            valid_positions=len(valid_positions)
        )
        
        return result
    
    @classmethod
    async def collect_and_sift(
        cls,
        node: CQKDNode,
        process_id: str,
        lk: int,
        alice_addr: str = None,
        bob_addr: str = None
    ) -> List[int]:
        """
        Helper method: raccoglie dati da QPM e restituisce posizioni valide.
        
        Usato da Alice per invocare il sifting al termine delle misurazioni.
        
        Args:
            node: Nodo di Alice o coordinatore
            process_id: ID del processo
            lk: Numero totale di operazioni
            alice_addr: Indirizzo di Alice
            bob_addr: Indirizzo di Bob
        
        Returns:
            list[int]: Posizioni valide (operation_id dove basi coincidono)
        """
        result = await cls.execute(
            node=node,
            process_id=process_id,
            lk=lk,
            alice_addr=alice_addr,
            bob_addr=bob_addr
        )
        
        return result.get("valid_positions", [])
