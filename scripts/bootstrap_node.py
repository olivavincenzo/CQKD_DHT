import asyncio
import os
from core.dht_node import CQKDNode
from utils.logging_config import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

async def main():
    """
    Avvia un nodo di bootstrap per la rete DHT.
    """
    port = int(os.getenv("DHT_PORT", 5678))
    node_id = "bootstrap"
    
    logger.info(f"Avvio bootstrap node su porta {port}...")
    
    bootstrap_node = CQKDNode(port=port, node_id=node_id)
    
    try:
        await bootstrap_node.start()
        logger.info(f"✓ Bootstrap node '{node_id}' attivo e in ascolto su {port}")
        
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