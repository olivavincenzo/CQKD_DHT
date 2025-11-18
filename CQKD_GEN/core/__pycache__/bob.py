import asyncio
import json
from typing import List, Dict, Any
from core.dht_node import CQKDNode
from core.node_states import NodeRole
from quantum.bg import BaseGenerator
from quantum.qpm import QuantumPhotonMeter
from utils.logging_config import get_logger


logger = get_logger(__name__)


class Bob:
    """
    Bob - Ricevente nel protocollo CQKD
    Segue STEP 12-17 del paper
    """
    
    def __init__(self, node: CQKDNode):
        self.node = node
        self.bob_bases: List[str] = []
        self.bob_bits: List[int] = []
        
    async def receive_key(self, process_id: str) -> bytes:
        """
        Bob riceve e genera chiave seguendo STEP 12-17
        
        Args:
            process_id: ID del processo (Alice lo comunica)
            
        Returns:
            bytes: Chiave generata
        """
        logger.info("bob_waiting_for_alice_notification", process_id=process_id)
        
        # ========== STEP 12: Bob attende notifica da Alice ==========
        notification = await self._wait_for_alice_notification(process_id)
        
        lk = notification['lk']
        lc = notification.get('lc') 
        sorting_rule = notification['sorting_rule']
        qpm_addresses = notification['qpm_addresses']
        
        logger.info(
            "step_12_complete",
            lk=lk,
            lc=lc,
            qpm_count=len(qpm_addresses)
        )
        
        # ========== STEP 13: Bob genera basi casuali ==========
        self.bob_bases = BaseGenerator.generate_base_sequence(lk)
        
        logger.info("step_13_complete", bob_bases_count=len(self.bob_bases))
        
        # ========== STEP 14-15: Bob misura fotoni dai QPM ==========
        measurements = []
        tasks = []
        
        for i in range(lk):
            original_index = sorting_rule[i]  # Applica sorting rule
            task = self._measure_photon(
                process_id,
                original_index,  # Usa indice originale per chiave DHT
                qpm_addresses[original_index],
                self.bob_bases[i]
            )
            tasks.append(task)
        
        measurement_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verifica errori
        errors = [r for r in measurement_results if isinstance(r, Exception)]
        if errors:
            logger.error("bob_measurement_errors", error_count=len(errors))
            # Log primi 3 errori per debug
            for err in errors[:3]:
                logger.error("measurement_error_detail", error=str(err))
            raise RuntimeError(f"Errori durante misurazioni: {len(errors)}")
        
        
        # Ricostruisci l'elenco dei bit di Bob nell'ordine originale,
        # dato che i risultati di `asyncio.gather` non hanno un ordine garantito.
        # Ogni risultato di misurazione contiene il suo indice originale.
        original_order_bits = [0] * lk
        for measurement in measurement_results:
            # L'indice originale è nell'oggetto 'measurement' stesso
            original_idx = measurement['index']
            original_order_bits[original_idx] = measurement['measured_bit']

        self.bob_bits = original_order_bits  # Ora i bit di Bob sono nello stesso ordine di quelli originali di Alice
        measurements = measurement_results

        logger.info(
            "step_14_15_complete",
            measurements_count=len(self.bob_bits),
            successful=len([r for r in measurements if not isinstance(r, Exception)])
        )
        
        # ========== STEP 16-17: Bob invia misurazioni al QPC ==========
        # Scrivi misurazioni nella DHT per il QPC
        for measurement in measurements:
            idx = measurement['index']
            key = f"{process_id}:qpm:{idx}:measurement"
            await self.node.store_data(key, json.dumps(measurement))
        
        logger.info("step_16_17_complete", measurements_sent=len(measurements))
        
        # ========== STEP 18: Bob attende risultati QPC ==========
        valid_positions = await self._wait_for_qpc_results(process_id)
        
        logger.info(
            "step_18_complete",
            valid_positions_count=len(valid_positions),
            sift_ratio=len(valid_positions) / lk if lk > 0 else 0
        )
        
        # ========== STEP 19: Bob genera chiave finale ==========
        sifted_bits = [self.bob_bits[i] for i in valid_positions if i < len(self.bob_bits)]

        if len(sifted_bits) < lc:
            raise ValueError(
                f"Bit insufficienti dopo sifting: "
                f"richiesti {lc}, ottenuti {len(sifted_bits)}"
            )
        

        final_key_bits = sifted_bits[:lc]
        
        from protocol.key_generation import KeyGenerationOrchestrator
        key_bytes = KeyGenerationOrchestrator.bits_to_bytes(final_key_bits)
        
        logger.info(
            "bob_key_generation_complete",
            process_id=process_id,
            final_key_length_bits=len(final_key_bits),
            final_key_length_bytes=len(key_bytes)
        )
        
        return key_bytes
    
    async def _wait_for_alice_notification(self, process_id: str) -> Dict[str, Any]:
        """
        STEP 12: Attende notifica da Alice
        
        Returns:
            Dict con lk, sorting_rule, qpm_addresses
        """
        key = f"{process_id}:alice_to_bob:notification"
        
        # Polling con timeout
        max_attempts = 30
        for attempt in range(max_attempts):
            notification_str = await self.node.retrieve_data(key)
            if notification_str:
                notification = json.loads(notification_str)
                logger.info("alice_notification_received", lk=notification.get('lk'))
                return notification
            
            await asyncio.sleep(0.5)
        
        raise TimeoutError("Timeout waiting for Alice notification")
    
    async def _measure_photon(
        self,
        process_id: str,
        index: int,
        qpm_node_id: str,
        bob_base: str
    ) -> Dict[str, Any]:
        """
        STEP 14-15: Misura un singolo fotone
        
        Returns:
            Dict con risultato misurazione
        """
        # Recupera polarizzazione da Alice (scritta da QPP)
        key = f"{process_id}:qpp:photon_{index}:to_qpm:{qpm_node_id}"
        
        # Polling per aspettare dati da Alice
        alice_data = None
        for _ in range(20):  # 10 secondi max
            data_str = await self.node.retrieve_data(key)
            if data_str:
                alice_data = json.loads(data_str)
                break
            await asyncio.sleep(0.5)
        
        if alice_data is None:
            raise ValueError(f"Polarizzazione non ricevuta per fotone {index}")
        
        alice_polarization = alice_data.get('polarization')
        alice_base = alice_data.get('alice_base')
        
        # Esegui misurazione quantistica
        measured_bit, bases_match = QuantumPhotonMeter.measure(
            alice_polarization,
            bob_base
        )
        
        return {
            "index": index,
            "measured_bit": measured_bit,
            "bob_base": bob_base,
            "alice_base": alice_base,
            "alice_polarization": alice_polarization,
            "bases_match": bases_match,
            "qpm_node": qpm_node_id
        }
    
    async def _wait_for_qpc_results(self, process_id: str) -> List[int]:
        """
        STEP 18: Attende risultati dal QPC
        
        Returns:
            List[int]: Posizioni valide (basi coincidenti)
        """
        key = f"{process_id}:qpc:collision:valid_positions_bob"
        
        # Polling con timeout
        max_attempts = 60
        for attempt in range(max_attempts):
            result_str = await self.node.retrieve_data(key)
            if result_str:
                # Parse lista da stringa
                import ast
                valid_positions = ast.literal_eval(result_str)
                return valid_positions
            
            await asyncio.sleep(1)
        
        raise TimeoutError("Timeout waiting for QPC collision results")



