from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
import os


class Settings(BaseSettings):
    """Configurazione globale del sistema CQKD"""

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False
    )

    # DHT Configuration
    dht_port: int = 5678
    bootstrap_nodes: str = "127.0.0.1:5678"
    node_id: Optional[str] = None

    # Node Configuration
    node_type: str = "worker"  # bootstrap, worker, alice, bob
    max_concurrent_roles: int = 5
    role_timeout_seconds: int = 300

    # Protocol Configuration
    key_length_multiplier: float = 2.5  # lk = multiplier * lc
    required_nodes_multiplier: int = 5  # 5lk nodes required

    # Security Configuration
    enable_channel_encryption: bool = True
    tls_cert_path: Optional[str] = None
    tls_key_path: Optional[str] = None

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # json or text

    # Performance
    max_retries: int = 3
    request_timeout_seconds: int = 30

    # Monitoring
    enable_prometheus: bool = False
    prometheus_port: int = 9090

    @property
    def bootstrap_nodes_list(self) -> List[tuple]:
        """Parse bootstrap nodes from string"""
        nodes = []
        for node in self.bootstrap_nodes.split(','):
            node = node.strip()
            if ':' in node:
                host, port = node.split(':')
                nodes.append((host, int(port)))
        return nodes


# Istanza globale delle settings
settings = Settings()
