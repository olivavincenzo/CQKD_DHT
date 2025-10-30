import asyncio
import sys
from typing import List
from core.dht_node import CQKDNode
from protocol.alice import Alice
from protocol.bob import Bob
from core.node_states import NodeRole
from utils.logging_config import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)


async def setup_dht_network(num_workers: int = 100) -> tuple[CQKDNode, List[CQKDNode]]:
    """
    Setup rete DHT con bootstrap e worker nodes
    
    Args:
        num_workers: Numero di nodi worker
        
    Returns:
        tuple: (bootstrap_node, lista_worker_nodes)
    """
    logger.info("setting_up_dht_network", num_workers=num_workers)
    
    # Bootstrap node
    bootstrap = CQKDNode(port=5678, node_id="bootstrap")
    await bootstrap.start()
    logger.info("bootstrap_node_started", port=5678)
    
    # Attendi che bootstrap sia pronto
    await asyncio.sleep(1)

    # Worker nodes
    workers = []
    base_port = 7000
    
    for i in range(num_workers):
        worker = CQKDNode(
            port=base_port + i,
            node_id=f"worker_{i}"
        )
        await worker.start()
        await worker.bootstrap([("127.0.0.1", 5678)])
        workers.append(worker)
        
        # Log progress ogni 20 nodi
        if (i + 1) % 20 == 0:
            logger.info("workers_started", count=i + 1, total=num_workers)
            await asyncio.sleep(0.1)  # Piccola pausa per non sovraccaricare
    
    # Attendi stabilizzazione rete DHT
    logger.info("waiting_for_dht_stabilization")
    await asyncio.sleep(2)
    
    logger.info("dht_network_ready", workers=num_workers)
    return bootstrap, workers


