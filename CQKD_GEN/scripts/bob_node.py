import asyncio
import os

from core.dht_node import CQKDNode
from protocol.bob import Bob
from utils.logging_config import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

PROCESS_ID_KEY = "cqkd_process_id"


async def wait_new_process_id(node: CQKDNode, key: str, last_seen: str | None = None) -> str:
    """
    Attende un nuovo process_id pubblicato da Alice sulla chiave DHT `key`,
    ignorando valori None, "__DELETED__" e lo stesso process_id già visto.
    Inoltre valida che esista la notifica {pid}:alice_to_bob prima di restituire il pid.
    """
    while True:
        try:
            pid = await node.retrieve_data(key)

            # ignora None, "__DELETED__", e pid già visto
            if pid and pid != "__DELETED__" and pid != last_seen:
                notif_key = f"{pid}:alice_to_bob"

                # breve finestra per verificare che Alice abbia davvero iniziato il round
                for _ in range(10):  # ~5s con sleep(0.5)
                    notif = await node.retrieve_data(notif_key)
                    if notif:
                        logger.info(
                            "bob_new_process_id_validated",
                            extra={"process_id": pid, "notif_key": notif_key},
                        )
                        return pid
                    await asyncio.sleep(0.5)

                # se non troviamo la notifica, considera pid stantio e continua il loop
                logger.warning(
                    "bob_stale_process_id_ignored",
                    extra={"process_id": pid, "key": key},
                )

            await asyncio.sleep(1.0)

        except Exception as e:
            logger.error(
                f"✗ Errore in wait_new_process_id su chiave '{key}': {e}",
                exc_info=True,
            )
            await asyncio.sleep(2.0)


async def main():
    """
    Avvia il nodo di Bob, attende i process_id dalla DHT e rimane in ascolto
    per successive generazioni di chiavi.
    """
    port = int(os.getenv("DHT_PORT", 6001))
    node_id = "bob"

    bootstrap_nodes_str = os.getenv("BOOTSTRAP_NODES")
    if not bootstrap_nodes_str:
        logger.error("✗ La variabile d'ambiente BOOTSTRAP_NODES è richiesta.")
        return

    bootstrap_nodes = [
        (host, int(b_port))
        for host, b_port in (
            addr.strip().split(":") for addr in bootstrap_nodes_str.split(",")
        )
    ]

    logger.info(
        f"Avvio Bob node '{node_id}' su porta {port}... "
        f"con bootstrap_nodes {bootstrap_nodes}"
    )

    bob_node = CQKDNode(port=port, node_id=node_id)
    await bob_node.start()
    await bob_node.bootstrap(bootstrap_nodes)

    logger.info(f"✓ Bob node '{node_id}' connesso alla rete DHT.")

    bob_protocol = Bob(bob_node)
    last_seen_pid: str | None = None

    try:
        # ===== Primo round =====
        logger.info(
            f"Bob in attesa del process_id sulla chiave DHT: '{PROCESS_ID_KEY}'..."
        )

        process_id = await wait_new_process_id(
            bob_node, key=PROCESS_ID_KEY, last_seen=last_seen_pid
        )
        last_seen_pid = process_id

        logger.info(
            f"✓ Bob ha ricevuto process_id: {process_id}. Avvio ricezione chiave..."
        )

        # Avvia la ricezione della chiave (STEP 12–19)
        bob_key = await bob_protocol.receive_key(process_id)

        if bob_key:
            logger.info(f"SUCCESS! Bob ha generato la chiave: {bob_key.hex()}")
            logger.info("✓ Bob rimane attivo per future generazioni di chiavi...")
        else:
            logger.error("✗ Bob non è riuscito a generare la chiave.")
            logger.info("✓ Bob rimane attivo per riprovare...")

        # ===== Loop successivi =====
        logger.info(
            f"Bob in attesa dei prossimi process_id sulla chiave DHT: '{PROCESS_ID_KEY}'..."
        )

        while True:
            try:
                process_id = await wait_new_process_id(
                    bob_node, key=PROCESS_ID_KEY, last_seen=last_seen_pid
                )
                last_seen_pid = process_id

                logger.info(
                    f"✓ Bob ha ricevuto nuovo process_id: {process_id}. "
                    "Avvio ricezione chiave..."
                )

                bob_key = await bob_protocol.receive_key(process_id)

                if bob_key:
                    logger.info(
                        f"SUCCESS! Bob ha generato una nuova chiave: {bob_key.hex()}"
                    )
                else:
                    logger.error(
                        "✗ Bob non è riuscito a generare la nuova chiave."
                    )

                await asyncio.sleep(1)

            except Exception as e:
                logger.error(
                    f"✗ Errore durante generazione chiave: {e}",
                    exc_info=True,
                )
                await asyncio.sleep(5)  # Pausa più lunga dopo errore

    except KeyboardInterrupt:
        logger.info(
            "Bob ha ricevuto un interrupt, ma rimane attivo per continuare le operazioni..."
        )
        # Loop di sopravvivenza dopo interrupt
        while True:
            try:
                await asyncio.sleep(10)
                logger.info("Bob ancora attivo dopo interrupt...")
            except Exception as retry_e:
                logger.error(
                    f"✗ Errore nel loop di recupero dopo interrupt: {retry_e}"
                )
                await asyncio.sleep(30)

    except Exception as e:
        logger.error(
            f"✗ Errore critico in Bob: {e}",
            exc_info=True,
        )
        logger.info("Bob rimane attivo nonostante l'errore critico...")
        while True:
            try:
                await asyncio.sleep(10)
                logger.info("Bob ancora attivo dopo errore critico...")
            except Exception as retry_e:
                logger.error(
                    f"✗ Errore anche nel loop di recupero: {retry_e}"
                )
                await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
