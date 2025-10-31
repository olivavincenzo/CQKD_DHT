
import asyncio
import os
from core.dht_node import CQKDNode
from protocol.bob import Bob
from utils.logging_config import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

PROCESS_ID_KEY = "cqkd_process_id"

async def main():
    """
    Avvia il nodo di Bob, attende il process_id dalla DHT e si mette in ascolto.
    """
    port = int(os.getenv("DHT_PORT", 6001))
    node_id = "bob"
    bootstrap_nodes_str = os.getenv("BOOTSTRAP_NODES")

    if not bootstrap_nodes_str:
        logger.error("✗ La variabile d'ambiente BOOTSTRAP_NODES è richiesta.")
        return

    bootstrap_nodes = [(host, int(b_port)) for host, b_port in (addr.strip().split(':') for addr in bootstrap_nodes_str.split(','))]


    logger.info(f"Avvio Bob node '{node_id}' su porta {port}... e con bootstrap_nodes{bootstrap_nodes}")

    bob_node = CQKDNode(port=port, node_id=node_id)
    await bob_node.start()
    await bob_node.bootstrap(bootstrap_nodes)
    logger.info(f"✓ Bob node '{node_id}' connesso alla rete DHT.")

    bob_protocol = Bob(bob_node)
    process_id = None

    try:
        # Attendi che Alice pubblichi il process_id sulla DHT
        logger.info(f"Bob in attesa del process_id sulla chiave DHT: '{PROCESS_ID_KEY}'...")
        while process_id is None:
            process_id = await bob_node.retrieve_data(PROCESS_ID_KEY)
            if process_id is None:
                await asyncio.sleep(2)
        
        logger.info(f"✓ Bob ha ricevuto process_id: {process_id}. Avvio ricezione chiave...")
        
        # Avvia la ricezione della chiave
        bob_key = await bob_protocol.receive_key(process_id)
        
        if bob_key:
            logger.info(f"SUCCESS! Bob ha generato la chiave: {bob_key.hex()}")
            logger.info(f"✓ Bob rimane attivo per future generazioni di chiavi...")
        else:
            logger.error("✗ Bob non è riuscito a generare la chiave.")
            logger.info(f"✓ Bob rimane attivo per riprovare...")

        # Mantieni Bob attivo indefinitamente per future generazioni di chiavi
        logger.info(f"Bob in attesa del prossimo process_id sulla chiave DHT: '{PROCESS_ID_KEY}'...")
        while True:
            try:
                # Reset process_id per permettere nuove generazioni
                process_id = None

                # Attendi che Alice pubblichi un nuovo process_id
                while process_id is None:
                    process_id = await bob_node.retrieve_data(PROCESS_ID_KEY)
                    if process_id is None:
                        await asyncio.sleep(2)

                logger.info(f"✓ Bob ha ricevuto nuovo process_id: {process_id}. Avvio ricezione chiave...")

                # Avvia la ricezione della nuova chiave
                bob_key = await bob_protocol.receive_key(process_id)

                if bob_key:
                    logger.info(f"SUCCESS! Bob ha generato una nuova chiave: {bob_key.hex()}")
                else:
                    logger.error("✗ Bob non è riuscito a generare la nuova chiave.")

                # Breve pausa prima di cercare nuove chiavi
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"✗ Errore durante generazione chiave: {e}", exc_info=True)
                await asyncio.sleep(5)  # Pausa più lunga dopo errore

    except Exception as e:
        logger.error(f"✗ Errore critico in Bob: {e}", exc_info=True)
        # In caso di errore critico, mantieni comunque il nodo attivo
        logger.info("Bob rimane attivo nonostante l'errore...")
        while True:
            await asyncio.sleep(10)

    # Non fermare mai il nodo Bob (rimuoviamo il finally block)

if __name__ == "__main__":
    asyncio.run(main())
