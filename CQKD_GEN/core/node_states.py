from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


class NodeState(str, Enum):
    """Stati possibili di un nodo DHT"""
    OFF = "off"
    ACTIVE = "active"
    BUSY = "busy"
    ERROR = "error"

class NodeRole(str, Enum):
    """Ruoli quantistici che un nodo può assumere"""
    NONE = "none"
    QSG = "qsg"  # Quantum Spin Generator
    BG = "bg"    # Base Generator
    QPP = "qpp"  # Quantum Photon Polarizer
    QPM = "qpm"  # Quantum Photon Meter
    QPC = "qpc"  # Quantum Photon Collider


@dataclass
class NodeRoleAssignment:
    """Assegnamento di ruolo a un nodo"""
    role: NodeRole
    process_id: str
    assigned_at: datetime
    expires_at: datetime
    metadata: dict

    def is_expired(self) -> bool:
        """Verifica se l'assegnamento è scaduto"""
        return datetime.now() > self.expires_at


@dataclass
class NodeInfo:
    """Informazioni su un nodo DHT"""
    node_id: str
    address: str
    port: int
    state: NodeState
    current_role: Optional[NodeRoleAssignment]
    last_seen: datetime
    capabilities: list[NodeRole]

    def can_accept_role(self, role: NodeRole) -> bool:
        """Verifica se il nodo può accettare un determinato ruolo"""
        return (
            self.state == NodeState.ACTIVE and
            role in self.capabilities and
            (self.current_role is None or self.current_role.is_expired())
        )