#!/usr/bin/env python3
"""
Test del sistema di health check gerarchico per nodi DHT

Questo test verifica:
1. Configurazione centralizzata dei timeout
2. Sistema gerarchico fast/medium/deep
3. Batch processing per molti nodi
4. Rimozione automatica nodi non sani
5. Metriche e logging
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
from typing import List

# Aggiungi il path del progetto
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.dht_node import CQKDNode
from core.node_states import NodeInfo, NodeState, NodeRole
from discovery.health_check_manager import HealthCheckManager, HealthCheckLevel
from discovery.node_cache import NodeCache
from discovery.discovery_strategies import SmartDiscoveryStrategy
from config import settings
from utils.logging_config import get_logger


logger = get_logger(__name__)


class MockCQKDNode:
    """Mock node per testing senza rete reale"""
    
    def __init__(self):
        self.server = MockServer()
        self.routing_table_nodes = []
    
    def get_routing_table_info(self):
        return {
            "total_nodes": len(self.routing_table_nodes),
            "network_health": {
                "well_distributed": True,
                "distribution_score": 0.8
            }
        }


class MockServer:
    """Mock server per testing"""
    
    def __init__(self):
        self.protocol = MockProtocol()
        self.node = MockKademliaNode()


class MockProtocol:
    """Mock protocol per testing"""
    
    def __init__(self):
        self.router = MockRouter()
    
    async def callPing(self, node):
        # Simula diversi comportamenti
        if hasattr(node, '_should_fail') and node._should_fail:
            raise Exception("Simulated failure")
        
        # Simula latenza variabile
        if hasattr(node, '_latency'):
            await asyncio.sleep(node._latency)
        
        return True
    
    async def callFindNode(self, node, target):
        if hasattr(node, '_should_fail') and node._should_fail:
            raise Exception("Simulated failure")
        return []


class MockRouter:
    """Mock router per testing"""
    
    def __init__(self):
        self.buckets = []
    
    def find_neighbors(self, node, k=20):
        return []
    
    def remove_contact(self, node_id):
        pass


class MockKademliaNode:
    """Mock Kademlia node"""
    
    def __init__(self):
        self.id = b"mock_node_id_12345678901234567890"


class MockHealthCheckNode:
    """Mock node per health check testing"""
    
    def __init__(self, node_id: str, address: str = "127.0.0.1", port: int = 5678, 
                 should_fail: bool = False, latency: float = 0.1):
        self.node_id = node_id
        self.address = address
        self.port = port
        self._should_fail = should_fail
        self._latency = latency


def create_test_nodes(count: int, failure_rate: float = 0.2) -> List[NodeInfo]:
    """Crea nodi di test con tasso di fallimento configurabile"""
    nodes = []
    for i in range(count):
        node_id = f"test_node_{i:04d}".ljust(40, '0')
        should_fail = (i % int(1 / failure_rate) == 0) if failure_rate > 0 else False
        latency = 0.05 + (i % 10) * 0.02  # Latenza variabile
        
        node = NodeInfo(
            node_id=node_id,
            address="127.0.0.1",
            port=5678 + i,
            state=NodeState.ACTIVE,
            current_role=None,
            last_seen=datetime.now(),
            capabilities=[NodeRole.QSG, NodeRole.BG] if i % 2 == 0 else [NodeRole.QPP]
        )
        
        # Aggiungi metadati per mock
        node._should_fail = should_fail
        node._latency = latency
        
        nodes.append(node)
    
    return nodes


async def test_health_check_configuration():
    """Test della configurazione centralizzata"""
    print("\n=== Test Configurazione Health Check ===")
    
    # Test parametri per diverse dimensioni di rete
    network_sizes = [10, 50, 100, 500, 1000]
    
    for size in network_sizes:
        params = settings.calculate_health_check_params(size)
        
        print(f"\nRete di {size} nodi ({params['network_category']}):")
        print(f"  Fast timeout: {params['fast_timeout']}s")
        print(f"  Medium timeout: {params['medium_timeout']}s")
        print(f"  Deep timeout: {params['deep_timeout']}s")
        print(f"  Batch size: {params['batch_size']}")
        print(f"  Concurrent batches: {params['concurrent_batches']}")
        print(f"  Fast interval: {params['fast_interval']}s")
        print(f"  Medium interval: {params['medium_interval']}s")
        print(f"  Deep interval: {params['deep_interval']}s")
        
        # Verifica che i timeout siano entro i limiti richiesti
        assert params['fast_timeout'] <= 2.0, f"Fast timeout troppo alto: {params['fast_timeout']}"
        assert params['medium_timeout'] <= 2.0, f"Medium timeout troppo alto: {params['medium_timeout']}"
        assert params['deep_timeout'] <= 5.0, f"Deep timeout troppo alto: {params['deep_timeout']}"
    
    print("\n✅ Configurazione validata con successo!")


async def test_health_check_manager():
    """Test del HealthCheckManager"""
    print("\n=== Test Health Check Manager ===")
    
    # Crea mock node e cache
    mock_node = MockCQKDNode()
    cache = NodeCache()
    
    # Crea health check manager
    health_check = HealthCheckManager(mock_node, cache)
    
    # Crea nodi di test
    test_nodes = create_test_nodes(20, failure_rate=0.2)
    
    # Aggiungi nodi alla cache
    for node in test_nodes:
        cache.add(node)
    
    print(f"Creati {len(test_nodes)} nodi di test")
    
    # Test fast check
    print("\n--- Test Fast Check ---")
    start_time = datetime.now()
    
    results = await health_check._execute_batch_health_check(
        test_nodes[:10],  # Test su primo gruppo
        HealthCheckLevel.FAST,
        1.0,  # 1s timeout
        5      # batch size
    )
    
    duration = (datetime.now() - start_time).total_seconds()
    successful = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)
    
    print(f"Fast check completato in {duration:.2f}s")
    print(f"Risultati: {successful} success, {failed} failed")
    print(f"Tempo medio risposta: {sum(r.response_time for r in results) / len(results):.3f}s")
    
    # Verifica che i risultati siano stati processati
    assert len(results) == 10, "Numero di risultati non corrispondente"
    assert successful + failed == 10, "Conteggio success/failed errato"
    
    # Test statistiche
    stats = health_check.get_stats()
    print(f"\nStatistiche health check:")
    print(f"  Fast checks: {stats['fast_checks']}")
    print(f"  Successful checks: {stats['successful_checks']}")
    print(f"  Failed checks: {stats['failed_checks']}")
    print(f"  Avg response time: {stats['avg_response_time']:.3f}s")
    print(f"  Monitored nodes: {stats['monitored_nodes']}")
    
    print("\n✅ Health Check Manager test completato!")


async def test_batch_processing():
    """Test del batch processing per molti nodi"""
    print("\n=== Test Batch Processing ===")
    
    mock_node = MockCQKDNode()
    cache = NodeCache()
    health_check = HealthCheckManager(mock_node, cache)
    
    # Crea molti nodi di test
    many_nodes = create_test_nodes(100, failure_rate=0.1)
    
    for node in many_nodes:
        cache.add(node)
    
    print(f"Creati {len(many_nodes)} nodi per test batch processing")
    
    # Test con batch size diverso
    batch_sizes = [10, 20, 50]
    
    for batch_size in batch_sizes:
        print(f"\n--- Test con batch size {batch_size} ---")
        
        start_time = datetime.now()
        
        results = await health_check._execute_batch_health_check(
            many_nodes[:batch_size * 2],  # Test su 2 batch
            HealthCheckLevel.FAST,
            1.0,
            batch_size
        )
        
        duration = (datetime.now() - start_time).total_seconds()
        successful = sum(1 for r in results if r.success)
        
        print(f"Processati {len(results)} nodi in {duration:.2f}s")
        print(f"Throughput: {len(results) / duration:.1f} nodi/s")
        print(f"Success rate: {successful / len(results) * 100:.1f}%")
        
        # Verifica efficienza
        assert duration < 5.0, f"Batch processing troppo lento: {duration}s"
    
    print("\n✅ Batch processing test completato!")


async def test_node_removal():
    """Test rimozione automatica nodi non sani"""
    print("\n=== Test Rimozione Nodi Non Sani ===")
    
    mock_node = MockCQKDNode()
    cache = NodeCache()
    health_check = HealthCheckManager(mock_node, cache)
    
    # Crea nodi con alto tasso di fallimento
    failing_nodes = create_test_nodes(10, failure_rate=0.8)
    
    for node in failing_nodes:
        cache.add(node)
    
    print(f"Creati {len(failing_nodes)} nodi con alto tasso di fallimento")
    
    # Simula fallimenti multipli
    for i in range(5):  # 5 round di check falliti
        results = await health_check._execute_batch_health_check(
            failing_nodes,
            HealthCheckLevel.FAST,
            1.0,
            5
        )
        
        await health_check._process_health_check_results(results)
        
        failed = sum(1 for r in results if not r.success)
        print(f"Round {i+1}: {failed} nodi falliti")
    
    # Verifica stato dei nodi
    health_status = health_check.get_all_health_status()
    nodes_to_remove = []
    
    for node_id, status in health_status.items():
        if status.needs_removal(3, 0.3):  # 3 fallimenti, score minimo 0.3
            nodes_to_remove.append(node_id)
    
    print(f"Nodi da rimuovere: {len(nodes_to_remove)}")
    
    if nodes_to_remove:
        await health_check._remove_unhealthy_nodes(nodes_to_remove)
        print(f"Rimossi {len(nodes_to_remove)} nodi non sani")
    
    # Verifica rimozione
    remaining_status = health_check.get_all_health_status()
    print(f"Nodi rimanenti monitorati: {len(remaining_status)}")
    
    print("\n✅ Test rimozione nodi completato!")


async def test_discovery_integration():
    """Test integrazione con SmartDiscoveryStrategy"""
    print("\n=== Test Integrazione Discovery ===")
    
    mock_node = MockCQKDNode()
    
    # Crea strategia con health check abilitato
    settings.enable_health_check = True
    strategy = SmartDiscoveryStrategy(mock_node, enable_cache=True)
    
    # Aggiungi nodi alla cache
    test_nodes = create_test_nodes(30, failure_rate=0.2)
    for node in test_nodes:
        strategy.cache.add(node)
    
    print(f"Aggiunti {len(test_nodes)} nodi alla cache")
    
    # Test health check stats
    health_stats = strategy.get_health_stats()
    print(f"Statistiche health check: {health_stats}")
    
    # Test verifica manuale nodi
    await strategy._manual_verify_nodes(test_nodes[:10])
    
    # Verifica statistiche dopo verifica
    updated_stats = strategy.get_health_stats()
    print(f"Statistiche dopo verifica: {updated_stats}")
    
    # Test stato salute nodo specifico
    if test_nodes:
        node_status = strategy.get_node_health_status(test_nodes[0].node_id)
        if node_status:
            print(f"Stato nodo {test_nodes[0].node_id[:16]}: {node_status}")
    
    # Ferma task di background
    await strategy.stop_background_tasks()
    
    print("\n✅ Test integrazione discovery completato!")


async def test_performance_scaling():
    """Test performance con scaling della rete"""
    print("\n=== Test Performance Scaling ===")
    
    network_sizes = [50, 100, 200, 500]
    
    for size in network_sizes:
        print(f"\n--- Test con {size} nodi ---")
        
        mock_node = MockCQKDNode()
        cache = NodeCache()
        health_check = HealthCheckManager(mock_node, cache)
        
        # Aggiorna dimensione rete per parametri adattivi
        mock_node.routing_table_nodes = create_test_nodes(size)
        
        # Crea nodi
        nodes = create_test_nodes(size, failure_rate=0.15)
        for node in nodes:
            cache.add(node)
        
        # Calcola parametri adattivi
        params = settings.calculate_health_check_params(size)
        
        # Test fast check su subset
        test_subset = nodes[:params['batch_size'] * 2]
        
        start_time = datetime.now()
        results = await health_check._execute_batch_health_check(
            test_subset,
            HealthCheckLevel.FAST,
            params['fast_timeout'],
            params['batch_size']
        )
        
        duration = (datetime.now() - start_time).total_seconds()
        throughput = len(results) / duration
        
        print(f"Processati {len(results)} nodi in {duration:.2f}s")
        print(f"Throughput: {throughput:.1f} nodi/s")
        print(f"Parametri: batch_size={params['batch_size']}, concurrent={params['concurrent_batches']}")
        
        # Verifica che il throughput sia accettabile
        min_throughput = 10  # nodi al secondo minimi
        assert throughput >= min_throughput, f"Throughput troppo basso: {throughput}"
    
    print("\n✅ Test performance scaling completato!")


async def main():
    """Main test execution"""
    print("🚀 Avvio Test Sistema Health Check")
    print("=" * 50)
    
    try:
        # Test configurazione
        await test_health_check_configuration()
        
        # Test health check manager
        await test_health_check_manager()
        
        # Test batch processing
        await test_batch_processing()
        
        # Test rimozione nodi
        await test_node_removal()
        
        # Test integrazione discovery
        await test_discovery_integration()
        
        # Test performance scaling
        await test_performance_scaling()
        
        print("\n" + "=" * 50)
        print("🎉 Tutti i test completati con successo!")
        print("✅ Sistema di health check pronto per produzione")
        
    except Exception as e:
        print(f"\n❌ Test fallito: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)