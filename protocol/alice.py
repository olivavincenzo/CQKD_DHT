import asyncio
import secrets
import json
from typing import List, Dict, Any, Optional, Tuple
from core.dht_node import CQKDNode
from core.node_states import NodeRole
from protocol.key_generation import KeyGenerationOrchestrator
from quantum.qsg import QuantumSpinGenerator
from quantum.bg import BaseGenerator
from quantum.qpp import QuantumPhotonPolarizer
import datetime
from utils.logging_config import get_logger

logger = get_logger(__name__)


class Alice:
    """
    Alice - Implementazione COMPLETA seguendo TUTTI i 19 step del paper
    """
    
    def __init__(self, node: CQKDNode, bob_address: str):
        self.node = node
        self.process_id = None
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
        
        
        try:       
            # ========== STEP 1: Alice calcola lk = |2.5 * lc| ==========
            requirements = self.orchestrator.calculate_required_nodes(desired_length_bits)
            lk = requirements['initial_key_length']
            lc = desired_length_bits
            alpha = requirements['total']
            
            logger.info("step_1_complete", lc=lc, lk=lk, alpha=alpha)
            
            # ========== STEP 2: Alice ping nodi e verifica #(n) >= 5lk ==========
            if available_nodes is None:
                available_nodes = await self.orchestrator.discover_available_nodes(
                    required_count=alpha,
                    required_capabilities=None,  # Tutte le capacità per massima flessibilità
                    max_retries=3  # NUOVO: Aumenta retry per discovery robusto
                )
            
            # ========== STEP 3: Alice ping nodi e verifica #(n) >= 5lk ==========
            
            if len(available_nodes) < alpha:
                raise ValueError(
                    f"Nodi insufficienti: richiesti {requirements['total']}, "
                    f"disponibili {len(available_nodes)}"
                )
            
            logger.info("step_2", available_nodes=len(available_nodes))
            
            # ========== STEP 4: Alice alloca nodi QSG, BG, QPP, QPM, QPC ==========
            allocation = await self.orchestrator.allocate_nodes(
                available_nodes,
                requirements
            )

            logger.info(f"!allocation: {allocation}")
            
            # ========== STEP 5: Alice apre process_id unico ==========
            process_id = self.orchestrator.process_id
            self.process_id = process_id
            logger.info("step_7_complete", process_id=process_id)

            # ========== STEP 6: DISPATCH commands to worker nodes ==========
            await self._dispatch_quantum_operations(lk, allocation)
            
            # ========== STEP 7 (continued): COLLECT results from worker nodes =====
            await self._collect_quantum_results(lk)

            logger.info(
                "step_8_9_quantum_data_collected_from_workers",
                bits=len(self.alice_bits),
                bases=len(self.alice_bases)
            )

            # ========== STEP 10: Random shuffling for security =====
            indices = list(range(lk))
            shuffled_indices = indices.copy()
            secrets.SystemRandom().shuffle(shuffled_indices)
            self.sorting_rule = shuffled_indices
            
            # Apply shuffling to ALL Alice's data
            self.alice_bits = [self.alice_bits[i] for i in shuffled_indices]
            self.alice_bases = [self.alice_bases[i] for i in shuffled_indices]
            
            logger.info(
                "step_10_random_shuffling_applied",
                sorting_rule_sample=self.sorting_rule[:5]
            )
            
            shuffled_data={
                "lk": lk,
                "lc": lc,
                "alice_bases": self.alice_bases,
                "alice_bits": self.alice_bits,
                "shuffled": True,
                "timestamp": datetime.now().isoformat()
            }
            
            # Store shuffled data for QPM nodes
            await self.node.store_data(
                f"{process_id}:alice_shuffled_data",
                json.dumps(shuffled_data)
    
            )

            # ===== STEP 11: Notify Bob =====
            await self._notify_bob(
                process_id,
                lk, 
                lc, 
                self.sorting_rule, 
                self.alice_bases, 
                allocation
            )
            logger.info("step_11_bob_notified")

            
            # ========== STEP 12-15: Attendi che Bob completi le misurazioni ==========
            logger.info("waiting_for_bob_and_qpc")
            valid_positions = await self._wait_for_qpc_sifting()
            
            logger.info(
                "step_18_sifting_complete",
                valid_positions=len(valid_positions),
                sift_ratio=len(valid_positions) / lk if lk > 0 else 0
            )
            
            # ===== STEP 19: Extract final key from valid positions =====
            sifted_bits = [
                self.alice_bits[i] for i in valid_positions
                if i < len(self.alice_bits)
            ]
            
            if len(sifted_bits) < lc:
                logger.warning(
                    "insufficient_bits_after_sifting",
                    required=lc,
                    available=len(sifted_bits)
                )
                # Use what we have
                final_key_bits = sifted_bits
            else:
                final_key_bits = sifted_bits[:lc]
            
            key_bytes = self.orchestrator.bits_to_bytes(final_key_bits)
            
            logger.info(
                "step_19_final_key_extracted",
                key_bits=len(final_key_bits),
                key_bytes=len(key_bytes)
            )
            
            await self.orchestrator.complete_process(success=True)
            logger.info(
                "alice_19step_protocol_complete",
                process_id=process_id,
                key_length=len(key_bytes)
            )
            
            return key_bytes
    
        except Exception as e:
                logger.error(
                    "alice_protocol_failed",
                    error=str(e),
                    process_id=process_id,
                    exc_info=True
                )
                
                if process_id:
                    await self.orchestrator.complete_process(
                        success=False,
                        error_message=str(e)
                    )
                
                raise
        finally:
            await self.orchestrator.stop()
        

    async def _dispatch_quantum_operations(
            self, 
            lk: int, 
            allocation: Dict[NodeRole, List[str]]
        ):
            """
            STEP 8: Dispatch commands to worker nodes for quantum operations.
            Alice sends commands via DHT, workers execute them.
            """
            logger.info(
                "dispatching_quantum_operations_to_workers",
                lk=lk
            )
            
            qsg_nodes = allocation.get(NodeRole.QSG, [])
            bg_nodes = allocation.get(NodeRole.BG, [])
            qpp_nodes = allocation.get(NodeRole.QPP, [])
            
            # Dispatch commands to each worker node
            dispatch_tasks = []
            
            for i in range(lk):
                # Command to QSG node
                qsg_node_id = qsg_nodes[i % len(qsg_nodes)]
                qsg_cmd = {
                    "cmd_id": f"{self.process_id}_qsg_{i}",
                    "process_id": self.process_id,
                    "role": NodeRole.QSG.value,
                    "operation_id": i,
                    "params": {
                        "process_id": self.process_id,
                        "operation_id": i,
                        "alice_addr": self.node.node_id,
                        "qpp_addr": qpp_nodes[i % len(qpp_nodes)]
                    }
                }
                
                # Command to BG node (for Alice's base)
                bg_node_id = bg_nodes[i % len(bg_nodes)]
                bg_cmd = {
                    "cmd_id": f"{self.process_id}_bg_alice_{i}",
                    "process_id": self.process_id,
                    "role": NodeRole.BG.value,
                    "operation_id": i,
                    "params": {
                        "process_id": self.process_id,
                        "operation_id": i,
                        "bob_addr": None,  # For Alice
                        "qpm_addr": None
                    }
                }
                
                # Send commands to workers via DHT
                


                key_qsg=f"cmd:{qsg_node_id.get('id')}"
                key_bg=f"cmd:{bg_node_id.get('id')}"
                logger.info(f"Contatto il nodo qsg con: {key_qsg}")
                logger.info(f"Contatto il nodo bg con: {key_bg}")


                dispatch_tasks.append(
                    self.node.store_data(key_qsg, json.dumps(qsg_cmd))
                )

                dispatch_tasks.append(
                    self.node.store_data(key_bg, json.dumps(bg_cmd))
                )
            
            # Wait for all commands to be dispatched
            await asyncio.gather(*dispatch_tasks)
            
            logger.info(
                "quantum_operations_dispatched",
                process_id=self.process_id,
                commands_sent=len(dispatch_tasks)
            )


    async def _collect_quantum_results(self, lk: int):
        """
        STEP 9: Collect results from worker nodes.
        Alice waits for workers to write results to DHT.
        """
        logger.info(
            "collecting_quantum_results_from_workers",
            process_id=self.process_id,
            lk=lk
        )
        
        self.alice_bits = []
        self.alice_bases = []
        
        # Collect results with timeout
        for i in range(lk):
            # Wait for QSG result
            qsg_result = await self._wait_for_result(
                f"{self.process_id}:qsg_result:{i}",
                timeout=30
            )
            self.alice_bits.append(qsg_result.get("spin", 0))
            
            # Wait for BG result (Alice's base)
            bg_result = await self._wait_for_result(
                f"{self.process_id}:bg_alice_result:{i}",
                timeout=30
            )
            self.alice_bases.append(bg_result.get("base", "+"))
        
        logger.info(
            "quantum_results_collected",
            process_id=self.process_id,
            bits=len(self.alice_bits),
            bases=len(self.alice_bases)
        )

    async def _wait_for_result(
        self, 
        key: str, 
        timeout: int = 30
    ) -> Dict[str, Any]:
        """
        Wait for a specific result to appear in DHT.
        
        Args:
            key: DHT key to wait for
            timeout: Maximum seconds to wait
            
        Returns:
            Result data from DHT
        """
        for attempt in range(timeout * 2):  # Poll every 0.5 seconds
            result = await self.node.retrieve_data(key)
            
            if result:
                return result
            
            await asyncio.sleep(0.5)
            
            if (attempt + 1) % 10 == 0:
                logger.debug(
                    "still_waiting_for_result",
                    key=key,
                    attempt=attempt + 1
                )
        
        raise TimeoutError(f"Timeout waiting for result: {key}")

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

    async def _wait_for_qpc_sifting(self) -> List[int]:
        """
        Wait for QPC to complete sifting (step 18).
        
        Returns:
            List[int]: Valid bit positions where bases matched
        """
        logger.info("alice_waiting_for_qpc_sifting", process_id=self.process_id)
        
        for attempt in range(120):  # 1 minute timeout
            # Try process-specific key
            result = await self.node.retrieve_data(
                f"{self.process_id}:qpc_sifting_result"
            )
            
            if result and "valid_positions" in result:
                logger.info(
                    "alice_received_qpc_sifting",
                    attempt=attempt,
                    valid_positions=len(result["valid_positions"])
                )
                return result["valid_positions"]
            
            # Try latest key
            result = await self.node.retrieve_data("latest_qpc_sifting_result")
            if result and "valid_positions" in result:
                if result.get("process_id") == self.process_id:
                    return result["valid_positions"]
            
            await asyncio.sleep(0.5)
            
            if (attempt + 1) % 10 == 0:
                logger.debug(
                    "alice_still_waiting_qpc",
                    attempt=attempt + 1
                )
        
        raise TimeoutError("Timeout waiting for QPC sifting results")

    async def _notify_bob(
        self,
        process_id: str,
        lk: int,
        lc: int,
        sorting_rule: List[int],
        alice_bases: List[str],
        allocation: dict
    ):

        notification_data = {
            "process_id": self.process_id,
            "lc": lc,
            "lk": lk,
            "sorting_rule": sorting_rule,
            "alice_bases": alice_bases,
            "qpm_nodes": allocation.get(NodeRole.QPM, []),
            "qpc_node": allocation.get(NodeRole.QPC, [None])[0],
            "alice_node": self.node.node_id,
            "timestamp": datetime.now().isoformat()
        }
        key = f"{process_id}:alice_to_bob"
        await self.node.store_data(key, json.dumps(notification_data)) 
        
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



