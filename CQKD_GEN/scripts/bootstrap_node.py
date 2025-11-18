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

        # Mantieni il nodo in esecuzione indefinitamente
        logger.info(f"✓ Bootstrap node '{node_id}' ora in esecuzione continua. In ascolto sulla porta {port}...")
        while True:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                logger.info(f"Bootstrap node '{node_id}' ricevuto segnale di cancellazione, ma rimane attivo...")
                # Ignora la cancellazione e continua l'esecuzione
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"✗ Errore nel loop principale del bootstrap '{node_id}': {e}", exc_info=True)
                await asyncio.sleep(5)  # Breve pausa prima di continuare

    except Exception as e:
        logger.error(f"✗ Errore critico durante l'avvio del bootstrap node '{node_id}': {e}", exc_info=True)
        logger.info(f"✓ Bootstrap node '{node_id}' rimane attivo nonostante l'errore critico...")
        # In caso di errore critico durante l'avvio, mantieni comunque il nodo attivo
        while True:
            try:
                await asyncio.sleep(10)
                logger.info(f"Bootstrap node '{node_id}' ancora attivo dopo errore critico...")
            except Exception as retry_e:
                logger.error(f"✗ Errore anche nel loop di recupero: {retry_e}")
                await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(main())