"""
Worker Executor - Executes quantum operations on worker nodes.
This is the CORE component that enables distributed execution.
"""

import asyncio
import json
from typing import Dict, Any, Optional
from datetime import datetime

from core.dht_node import CQKDNode
from core.node_states import NodeRole
from quantum.qsg import QuantumSpinGenerator
from quantum.bg import BaseGenerator
from quantum.qpp import QuantumPhotonPolarizer
from quantum.qpm import QuantumPhotonMeter
from quantum.qpc import QuantumPhotonCollider
from utils.logging_config import get_logger

logger = get_logger(__name__)


class WorkerExecutor:
    """
    Executor that polls DHT for commands and executes quantum operations.
    This implements the distributed execution model from the CQKD paper.
    """
    
    def __init__(self, node: CQKDNode, polling_interval: float = 0.3):
        self.node = node
        self.polling_interval = polling_interval
        self.running = False
        self.processed_commands = set()
        
        # Map roles to quantum component classes
        self.role_components = {
            NodeRole.QSG: QuantumSpinGenerator,
            NodeRole.BG: BaseGenerator,
            NodeRole.QPP: QuantumPhotonPolarizer,
            NodeRole.QPM: QuantumPhotonMeter,
            NodeRole.QPC: QuantumPhotonCollider
        }
    
    async def start(self):
        """Start the executor loop - polls DHT and executes commands."""
        self.running = True
        logger.info(
            "worker_executor_started",
            node_id=self.node.node_id,
            polling_interval=self.polling_interval
        )
        
        while self.running:
            try:
               
                await self._poll_and_execute()
                await asyncio.sleep(self.polling_interval)
                
            except asyncio.CancelledError:
                logger.info("worker_executor_cancelled", node_id=self.node.node_id)
                break
                
            except Exception as e:
                logger.error(
                    "worker_executor_error",
                    node_id=self.node.node_id,
                    error=str(e)
                )
                await asyncio.sleep(1)
    
    async def stop(self):
        """Stop the executor loop."""
        self.running = False
        logger.info("worker_executor_stopped", node_id=self.node.node_id)
    
    async def _poll_and_execute(self):
        """
        Poll DHT for commands addressed to this node.
        Command key pattern: {process_id}:cmd:{node_id}
        """
        try:
            # Check for command addressed to this specific node
            cmd_key = f"cmd:{self.node.node_id}"
            command_data = await self.node.retrieve_data(cmd_key)

            # ✅ Esegui solo se è un dict valido
            if command_data and isinstance(command_data, dict):
                cmd_id = command_data.get('cmd_id')

                if cmd_id in self.processed_commands:
                    return

                await self._execute_command(command_data)
                self.processed_commands.add(cmd_id)

                # Clean old processed commands
                if len(self.processed_commands) > 1000:
                    self.processed_commands = set(list(self.processed_commands)[-500:])

                #await self.node.delete_data(cmd_key)

                
        except Exception as e:
            logger.debug(
                "poll_error",
                node_id=self.node.node_id,
                error=str(e)
            )
    
    async def _execute_command(self, command: Dict[str, Any]):
        """
        Execute a quantum operation command based on role.
        """
        role_str = command.get('role')
        role = NodeRole(role_str) if role_str else None
        
        if not role or role not in self.role_components:
            logger.warning(
                "invalid_role_in_command",
                node_id=self.node.node_id,
                role=role_str
            )
            return
        
        logger.info(
            "worker_executing_quantum_operation",
            node_id=self.node.node_id,
            role=role.value,
            cmd_id=command.get('cmd_id'),
            process_id=command.get('process_id')
        )
        
        try:
            # Acquire role temporarily
            await self.node.request_role(
                role=role,
                process_id=command['process_id'],
                timeout_seconds=300
            )
            
            # Get quantum component
            component_class = self.role_components[role]
            
            # Execute based on role using the execute() method
            result = await component_class.execute(
                node=self.node,
                **command.get('params', {})
            ) 

            component_class = self.role_components[role]
            params = command.get("params", {})

            
            logger.info(
                "worker_operation_completed",
                node_id=self.node.node_id,
                role=role.value,
                cmd_id=command.get('cmd_id'),
                success=result.get('success', True)
            )
            
        except Exception as e:
            logger.error(
                "worker_operation_failed",
                node_id=self.node.node_id,
                role=role_str,
                cmd_id=command.get('cmd_id'),
                error=str(e),
                exc_info=True
            )
            
            # Store error in DHT for coordinator to see
            error_key = f"{command['process_id']}:error:{command.get('cmd_id')}"
            await self.node.store_data(error_key, {
                "error": str(e),
                "node": self.node.node_id,
                "role": role_str,
                "timestamp": datetime.now().isoformat()
            })
            
        finally:
            # Release role
            await self.node.release_role()