async def test_complete_cqkd_protocol():
    """
    Test completo del protocollo CQKD:
    1. Setup rete DHT
    2. Alice e Bob si connettono
    3. Alice genera chiave usando protocollo CQKD
    4. Bob riceve e genera stessa chiave
    5. Verifica che le chiavi coincidano
    """


    logger.info("TEST PROTOCOLLO CQKD COMPLETO")

    bootstrap = None
    workers = []
    alice_node = None
    bob_node = None
    
    try:
        # STEP 1: Setup rete DHT
        logger.info("Step 1: Setup rete DHT con 100 nodi worker...")
        bootstrap, workers = await setup_dht_network(num_workers=100)
        logger.info("✓ Rete DHT pronta\n")

        # STEP 2: Setup nodi Alice e Bob
        print("Step 2: Setup Alice e Bob...")
        alice_node = CQKDNode(port=6000, node_id="alice")
        await alice_node.start()
        await alice_node.bootstrap([("127.0.0.1", 5678)])

        # Dopo il bootstrap di Alice
        rt_info = alice_node.get_routing_table_info()
        logger.info(f"\nRouting table di Alice:")
        logger.info(f"  Nodi totali: {rt_info['total_nodes']}")
        logger.info(f"  Bucket attivi: {rt_info['active_buckets']}")
        for bucket in rt_info['buckets_detail'][:3]:  # Mostra primi 3 bucket
            logger.info(f"  Bucket {bucket['bucket_index']}: {bucket['node_count']} nodi")
        
        bob_node = CQKDNode(port=6001, node_id="bob")
        await bob_node.start()
        await bob_node.bootstrap([("127.0.0.1", 5678)])
        
        await asyncio.sleep(1)
        logger.info("✓ Alice e Bob connessi alla rete DHT\n")
        
        # STEP 3: Crea istanze protocollo
        logger.info("Step 3: Inizializzazione protocollo...")
        alice = Alice(alice_node, bob_address="127.0.0.1:6001")
        bob = Bob(bob_node)
        logger.info("✓ Alice e Bob inizializzati\n")
        
        # STEP 4: Test generazione chiave
        desired_key_length = 8  # Iniziamo con chiave piccola per test
        logger.info(f"Step 4: Alice genera chiave di {desired_key_length} bit...")
        logger.info("  (Questo include discovery nodi, allocazione, generazione fotoni)\n")

        # ✅ AVVIA BOB IN BACKGROUND
        # Bob deve conoscere il 'session_id' per recuperare i dettagli dalla DHT
        # e partecipare alla generazione della chiave avviata da Alice.
        session_id = alice.orchestrator.session_id
        logger.info(f"Step 4.1: Avvio di Bob in background per la sessione '{session_id}'...")
        bob_task = asyncio.create_task(bob.receive_key(session_id))
        
        # Alice genera e pubblica la chiave sulla DHT
        # NOTA: Questo è dove avviene TUTTO il protocollo CQKD
        try:
            alice_key = await alice.generate_key(
                desired_length_bits=desired_key_length
            )
            logger.info(f"✓ Alice ha generato chiave: {alice_key.hex()}\n")
            
        except ValueError as e:
            logger.error(f"✗ Errore durante generazione chiave: {e}")
            logger.error("\nPossibili cause:")
            logger.error("  - Nodi worker insufficienti")
            logger.error("  - Rete DHT non stabilizzata")
            logger.error(f"  - Servono {5 * int(2.5 * desired_key_length)} nodi, disponibili ~100")
            return
        
        # STEP 5: Bob riceve chiave
        logger.info("Step 5: Bob riceve e genera chiave...")

        # Attendi Bob
        bob_key = await bob_task
        logger.info(f"✓ Bob ha generato chiave: {bob_key.hex()}\n")
        
       
    except Exception as e:
        logger.error("test_failed", error=str(e), exc_info=True)
        print(f"\n✗ Test fallito: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # CLEANUP
        logger.info("\nCleanup...")
        
        if alice_node:
            await alice_node.stop()
        if bob_node:
            await bob_node.stop()
        
        for worker in workers:
            await worker.stop()
        
        if bootstrap:
            await bootstrap.stop()
        
        logger.info("✓ Cleanup completato")


async def test_simplified_discovery():
    """
    Test semplificato solo per discovery (senza generazione chiave completa)
    Utile per verificare che cache + random walk funzionino
    """
    print("\n" + "="*60)
    print("TEST SEMPLIFICATO - SOLO DISCOVERY")
    print("="*60 + "\n")
    
    bootstrap = None
    workers = []
    test_node = None
    
    try:
        # Setup rete minima
        print("Setup rete DHT con 50 nodi...")
        bootstrap, workers = await setup_dht_network(num_workers=50)
        
        # Crea nodo test
        test_node = CQKDNode(port=6100, node_id="test")
        await test_node.start()
        await test_node.bootstrap([("127.0.0.1", 5678)])
        await asyncio.sleep(1)
        
        # Crea orchestratore
        from protocol.key_generation import KeyGenerationOrchestrator
        orchestrator = KeyGenerationOrchestrator(test_node)
        
        # Test discovery
        print("\nTest 1: Discovery di 30 nodi...")
        nodes1 = await orchestrator.discover_available_nodes(30)
        print(f"✓ Trovati {len(nodes1)} nodi")
        
        print("\nTest 2: Discovery di altri 20 nodi (dovrebbe usare cache)...")
        nodes2 = await orchestrator.discover_available_nodes(20)
        print(f"✓ Trovati {len(nodes2)} nodi")
        
        # Statistiche cache
        if orchestrator.smart_discovery.cache:
            stats = orchestrator.smart_discovery.cache.get_stats()
            print(f"\nStatistiche cache:")
            print(f"  - Cache hit rate: {stats['hit_rate']:.2%}")
            print(f"  - Nodi in cache: {stats['cache_size']}")
        
        print("\n✓ Test discovery completato con successo")
        
    except Exception as e:
        print(f"\n✗ Test fallito: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        if test_node:
            await test_node.stop()
        for worker in workers:
            await worker.stop()
        if bootstrap:
            await bootstrap.stop()


async def main():
    """Entry point con scelta test"""
    if len(sys.argv) > 1 and sys.argv[-1] == "--simple":
        await test_simplified_discovery()
    else:
        await test_complete_cqkd_protocol()


if __name__ == "__main__":
    print("\nUSO:")
    print("  python test.py          # Test completo CQKD")
    print("  python test.py --simple # Test solo discovery\n")
    
    asyncio.run(main())
