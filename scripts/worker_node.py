
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

        # Aggiungi delay casuale per evitare collisioni
        import random
        await asyncio.sleep(random.uniform(0.5, 2.0))

        await worker_node.bootstrap(bootstrap_nodes)

        # Verifica che abbiamo nodi nella routing table
        routing_info = worker_node.get_routing_table_info()
        if routing_info.get('total_nodes', 0) == 0:
            logger.warning(f"⚠ Worker '{node_id}': routing table vuota dopo bootstrap, attendo 10s...")
            await asyncio.sleep(10)  # Dai tempo alla rete di stabilizzarsi

            # Riprova il bootstrap
            await worker_node.bootstrap(bootstrap_nodes)
            routing_info = worker_node.get_routing_table_info()

        if routing_info.get('total_nodes', 0) > 0:
            logger.info(f"✓ Worker node '{node_id}' connesso alla rete DHT con {routing_info['total_nodes']} nodi.")
        else:
            logger.warning(f"⚠ Worker node '{node_id}' connesso ma routing table vuota.")

        # Mantieni il nodo in esecuzione indefinitamente
        logger.info(f"✓ Worker node '{node_id}' ora in esecuzione continua. In attesa di operazioni...")
        while True:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                logger.info(f"Worker node '{node_id}' ricevuto segnale di cancellazione, ma rimane attivo...")
                # Ignora la cancellazione e continua l'esecuzione
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"✗ Errore nel loop principale del worker '{node_id}': {e}", exc_info=True)
                await asyncio.sleep(5)  # Breve pausa prima di continuare

    except Exception as e:
        logger.error(f"✗ Errore critico durante l'avvio del worker node '{node_id}': {e}", exc_info=True)
        logger.info(f"✓ Worker node '{node_id}' rimane attivo nonostante l'errore critico...")
        # In caso di errore critico durante l'avvio, mantieni comunque il nodo attivo
        while True:
            try:
                await asyncio.sleep(10)
                logger.info(f"Worker node '{node_id}' ancora attivo dopo errore critico...")
            except Exception as retry_e:
                logger.error(f"✗ Errore anche nel loop di recupero: {retry_e}")
                await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(main())
