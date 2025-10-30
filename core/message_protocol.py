from pydantic import BaseModel, Field
from typing import Optional, Any, Dict
from datetime import datetime
from core.node_states import NodeRole



class MessageType(str):
    """Tipi di messaggi nel protocollo CQKD"""
    # Role management
    ROLE_REQUEST = "role_request"
    ROLE_ACCEPT = "role_accept"
    ROLE_REJECT = "role_reject"
    ROLE_RELEASE = "role_release"

    # Quantum operations
    SPIN_GENERATE = "spin_generate"
    BASE_GENERATE = "base_generate"
    PHOTON_POLARIZE = "photon_polarize"
    PHOTON_MEASURE = "photon_measure"
    PHOTON_COLLIDE = "photon_collide"

    # Results
    RESULT_READY = "result_ready"
    ERROR = "error"

class CQKDMessage(BaseModel):
    """Messaggio base del protocollo CQKD"""
    message_id: str = Field(default_factory=lambda: datetime.now().timestamp())
    message_type: str
    sender_id: str
    recipient_id: Optional[str] = None
    process_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    payload: Dict[str, Any]
    signature: Optional[str] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class RoleRequestMessage(BaseModel):
    """Richiesta di assegnamento ruolo"""
    process_id: str
    role: NodeRole
    sender_address: str
    timeout_seconds: int = 300
    metadata: Dict[str, Any] = {}

class QuantumOperationMessage(BaseModel):
    """Messaggio per operazione quantistica"""
    operation_id: str
    process_id: str
    role: NodeRole
    input_data: Dict[str, Any]
    target_nodes: list[str] = []


class ResultMessage(BaseModel):
    """Risultato di un'operazione quantistica"""
    operation_id: str
    process_id: str
    role: NodeRole
    result_data: Dict[str, Any]
    success: bool
    error_message: Optional[str] = None