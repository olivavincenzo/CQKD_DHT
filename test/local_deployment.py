import asyncio
import multiprocessing
import signal
import sys
import time
from core.dht_node import CQKDNode
from config import settings
from utils.logging_config import setup_logging, get_logger


setup_logging()
logger = get_logger(__name__)


async def run_worker_node(port: int, node_id: str, bootstrap_nodes: list):
    """Esegue un nodo worker"""
    node = CQKDNode(port=port, node_id=node_id)

    try:
        await node.start()

        if bootstrap_nodes:
            await node.bootstrap(bootstrap_nodes)

        logger.info(
            "worker_node_started",
            node_id=node_id,
            port=port
        )

        # Mantieni attivo
        while True:
            await asyncio.sleep(1)

    except asyncio.CancelledError:
        logger.info("worker_node_cancelled", node_id=node_id)
    except Exception as e:
        logger.error("worker_node_error", node_id=node_id, error=str(e))
    finally:
        await node.stop()
        logger.info("worker_node_stopped", node_id=node_id)


def worker_process(port: int, node_id: str, bootstrap_nodes: list):
    """Processo worker (entry point)"""
    setup_logging()

    # Gestione segnali
    def signal_handler(sig, frame):
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Esegui nodo
    try:
        asyncio.run(run_worker_node(port, node_id, bootstrap_nodes))
    except KeyboardInterrupt:
        pass


def deploy_local_network(num_workers: int, base_port: int = 5678):
    """
    Deploya una rete locale con multiprocessing

    Args:
        num_workers: Numero di nodi worker
        base_port: Porta base per i nodi
    """
    logger.info(
        "local_deployment_starting",
        num_workers=num_workers,
        base_port=base_port
    )

    processes = []

    try:
        # Avvia nodo bootstrap
        bootstrap_port = base_port
        bootstrap_process = multiprocessing.Process(
            target=worker_process,
            args=(bootstrap_port, "bootstrap", []),
            name="bootstrap"
        )
        bootstrap_process.start()
        processes.append(bootstrap_process)

        logger.info("bootstrap_node_launched", port=bootstrap_port)

        # Attendi bootstrap
        time.sleep(2)

        # Avvia worker nodes
        bootstrap_nodes = [("127.0.0.1", bootstrap_port)]

        for i in range(1, num_workers + 1):
            port = base_port + i
            node_id = f"worker_{i}"

            process = multiprocessing.Process(
                target=worker_process,
                args=(port, node_id, bootstrap_nodes),
                name=node_id
            )
            process.start()
            processes.append(process)

            if i % 10 == 0:
                logger.info(
                    "workers_launched",
                    count=i,
                    total=num_workers
                )
                time.sleep(0.5)  # Evita overload

        logger.info(
            "local_deployment_complete",
            total_nodes=len(processes)
        )

        # Mantieni attivo
        print(f"\n{'='*60}")
        print(f"Rete CQKD locale avviata con {len(processes)} nodi")
        print(f"Bootstrap node: 127.0.0.1:{bootstrap_port}")
        print(f"Worker nodes: {base_port+1} - {base_port+num_workers}")
        print(f"Premi Ctrl+C per fermare")
        print(f"{'='*60}\n")

        for process in processes:
            process.join()

    except KeyboardInterrupt:
        logger.info("local_deployment_shutdown_requested")

        # Termina tutti i processi
        for process in processes:
            if process.is_alive():
                process.terminate()

        # Attendi terminazione
        for process in processes:
            process.join(timeout=5)
            if process.is_alive():
                process.kill()

        logger.info("local_deployment_stopped")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Deploy CQKD local network")
    parser.add_argument(
        "--workers",
        type=int,
        default=50,
        help="Number of worker nodes (default: 50)"
    )
    parser.add_argument(
        "--base-port",
        type=int,
        default=5678,
        help="Base port for nodes (default: 5678)"
    )

    args = parser.parse_args()

    deploy_local_network(args.workers, args.base_port)
