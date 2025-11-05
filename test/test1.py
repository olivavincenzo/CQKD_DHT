import asyncio
from kademlia.network import Server

async def run():
    node = Server()
    await node.listen(5678)

    node_id = node.node.id
    print("node_id =", node_id)

    # Mantieni il nodo attivo indefinitamente
    try:
        await asyncio.Future()  # blocca per sempre
    except asyncio.CancelledError:
        pass

asyncio.run(run())