import socket
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks
import uvicorn
from pydantic import BaseModel
import os

async def resolve_bootstrap_nodes(bootstrap_nodes_raw: List[Tuple[str, int]]) -> List[Tuple[str, int]]:
    resolved_nodes = []
    for host, port in bootstrap_nodes_raw:
        try:
            addr_info = await asyncio.get_event_loop().getaddrinfo(
                host, port, type=socket.SOCK_DGRAM
            )
            ip_address = addr_info[0][-1][0]
            resolved_nodes.append((ip_address, port))
            logger.info(f"Resolved bootstrap node: {host}:{port} -> {ip_address}:{port}")
        except socket.gaierror as e:
            logger.error(f"Failed to resolve bootstrap host {host}: {e}")
            # If resolution fails, it's a critical error for bootstrapping
            raise
    return resolved_nodes

@asynccontextmanager
async def lifespan(app: FastAPI):
    global alice_node
    port = int(os.getenv("DHT_PORT", 6000))
    bootstrap_nodes_str = os.getenv("BOOTSTRAP_NODES")
    node_id = "alice"
    
    bootstrap_nodes_raw = [(host, int(b_port)) for host, b_port in (addr.strip().split(':') for addr in bootstrap_nodes_str.split(','))]
    resolved_bootstrap_nodes = await resolve_bootstrap_nodes(bootstrap_nodes_raw)

    logger.info(f"Avvio Alice node '{node_id}' su porta {port}...")
    alice_node = CQKDNode(port=port, node_id=node_id)
    await alice_node.start()
    await alice_node.bootstrap(resolved_bootstrap_nodes) # Use resolved nodes
    logger.info(f"✓ Alice node '{node_id}' connessa alla rete DHT.")
    

    try:
        yield
    except Exception as e:
        logger.error(f"✗ Errore nel servizio Alice durante l'esecuzione: {e}", exc_info=True)
        logger.info("Alice rimane attiva nonostante l'errore...")
        # Non fermare il servizio anche in caso di errore
        yield
    finally:
        # NOTA: Non fermiamo alice_node per mantenere il container in esecuzione
        logger.info("Alice lifespan completato, ma il nodo rimane attivo per operazioni continue...")
        if alice_node:
            logger.info("Alice node mantenuto attivo per operazioni continue...")
            # await alice_node.stop()  # Commentato per mantenere il nodo attivo

