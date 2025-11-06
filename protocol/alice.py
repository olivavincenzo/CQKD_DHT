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
    Alice - Implementazione COMPLETA seguendo i 19 step del paper (Sezione 4)
    
    APPROCCIO 2: Decentralizzazione totale - BG genera le basi di Alice
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
            
            # ========== STEP 2-3: Alice ping nodi e verifica #(n) >= 5lk ==========
            if available_nodes is None:
                available_nodes = await self.orchestrator.discover_available_nodes(
                    required_count=alpha,
                    required_capabilities=None,
                    max_retries=3
                )
            
            if len(available_nodes) < alpha:
                raise ValueError(
                    f"Nodi insufficienti: richiesti {alpha}, "
                    f"disponibili {len(available_nodes)}"
                )
            
            logger.info("step_2_3_complete", available_nodes=len(available_nodes))
            
            # ========== STEP 4-6: Alice alloca nodi QSG, BG, QPP, QPM, QPC ==========
            allocation = await self.orchestrator.allocate_nodes(
                available_nodes,
                requirements
            )
            
            logger.info(
                "step_4_5_6_complete",
                qsg=len(allocation.get(NodeRole.QSG, [])),
                bg=len(allocation.get(NodeRole.BG, [])),
                qpp=len(allocation.get(NodeRole.QPP, [])),
                qpm=len(allocation.get(NodeRole.QPM, [])),
                qpc=len(allocation.get(NodeRole.QPC, []))
            )
            
            # ========== STEP 7: Alice apre process_id unico ==========
            process_id = self.orchestrator.process_id
            self.process_id = process_id
            logger.info("step_7_complete", process_id=process_id)
            
            # ========== STEP 8: Alice comanda i nodi (QSG, BG_A, QPP) ==========
            await self._dispatch_quantum_operations(lk, allocation)
            logger.info("step_8_dispatch_complete")
            
            # ========== STEP 9: Alice raccoglie risultati (spin da QSG, basi da BG) ==========
            await self._collect_quantum_results(lk)
            logger.info(
                "step_9_collect_complete",
                bits=len(self.alice_bits),
                bases=len(self.alice_bases)
            )
            
            # ========== STEP 10: Alice genera NUOVO ORDINE CASUALE (sorting rule) ==========
            indices = list(range(lk))
            shuffled_indices = indices.copy()
            secrets.SystemRandom().shuffle(shuffled_indices)
            self.sorting_rule = shuffled_indices
            
            # Applica shuffling ai dati di Alice
            self.alice_bits = [self.alice_bits[i] for i in shuffled_indices]
            self.alice_bases = [self.alice_bases[i] for i in shuffled_indices]
            
            logger.info(
                "step_10_shuffling_complete",
                sorting_rule_sample=self.sorting_rule[:5]
            )
            
            # ========== STEP 11: Alice notifica Bob (lk, sorting_rule, QPM addresses) ==========
            await self._notify_bob(
                process_id,
                lk,
                lc,
                self.sorting_rule,
                self.alice_bases,
                allocation
            )
            logger.info("step_11_bob_notified")
            
            # ========== STEP 12-17: Attendi che Bob completi (Bob esegue in parallelo) ==========
            # Bob farà step 12-15: ping nodi, alloca BG_B, genera basi
            # Bob farà step 16-17: QPM misura, invia a Bob e QPC
            
            logger.info("waiting_for_bob_and_qpc")
            


                
            # ========== STEP 18: Invoca QPC per il sifting ==========
            from quantum.qpc import QuantumPhotonCollider
            
            logger.info("step_18_invoking_qpc", process_id=self.process_id, lk=lk)
            
            await QuantumPhotonCollider.execute(
                node=self.node,
                process_id=self.process_id,
                lk=lk,
                alice_addr=self.node.node_id,
                bob_addr=self.bob_address
            )

            logger.info("step_18_qpc_invoked") 

            # ========== STEP 18: Attendi QPC collision ==========

            valid_positions = await self._wait_for_qpc_sifting()
            
            logger.info(
                "step_18_qpc_sifting_complete",
                valid_positions=len(valid_positions),
                sift_ratio=len(valid_positions) / lk if lk > 0 else 0
            )
            



            # ========== STEP 19: Alice ordina secondo sorting_rule e cancella bit errati ==========
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
                process_id=self.process_id,
                exc_info=True
            )
            
            if self.process_id:
                await self.orchestrator.complete_process(
                    success=False,
                    error_message=str(e)
                )
            
            raise
        finally:
            await self.orchestrator.stop()
    
