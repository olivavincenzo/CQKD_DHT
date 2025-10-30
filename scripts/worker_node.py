
import asyncio
import os
import secrets
from core.dht_node import CQKDNode
from utils.logging_config import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

async def main():
    """
    Avvia un nodo worker, lo connette alla rete DHT e lo lascia in esecuzione.
    """
    port = int(os.getenv("DHT_PORT", 7000))
    node_id = f"worker_{secrets.token_hex(4)}"
    
    bootstrap_nodes_str = os.getenv("BOOTSTRAP_NODES")
    if not bootstrap_nodes_str:
        logger.error("✗ La variabile d'ambiente BOOTSTRAP_NODES è richiesta.")
        return

    # Converte "host1:port1,host2:port2" in [("host1", port1), ("host2", port2)]
    bootstrap_nodes = []
    for addr in bootstrap_nodes_str.split(','):
        host, b_port = addr.strip().split(':')
        bootstrap_nodes.append((host, int(b_port)))

    logger.info(f"Avvio worker node '{node_id}' su porta {port}...")
    worker_node = CQKDNode(port=port, node_id=node_id)

    try:
        await worker_node.start()
        logger.info(f"✓ Worker node '{node_id}' avviato. Tentativo di bootstrap verso {bootstrap_nodes}...")
        
        await worker_node.bootstrap(bootstrap_nodes)
        logger.info(f"✓ Worker node '{node_id}' connesso alla rete DHT.")

        # Mantieni il nodo in esecuzione
        await asyncio.Event().wait()

    except Exception as e:
        logger.error(f"✗ Errore critico nel worker node '{node_id}': {e}", exc_info=True)
    finally:
        if worker_node:
            await worker_node.stop()
        logger.info(f"Worker node '{node_id}' fermato.")

if __name__ == "__main__":
    asyncio.run(main())
