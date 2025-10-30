import pytest
import asyncio
from typing import List
from core.dht_node import CQKDNode
from utils.logging_config import setup_logging


@pytest.fixture(scope="session")
def event_loop():
    """Crea event loop per tutta la sessione di test"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def setup_test_logging():
    """Configura logging per i test"""
    setup_logging()


@pytest.fixture
async def bootstrap_node():
    """Crea un nodo bootstrap per i test"""
    node = CQKDNode(port=5678)
    await node.start()
    yield node
    await node.stop()


@pytest.fixture
async def worker_nodes(bootstrap_node):
    """Crea una rete di nodi worker per i test"""
    nodes = []
    base_port = 5679

    for i in range(10):
        node = CQKDNode(port=base_port + i)
        await node.start()
        await node.bootstrap([("127.0.0.1", 5678)])
        nodes.append(node)
        await asyncio.sleep(0.1)

    yield nodes

    for node in nodes:
        await node.stop()


@pytest.fixture
async def alice_and_bob(bootstrap_node, worker_nodes):
    """Crea istanze Alice e Bob per i test"""
    from protocol.alice import Alice
    from protocol.bob import Bob

    alice_node = CQKDNode(port=6000)
    await alice_node.start()
    await alice_node.bootstrap([("127.0.0.1", 5678)])

    bob_node = CQKDNode(port=6001)
    await bob_node.start()
    await bob_node.bootstrap([("127.0.0.1", 5678)])

    alice = Alice(alice_node, bob_address="127.0.0.1:6001")
    bob = Bob(bob_node)

    yield alice, bob

    await alice_node.stop()
    await bob_node.stop()
