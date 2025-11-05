
import asyncio
import os
import secrets
from core.dht_node import CQKDNode
from utils.logging_config import setup_logging, get_logger
from protocol.worker import WorkerExecutor
import random

setup_logging()
logger = get_logger(__name__)

async def main():
    """
    Avvia un nodo worker, lo connette alla rete DHT e lo lascia in esecuzione.
    """
    port = int(os.getenv("DHT_PORT", 7000))
    worker_node = CQKDNode(port=port, node_id=None)
    

    bootstrap_nodes_str = os.getenv("BOOTSTRAP_NODES")
    if not bootstrap_nodes_str:
        logger.error("✗ La variabile d'ambiente BOOTSTRAP_NODES è richiesta.")
        return
    # Converte "host1:port1,host2:port2" in [("host1", port1), ("host2", port2)]
    bootstrap_nodes = []
    for addr in bootstrap_nodes_str.split(','):
        host, b_port = addr.strip().split(':')
        bootstrap_nodes.append((host, int(b_port)))


    try:
        await worker_node.start() # await self.server.listen(self.port)

        logger.info(f"✓ Worker node avviato. Tentativo di bootstrap verso {bootstrap_nodes}...")

        # PROCESSO PER RECUPERARE ID DEL NODO
        real_node_id = getattr(worker_node.server.node, "id", None)

        if real_node_id:
            # Se è in bytes, convertilo in hex abbreviato
            if isinstance(real_node_id, (bytes, bytearray)):
                real_node_id_str = real_node_id.hex()[:16] + "..."
            else:
                # fallback per tipi non previsti
                real_node_id_str = str(real_node_id)[:16] + "..."

            # aggiorna identificatore interno del nodo
            worker_node.node_id = real_node_id_str
            logger.info(f"✓ Node ID DHT effettivo: {worker_node.node_id}")
        else:
            logger.warning("⚠ Impossibile determinare il node_id reale della DHT")

        logger.info(f"real_node_id:{real_node_id_str}")

        # Aggiungi delay casuale per evitare collisioni
        await asyncio.sleep(2)

        await worker_node.bootstrap(bootstrap_nodes)

     

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
            raise



    except Exception as e:
        logger.error(f"✗ Errore critico durante l'avvio del worker node '{real_node_id}': {e}", exc_info=True)
        logger.info(f"✓ Worker node '{real_node_id}' rimane attivo nonostante l'errore critico...")
        # In caso di errore critico durante l'avvio, mantieni comunque il nodo attivo
        while True:
            try:
                await asyncio.sleep(10)
                logger.info(f"Worker node '{real_node_id}' ancora attivo dopo errore critico...")
            except Exception as retry_e:
                logger.error(f"✗ Errore anche nel loop di recupero: {retry_e}")
                await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(main())
