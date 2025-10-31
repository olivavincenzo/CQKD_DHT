#!/usr/bin/env python3
"""
Script di test per verificare i miglioramenti del processo di discovery
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.dht_node import CQKDNode
from discovery.node_discovery import NodeDiscoveryService
from discovery.discovery_strategies import SmartDiscoveryStrategy
from protocol.key_generation import KeyGenerationOrchestrator
from utils.logging_config import get_logger

logger = get_logger(__name__)

async def test_discovery_improvements():
    """Test dei miglioramenti del discovery"""
    
    print("🧪 Test dei miglioramenti del processo di discovery...")
    
    # Crea un nodo di test
    test_node = CQKDNode(port=9999, node_id="test_discovery_node")
    
    try:
        # Avvia il nodo
        await test_node.start()
        print("✅ Nodo di test avviato")
        
        # Test 1: Verifica get_routing_table_info
        print("\n📊 Test 1: Verifica get_routing_table_info()")
        routing_info = test_node.get_routing_table_info()
        print(f"   Total nodes: {routing_info.get('total_nodes', 0)}")
        print(f"   Active buckets: {routing_info.get('active_buckets', 0)}")
        print(f"   Network health: {routing_info.get('network_health', {})}")
        
        # Test 2: Test NodeDiscoveryService
        print("\n🔍 Test 2: Test NodeDiscoveryService migliorato")
        discovery_service = NodeDiscoveryService(test_node)
        
        try:
            result = await discovery_service.discover_nodes_for_roles(
                required_count=5,
                required_capabilities=None
            )
            print(f"   Nodi scoperti: {len(result.discovered_nodes)}")
            print(f"   Query eseguite: {result.query_count}")
            print(f"   Durata: {result.duration_seconds:.2f}s")
        except Exception as e:
            print(f"   ❌ Errore discovery: {e}")
        
        # Test 3: Test SmartDiscoveryStrategy
        print("\n🧠 Test 3: Test SmartDiscoveryStrategy migliorata")
        smart_discovery = SmartDiscoveryStrategy(test_node)
        await smart_discovery.start_background_tasks()
        
        try:
            nodes = await smart_discovery.discover_nodes(
                required_count=5,
                required_capabilities=None,
                prefer_distributed=True,
                max_discovery_time=30
            )
            print(f"   Nodi trovati: {len(nodes)}")
            for i, node_id in enumerate(nodes[:3]):  # Mostra solo i primi 3
                print(f"   - Node {i+1}: {node_id[:16]}...")
        except Exception as e:
            print(f"   ❌ Errore smart discovery: {e}")
        
        # Test 4: Test KeyGenerationOrchestrator
        print("\n🎼 Test 4: Test KeyGenerationOrchestrator con retry")
        orchestrator = KeyGenerationOrchestrator(test_node)
        
        try:
            nodes = await orchestrator.discover_available_nodes(
                required_count=5,
                required_capabilities=None,
                max_retries=2
            )
            print(f"   Nodi orchestrati: {len(nodes)}")
            for i, node_id in enumerate(nodes[:3]):  # Mostra solo i primi 3
                print(f"   - Node {i+1}: {node_id[:16]}...")
        except Exception as e:
            print(f"   ❌ Errore orchestrator: {e}")
        
        # Cleanup
        await smart_discovery.stop_background_tasks()
        print("\n🧹 Cleanup completato")
        
    except Exception as e:
        print(f"❌ Errore durante il test: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        try:
            await test_node.stop()
            print("✅ Nodo di test fermato")
        except:
            pass

if __name__ == "__main__":
    print("🚀 Avvio test dei miglioramenti del discovery...")
    asyncio.run(test_discovery_improvements())
    print("🏁 Test completato")