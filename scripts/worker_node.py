
import asyncio
import os
import secrets
import time
from typing import List, Tuple
from core.dht_node import CQKDNode
from utils.logging_config import setup_logging, get_logger
from protocol.worker import WorkerExecutor
from discovery.bootstrap_manager import get_bootstrap_manager, parse_bootstrap_nodes_from_env
from config import settings

setup_logging()
logger = get_logger(__name__)

async def main():
    """
    Avvia un nodo worker, lo connette alla rete DHT e lo lascia in esecuzione.
    Utilizza il bootstrap manager avanzato per load balancing e fallback automatico.
    """
    port = int(os.getenv("DHT_PORT", 7000))
    
    # Ottieni configurazione bootstrap
    bootstrap_strategy = os.getenv("BOOTSTRAP_SCALE_STRATEGY", settings.bootstrap_strategy)
    worker_count = int(os.getenv("WORKER_COUNT", "0"))  # 0 = sconosciuto, usa strategia configurata
    
    logger.info(f"Worker启动 - Port: {port}, Strategy: {bootstrap_strategy}, Worker Count: {worker_count}")
    
    # Inizializza il bootstrap manager
    bootstrap_manager = get_bootstrap_manager(worker_count, bootstrap_strategy)
    
    # Avvia il health check loop per bootstrap nodes
    health_check_task = asyncio.create_task(bootstrap_manager.health_check_loop())
    
    worker_node = CQKDNode(port=port, node_id=None)

    try:
        await worker_node.start()
        
        # Ottieni node ID reale
        real_node_id = getattr(worker_node.server.node, "id", None)
        real_node_id_str = "unknown"
        
        if real_node_id:
            # Se è in bytes, convertilo in hex abbreviato
            if isinstance(real_node_id, (bytes, bytearray)):
                real_node_id_str = real_node_id.hex()[:16] + "..."
            else:
                # fallback per tipi non previsti
                real_node_id_str = str(real_node_id)[:16] + "..."
            
            # aggiorna identificatore interno del nodo
            worker_node.node_id = real_node_id_str
            logger.info(f"✓ Node ID DHT effettivo: {real_node_id_str}")
        else:
            logger.warning("⚠ Impossibile determinare il node_id reale della DHT")

        # Aggiungi delay casuale per evitare collisioni
        import random
        await asyncio.sleep(random.uniform(0.5, 2.0))
        
        # Esegui bootstrap con fallback automatico
        bootstrap_success = await perform_bootstrap_with_fallback(worker_node, bootstrap_manager, real_node_id_str)
        
        if not bootstrap_success:
            logger.error(f"✗ Worker '{real_node_id_str}': bootstrap fallito dopo tutti i tentativi")
            # Continua comunque l'esecuzione per tentare riconnessioni successive





        # ===== START EXECUTOR FOR QUANTUM OPERATIONS =====
        executor = WorkerExecutor(worker_node, polling_interval=0.3)
        executor_task = asyncio.create_task(executor.start())
        
        logger.info(
            f"✓ Worker '{real_node_id_str}' executor started - "
            f"ready for quantum operations"
        )
        
        # Keep node running
        try:
            await executor_task
        except asyncio.CancelledError:
            logger.info(f"Worker '{real_node_id_str}' received cancellation")
            await executor.stop()
            health_check_task.cancel()
            raise



    except Exception as e:
        logger.error(f"✗ Errore critico durante l'avvio del worker node '{real_node_id_str}': {e}", exc_info=True)
        logger.info(f"✓ Worker node '{real_node_id_str}' rimane attivo nonostante l'errore critico...")
        # In caso di errore critico durante l'avvio, mantieni comunque il nodo attivo
        while True:
            try:
                await asyncio.sleep(10)
                logger.info(f"Worker node '{real_node_id_str}' ancora attivo dopo errore critico...")
            except Exception as retry_e:
                logger.error(f"✗ Errore anche nel loop di recupero: {retry_e}")
                await asyncio.sleep(30)


async def perform_bootstrap_with_fallback(worker_node: CQKDNode, bootstrap_manager, worker_id: str) -> bool:
    """
    Esegue il bootstrap con fallback automatico e load balancing
    
    Args:
        worker_node: Istanza del worker node
        bootstrap_manager: Bootstrap manager instance
        worker_id: ID del worker per logging
        
    Returns:
        bool: True se bootstrap riuscito, False altrimenti
    """
    max_retries = settings.bootstrap_fallback_max_retries
    retry_delay = settings.bootstrap_fallback_retry_delay
    
    for attempt in range(max_retries):
        try:
            # Ottieni bootstrap nodes basandosi sulla strategia
            bootstrap_nodes = bootstrap_manager.get_bootstrap_nodes(
                strategy=settings.bootstrap_selection_strategy
            )
            
            if not bootstrap_nodes:
                logger.error(f"✗ Worker '{worker_id}': Nessun bootstrap node disponibile")
                await asyncio.sleep(retry_delay)
                continue
            
            logger.info(f"✓ Worker '{worker_id}': Tentativo bootstrap {attempt + 1}/{max_retries} verso {bootstrap_nodes}")
            
            # Esegui bootstrap
            await worker_node.bootstrap(bootstrap_nodes)
            
            # Report successo per tutti i bootstrap nodes usati
            for host, port in bootstrap_nodes:
                bootstrap_manager.report_connection_success(host, port)
            
            # Verifica che abbiamo nodi nella routing table
            routing_info = worker_node.get_routing_table_info()
            if routing_info.get('total_nodes', 0) > 0:
                logger.info(f"✓ Worker '{worker_id}' connesso alla rete DHT con {routing_info['total_nodes']} nodi.")
                
                # Log info bootstrap manager
                bootstrap_info = bootstrap_manager.get_bootstrap_info()
                logger.info(f"✓ Bootstrap status: {bootstrap_info['healthy_nodes']}/{bootstrap_info['total_nodes']} nodes healthy")
                
                return True
            else:
                logger.warning(f"⚠ Worker '{worker_id}': routing table vuota dopo bootstrap")
                
                # Attendi e riprova
                await asyncio.sleep(10)
                
                # Riprova il bootstrap con gli stessi nodi
                await worker_node.bootstrap(bootstrap_nodes)
                routing_info = worker_node.get_routing_table_info()
                
                if routing_info.get('total_nodes', 0) > 0:
                    logger.info(f"✓ Worker '{worker_id}' connesso al retry con {routing_info['total_nodes']} nodi.")
                    return True
        
        except Exception as e:
            logger.error(f"✗ Worker '{worker_id}': Bootstrap attempt {attempt + 1} failed: {e}")
            
            # Report fallimento per tutti i bootstrap nodes usati
            bootstrap_nodes = bootstrap_manager.get_bootstrap_nodes(
                strategy=settings.bootstrap_selection_strategy
            )
            for host, port in bootstrap_nodes:
                bootstrap_manager.report_connection_failure(host, port)
        
        # Attendi prima del prossimo tentativo
        if attempt < max_retries - 1:
            await asyncio.sleep(retry_delay * (attempt + 1))  # Backoff esponenziale
    
    logger.error(f"✗ Worker '{worker_id}': Bootstrap fallito dopo {max_retries} tentativi")
    return False

if __name__ == "__main__":
    asyncio.run(main())