# alice.py - APPROCCIO 2 CON COMANDI ESPLICITI A TUTTI I NODI

    async def _dispatch_quantum_operations(
        self,
        lk: int,
        allocation: Dict[NodeRole, List[str]]
    ):
        """
        STEP 8: Alice comanda TUTTI i nodi quantistici.
        
        Secondo il paper (Step 8): "Alice trasmette comandi ai nodi"
        Questo significa che Alice invia comandi espliciti a:
        - QSG: genera spin
        - BG: genera base
        - QPP: calcola polarizzazione
        - QPM: misura
        """
        logger.info("dispatching_quantum_operations", lk=lk)
        
        qsg_nodes = allocation.get(NodeRole.QSG, [])
        bg_nodes = allocation.get(NodeRole.BG, [])
        qpp_nodes = allocation.get(NodeRole.QPP, [])
        qpm_nodes = allocation.get(NodeRole.QPM, [])
      
        
        logger.info(f"qsg_nodes: {qsg_nodes}")
        logger.info(f"bg_nodes: {bg_nodes}")
        logger.info(f"qpp_nodes: {qpp_nodes}")
        logger.info(f"qpm_nodes: {qpm_nodes}")

        


        
        dispatch_tasks = []
        
        for i in range(lk):
            qsg_node_id = qsg_nodes[i % len(qsg_nodes)]
            bg_node_id = bg_nodes[i % len(bg_nodes)]
            qpp_node_id = qpp_nodes[i % len(qpp_nodes)]
            qpm_node_id = qpm_nodes[i % len(qpm_nodes)]
            
            # ===== COMANDO 1: QSG =====
            qsg_cmd = {
                "cmd_id": f"{self.process_id}_qsg_{i}",
                "process_id": self.process_id,
                "role": NodeRole.QSG.value,
                "operation_id": i,
                "params": {
                    "process_id": self.process_id,
                    "operation_id": i,
                    "alice_addr": self.node.node_id,
                    "qpp_addr": qpp_node_id.get('id')
                }
            }
            
            # ===== COMANDO 2: BG (per Alice) =====
            bg_cmd = {
                "cmd_id": f"{self.process_id}_bg_alice_{i}",
                "process_id": self.process_id,
                "role": NodeRole.BG.value,
                "operation_id": i,
                "params": {
                    "process_id": self.process_id,
                    "operation_id": i,
                    "owner": "alice",
                    "alice_addr": self.node.node_id,
                    "qpp_addr": qpp_node_id.get('id'),
                    "qpm_addr": qpm_node_id.get('id')
                }
            }
            
            # ===== COMANDO 3: QPP =====
            # QPP leggerà spin da QSG e base da BG dalla DHT
            qpp_cmd = {
                "cmd_id": f"{self.process_id}_qpp_{i}",
                "process_id": self.process_id,
                "role": NodeRole.QPP.value,
                "operation_id": i,
                "params": {
                    "process_id": self.process_id,
                    "operation_id": i,
                    "qpm_addr": qpm_node_id.get('id')
                }
            }
            
            # ===== COMANDO 4: QPM =====
            # QPM leggerà polarizzazione da QPP e base_bob da BG_B dalla DHT
            qpm_cmd = {
                "cmd_id": f"{self.process_id}_qpm_{i}",
                "process_id": self.process_id,
                "role": NodeRole.QPM.value,
                "operation_id": i,
                "params": {
                    "process_id": self.process_id,
                    "operation_id": i,
                    "bob_addr": self.bob_address
                }
            }
            

            logger.info(f"[{i}] contatto questo nodo qsg: {qsg_node_id.get('id')}")
            logger.info(f"[{i}] contatto questo nodo bg: {bg_node_id.get('id')}")
            logger.info(f"[{i}] contatto questo nodo qpp: {qpp_node_id.get('id')}")
            logger.info(f"[{i}] contatto questo nodo qpm: {qpm_node_id.get('id')}")
            dispatch_tasks.extend([
                self.node.store_data(f"cmd:{qsg_node_id.get('id')}", json.dumps(qsg_cmd)),
                self.node.store_data(f"cmd:{bg_node_id.get('id')}", json.dumps(bg_cmd)),

                self.node.store_data(f"cmd:{qpp_node_id.get('id')}", json.dumps(qpp_cmd)),

                self.node.store_data(f"cmd:{qpm_node_id.get('id')}", json.dumps(qpm_cmd))
            ])
        
        await asyncio.gather(*dispatch_tasks)
        
        logger.info(
            "quantum_operations_dispatched",
            commands_sent=len(dispatch_tasks),
            qsg=lk,
            bg=lk,
            qpp=lk,
            qpm=lk
        )


    
    async def _collect_quantum_results(self, lk: int):
        """
        STEP 9: Collect results from worker nodes.
        
        Alice raccoglie:
        - Spin da QSG_i
        - Basi da BG_A,i (generate dai worker, non localmente!)
        """
        logger.info("collecting_quantum_results", lk=lk)
        
        self.alice_bits = []
        self.alice_bases = []
        
        for i in range(lk):
            # Raccogli spin da QSG
            qsg_result = await self._wait_for_result(
                f"{self.process_id}:qsg_result:{i}",
                timeout=30
            )
            self.alice_bits.append(qsg_result.get("spin", 0))
            
            # ✅ Raccogli base da BG (generata dal worker!)
            bg_result = await self._wait_for_result(
                f"{self.process_id}:bg_alice_result:{i}",
                timeout=30
            )
            self.alice_bases.append(bg_result.get("base", "+"))
        
        logger.info(
            "quantum_results_collected",
            bits=len(self.alice_bits),
            bases=len(self.alice_bases)
        )

    
    async def _wait_for_result(
        self,
        key: str,
        timeout: int = 30
    ) -> Dict[str, Any]:
        """Wait for a specific result to appear in DHT."""
        for attempt in range(timeout * 2):
            result = await self.node.retrieve_data(key)
            if result:
                return result
            
            await asyncio.sleep(0.5)
            
            if (attempt + 1) % 10 == 0:
                logger.debug("still_waiting_for_result", key=key, attempt=attempt + 1)
        
        raise TimeoutError(f"Timeout waiting for result: {key}")
    
    async def _wait_for_qpc_sifting(self) -> List[int]:
        """STEP 18: Wait for QPC to complete sifting."""
        logger.info("alice_waiting_for_qpc_sifting", process_id=self.process_id)
        
        for attempt in range(120):
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
            
            await asyncio.sleep(0.5)
            
            if (attempt + 1) % 10 == 0:
                logger.debug("alice_still_waiting_qpc", attempt=attempt + 1)
        
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
        """STEP 11: Alice notifica Bob con lk, sorting_rule, indirizzi QPM."""
        notification_data = {
            "process_id": process_id,
            "lc": lc,
            "lk": lk,
            "sorting_rule": sorting_rule,
            "alice_bases": alice_bases,
            "qpm_nodes": allocation.get(NodeRole.QPM, []),
            "qpc_node": allocation.get(NodeRole.QPC, [None])[0],
            "bg_nodes": allocation.get(NodeRole.BG, []), 
            "alice_node": self.node.node_id,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        key = f"{process_id}:alice_to_bob"
        await self.node.store_data(key, json.dumps(notification_data))
        
        logger.info("alice_notified_bob", process_id=process_id, lk=lk)




import socket
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks,Query
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
        logger.info("Refresh_table start!")

        refresh_ids= alice_node.server.protocol.get_refresh_ids()
        logger.info(f"refresh_ids {refresh_ids}")
        await alice_node.server._refresh_table()
        logger.info("Refresh_table completato!")
        routing_info = alice_node.get_routing_table_info()

        # Extract nodes, sort by port, and format
        nodes_list = routing_info.get("all_nodes", [])
        
        # Sort nodes by port in ascending order
        nodes_list.sort(key=lambda n: int(n["address"].split(":")[1]))

        


        # Calcola statistiche aggiuntive
        total_capacity = routing_info.get("total_buckets", 0) * routing_info.get("bucket_capacity", 20)
        usage_percentage = (routing_info.get("total_nodes", 0) / total_capacity * 100) if total_capacity > 0 else 0

        status = {
            "node_id": alice_node.node_id,
            "nodi>7000": nodes_list, # New key for sorted and formatted nodes
            "network_metrics": {
                "total_nodes":routing_info.get("total_nodes",0),
                "tutti_nodi": routing_info.get("buckets_detail",0),
                "bucket_capacity": routing_info.get("bucket_capacity",0),
                "active_buckets": routing_info.get("active_buckets", 0),
                "bucket_distribution": routing_info.get("bucket_distribution",0),
                "capacity_usage_percentage": round(usage_percentage, 2),
                "network_health": routing_info.get("network_health", {}),
                "discovery_ready": routing_info.get("network_health", {}).get("well_distributed", False)
            }
        }

        return status
    except Exception as e:
        logger.error("network_status_error", error=str(e))
        return {"error": str(e), "status": "error"}


@app.get("/get")
async def get_value(key: str = Query(..., min_length=1, description="La chiave da cercare nella DHT")):
    """
    Endpoint per fare get su Kademlia.

    Query parameter:
    - key: la chiave da cercare nella DHT (obbligatoria)
    """
    try:
        # effettua la richiesta alla DHT; `alice_node` dovrebbe essere visibile nel modulo
        # Se alice_node.server.get è sincrona, rimuovi `await`.
        value: Optional[Any] = await alice_node.server.get(key)

        if value is None:
            # Nessun valore trovato per la chiave
            return {"status": "not_found", "key": key, "value": None}
        else:
            # Valore trovato — restituisci il payload così com'è (serializzabile in JSON)
            return {"status": "ok", "key": key, "value": value}
    except Exception as e:
        # log dell'errore per debug
        logger.exception("Errore durante la ricerca della chiave nella rete Kademlia")
        # Risposta d'errore
        raise HTTPException(status_code=500, detail=f"Errore interno: {str(e)}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
