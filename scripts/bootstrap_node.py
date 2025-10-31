import asyncio
import os
from core.dht_node import CQKDNode
from utils.logging_config import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

async def main():
    """
    Avvia un nodo di bootstrap per la rete DHT.
    Supporta sia bootstrap primario che secondario (multi-bootstrap).
    """
    port = int(os.getenv("DHT_PORT", 5678))
    node_id = os.getenv("NODE_ID", f"bootstrap_{port}")  # Usa NODE_ID se disponibile
    bootstrap_nodes_str = os.getenv("BOOTSTRAP_NODES")

    logger.info(f"Avvio bootstrap node '{node_id}' su porta {port}...")

    bootstrap_node = CQKDNode(port=port, node_id=node_id)

    try:
        await bootstrap_node.start()

        # Se ci sono bootstrap nodes, connetti (bootstrap secondario)
        if bootstrap_nodes_str:
            bootstrap_nodes = [(host, int(b_port)) for host, b_port in (addr.strip().split(':') for addr in bootstrap_nodes_str.split(','))]
            logger.info(f"Bootstrap secondario '{node_id}' si connette a: {bootstrap_nodes}")
            await bootstrap_node.bootstrap(bootstrap_nodes)
            logger.info(f"✓ Bootstrap secondario '{node_id}' connesso alla rete esistente")
        else:
            logger.info(f"✓ Bootstrap primario '{node_id}' attivo e in ascolto su {port}")

        # Mantieni il nodo in esecuzione
        await asyncio.Event().wait()
        
    except Exception as e:
        logger.error(f"✗ Errore critico nel bootstrap node: {e}", exc_info=True)
    finally:
        if bootstrap_node:
            await bootstrap_node.stop()
        logger.info("Bootstrap node fermato.")

if __name__ == "__main__":
    asyncio.run(main())