from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks
import uvicorn
from pydantic import BaseModel
import os
import asyncio

# Variabili globali per il nodo e il protocollo
bob_node: Optional[CQKDNode] = None
bob_protocol: Optional[Bob] = None

def get_bootstrap_nodes():
    """Legge e formatta i nodi di bootstrap dalle variabili d'ambiente."""
    bootstrap_nodes_str = os.getenv("BOOTSTRAP_NODES")
    if not bootstrap_nodes_str:
        logger.error("✗ La variabile d'ambiente BOOTSTRAP_NODES è richiesta.")
        raise ValueError("BOOTSTRAP_NODES non impostata")
    
    nodes = []
    for addr in bootstrap_nodes_str.split(','):
        host, port = addr.strip().split(':')
        nodes.append((host, int(port)))
    return nodes

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestisce il ciclo di vita dell'applicazione FastAPI."""
    global bob_node, bob_protocol
    
    port = int(os.getenv("DHT_PORT", 6001))
    bootstrap_nodes = get_bootstrap_nodes()
    
    logger.info(f"Avvio Bob Service su porta {port}...")
    bob_node = CQKDNode(port=port, node_id="bob")
    await bob_node.start()
    await bob_node.bootstrap(bootstrap_nodes)
    
    bob_protocol = Bob(bob_node)
    logger.info("✓ Bob Service pronto e connesso alla DHT.")
    
    yield
    
    logger.info("Shutdown Bob Service...")
    if bob_node:
        await bob_node.stop()

app = FastAPI(title="Bob Controller Service", version="1.0.0", lifespan=lifespan)

@app.get("/health", summary="Health Check")
async def health():
    """Controlla lo stato del servizio di Bob."""
    if not bob_protocol or not bob_node:
        raise HTTPException(status_code=503, detail="Bob controller non inizializzato")
    return {"status": "healthy", "node_id": bob_node.node_id}

class ProcessIdRequest(BaseModel):
    process_id: str

@app.post("/receive-key", status_code=202, summary="Avvia la ricezione della chiave")
async def receive_key_endpoint(req: ProcessIdRequest, background_tasks: BackgroundTasks):
    """
    Endpoint per avviare il processo di ricezione della chiave in background.
    """
    if not bob_protocol:
        raise HTTPException(status_code=503, detail="Bob controller non inizializzato.")
    
    logger.info(f"Richiesta API ricevuta: avvio ricezione chiave per process_id: {req.process_id}")
    
    # Esegui il lungo processo di ricezione in background
    background_tasks.add_task(bob_protocol.receive_key, req.process_id)
    
    return {"status": "Key reception process started in background", "process_id": req.process_id}

if __name__ == "__main__":
    # La porta 8000 è quella interna al container. Sarà mappata nel docker-compose.
    uvicorn.run(app, host="0.0.0.0", port=8000)