app = FastAPI(title="Alice Controller Service", version="1.0.0", lifespan=lifespan)


class KeyRequest(BaseModel):
    desired_key_length: int

@app.post("/generate-key", status_code=202)
async def generate_key(req: KeyRequest):
    """Endpoint to start the key generation process."""

    desired_key_length= req.desired_key_length
    bob_address = os.getenv("BOB_DHT_ADDRESS")
    alice_protocol = Alice(alice_node, bob_address=bob_address)

    PROCESS_ID_KEY = "cqkd_process_id"
    process_id = alice_protocol.orchestrator.process_id

    await alice_node.store_data(PROCESS_ID_KEY, process_id)
    logger.info(f"Alice pubblica il process_id '{process_id}' sulla chiave DHT '{PROCESS_ID_KEY}' per Bob...")

    logger.info("✓ process_id pubblicato.")

    # Avvia la generazione della chiave
    logger.info(f"Alice avvia la generazione di una chiave a {desired_key_length} bit...")
    
    alice_key = await alice_protocol.generate_key(desired_length_bits=desired_key_length)

    if alice_key:
        logger.info(f"SUCCESS! Alice ha generato la chiave: {alice_key.hex()}")
    else:
        logger.error("✗ Alice non è riuscita a generare la chiave.")

    return {"status": "Key generata"}

@app.get("/network-status")
async def get_network_status():
    """Endpoint per monitorare lo stato della rete DHT"""
    try:
        routing_info = alice_node.get_routing_table_info()

        # Calcola statistiche aggiuntive
        total_capacity = routing_info.get("total_buckets", 0) * routing_info.get("bucket_capacity", 20)
        usage_percentage = (routing_info.get("total_nodes", 0) / total_capacity * 100) if total_capacity > 0 else 0

        status = {
            "node_id": alice_node.node_id,
            "routing_table": routing_info,
            "network_metrics": {
                "total_nodes": routing_info.get("total_nodes", 0),
                "active_buckets": routing_info.get("active_buckets", 0),
                "capacity_usage_percentage": round(usage_percentage, 2),
                "network_health": routing_info.get("network_health", {}),
                "discovery_ready": routing_info.get("network_health", {}).get("well_distributed", False)
            }
        }

        return status
    except Exception as e:
        logger.error("network_status_error", error=str(e))
        return {"error": str(e), "status": "error"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
