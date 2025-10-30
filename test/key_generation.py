import pytest
import asyncio
from protocol.key_generation import KeyGenerationOrchestrator


@pytest.mark.asyncio
async def test_key_generation_orchestrator_requirements():
    """Test calcolo requisiti nodi"""
    from core.dht_node import CQKDNode

    node = CQKDNode(port=7000)
    await node.start()

    orchestrator = KeyGenerationOrchestrator(node)

    # Per chiave 128 bit: lk = 2.5 * 128 = 320
    # Nodi totali: 5 * 320 = 1600
    requirements = orchestrator.calculate_required_nodes(128)

    assert requirements['initial_key_length'] == 320
    assert requirements['qsg'] == 320
    assert requirements['bg'] == 320
    assert requirements['qpp'] == 320
    assert requirements['qpm'] == 320
    assert requirements['qpc'] == 320
    assert requirements['total'] == 1600

    await node.stop()


@pytest.mark.asyncio
async def test_bits_to_bytes_conversion():
    """Test conversione bit <-> bytes"""
    from core.dht_node import CQKDNode

    node = CQKDNode(port=7001)
    await node.start()

    orchestrator = KeyGenerationOrchestrator(node)

    # Test conversione
    bits = [1, 0, 1, 0, 1, 0, 1, 0]  # 0b10101010 = 170
    result_bytes = orchestrator.bits_to_bytes(bits)

    assert len(result_bytes) == 1
    assert result_bytes[0] == 170

    # Test conversione inversa
    recovered_bits = orchestrator.bytes_to_bits(result_bytes)
    assert recovered_bits == bits

    await node.stop()


@pytest.mark.asyncio
async def test_simple_key_generation(alice_and_bob, worker_nodes):
    """Test generazione chiave semplificata"""
    alice, bob = alice_and_bob

    # Simula generazione chiave piccola (4 bit finali)
    # lk = 2.5 * 4 = 10 bit iniziali
    # Nodi richiesti: 5 * 10 = 50 (ma abbiamo solo 10 worker)

    # Per test, usiamo parametri ridotti
    # TODO: Implementare versione semplificata per testing

    # Questo test richiede implementazione completa
    # Per ora verifica solo che le istanze siano create
    assert alice is not None
    assert bob is not None
    assert alice.node.state.value == "active"
    assert bob.node.state.value == "active"
