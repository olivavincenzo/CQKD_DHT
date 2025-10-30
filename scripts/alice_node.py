
import asyncio
import os
from core.dht_node import CQKDNode
from protocol.alice import Alice
from utils.logging_config import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

PROCESS_ID_KEY = "cqkd_process_id"
MIN_WORKERS_FOR_TEST = 10 # Numero minimo di worker prima di iniziare

async def main():
    """
    Avvia il nodo di Alice, attende i worker, pubblica il process_id 
    e avvia la generazione della chiave.
    """
    port = int(os.getenv("DHT_PORT", 6000))
    bob_address = os.getenv("BOB_ADDRESS")
    bootstrap_nodes_str = os.getenv("BOOTSTRAP_NODES")
    node_id = "alice"

    if not all([bob_address, bootstrap_nodes_str]):
        logger.error("✗ Le variabili d'ambiente BOB_ADDRESS e BOOTSTRAP_NODES sono richieste.")
        return

    bootstrap_nodes = [(host, int(b_port)) for host, b_port in (addr.strip().split(':') for addr in bootstrap_nodes_str.split(','))]

    logger.info(f"Avvio Alice node '{node_id}' su porta {port}...")
    alice_node = CQKDNode(port=port, node_id=node_id)
    await alice_node.start()
    await alice_node.bootstrap(bootstrap_nodes)
    logger.info(f"✓ Alice node '{node_id}' connessa alla rete DHT.")

    try:
        # Attendi che la rete abbia un numero sufficiente di worker
        logger.info(f"Alice in attesa di almeno {MIN_WORKERS_FOR_TEST} worker nella sua routing table...")
        while True:
            rt_info = alice_node.get_routing_table_info()
            num_nodes = rt_info.get("total_nodes", 0)
            if num_nodes >= MIN_WORKERS_FOR_TEST:
                logger.info(f"✓ Rete pronta. Alice conosce {num_nodes} nodi.")
                break
            logger.info(f"Attualmente {num_nodes}/{MIN_WORKERS_FOR_TEST} nodi noti. Attendo...")
            await asyncio.sleep(5)

        # Inizializza il protocollo e pubblica il process_id per Bob
        alice_protocol = Alice(alice_node, bob_address=bob_address)
        process_id = alice_protocol.orchestrator.process_id
        
        logger.info(f"Alice pubblica il process_id '{process_id}' sulla chiave DHT '{PROCESS_ID_KEY}' per Bob...")
        await alice_node.store_data(PROCESS_ID_KEY, process_id)
        logger.info("✓ process_id pubblicato.")

        # Avvia la generazione della chiave
        desired_key_length = 8
        logger.info(f"Alice avvia la generazione di una chiave a {desired_key_length} bit...")
        
        alice_key = await alice_protocol.generate_key(desired_length_bits=desired_key_length)
        
        if alice_key:
            logger.info(f"SUCCESS! Alice ha generato la chiave: {alice_key.hex()}")
        else:
            logger.error("✗ Alice non è riuscita a generare la chiave.")

    except Exception as e:
        logger.error(f"✗ Errore critico in Alice: {e}", exc_info=True)
    finally:
        await alice_node.stop()
        logger.info("Alice node fermato.")

if __name__ == "__main__":
    asyncio.run(main())
