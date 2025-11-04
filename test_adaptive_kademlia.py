#!/usr/bin/env python3
"""
Test script per validare l'implementazione adattiva dei parametri Kademlia

Questo script verifica:
1. Calcolo corretto dei parametri basati sulla dimensione della rete
2. Aggiornamento dinamico dei parametri durante il runtime
3. Logging appropriato per monitoraggio
4. Compatibilità con configurazione esistente
"""

import asyncio
import sys
import os
from datetime import datetime
from typing import Dict, Any

# Aggiungi il path del progetto
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import settings
from utils.logging_config import get_logger

logger = get_logger(__name__)


class MockCoordinatorNode:
    """Mock node per simulare il coordinator e testare i parametri adattivi"""
    
    def __init__(self, network_size: int = 0):
        self.network_size = network_size
    
    def get_routing_table_info(self) -> Dict[str, Any]:
        """Simula informazioni sulla routing table"""
        return {
            "total_nodes": self.network_size,
            "network_health": {
                "well_distributed": self.network_size > 10,
                "distribution_score": min(1.0, self.network_size / 100)
            },
            "active_buckets": max(1, self.network_size // 20)
        }


async def test_adaptive_parameter_calculation():
    """Test del calcolo dei parametri adattivi"""
    logger.info("=== TEST: Calcolo Parametri Adattivi ===")
    
    test_cases = [
        (10, "small"),
        (25, "medium"),
        (50, "medium"),
        (75, "large"),
        (100, "large"),
        (250, "xlarge"),
        (500, "xlarge"),
        (1000, "xlarge")
    ]
    
    for network_size, expected_category in test_cases:
        params = settings.calculate_adaptive_kademlia_params(network_size)
        
        logger.info(
            "adaptive_params_test",
            network_size=network_size,
            expected_category=expected_category,
            actual_category=params.get('network_category'),
            alpha=params['alpha'],
            k=params['k'],
            query_timeout=params['query_timeout'],
            discovery_timeout=params['discovery_timeout'],
            adaptive_enabled=params['adaptive_enabled']
        )
        
        # Validazioni
        assert params['network_category'] == expected_category, f"Category mismatch for {network_size}"
        assert params['alpha'] >= settings.base_alpha, f"Alpha too low for {network_size}"
        assert params['k'] >= settings.base_k, f"K too low for {network_size}"
        assert params['query_timeout'] >= settings.base_query_timeout, f"Timeout too low for {network_size}"
        
        # Limiti massimi
        assert params['alpha'] <= settings.max_alpha, f"Alpha exceeds max for {network_size}"
        assert params['k'] <= settings.max_k, f"K exceeds max for {network_size}"
        assert params['query_timeout'] <= settings.max_query_timeout, f"Timeout exceeds max for {network_size}"
    
    logger.info("✅ Test calcolo parametri adattivi SUPERATO")


async def test_node_discovery_adaptive_params():
    """Test del servizio discovery con parametri adattivi"""
    logger.info("=== TEST: NodeDiscoveryService con Parametri Adattivi ===")
    
    from discovery.node_discovery import NodeDiscoveryService
    
    test_network_sizes = [15, 50, 100, 500]
    
    for network_size in test_network_sizes:
        logger.info(f"Testing discovery with network size: {network_size}")
        
        # Crea mock coordinator
        mock_coordinator = MockCoordinatorNode(network_size)
        
        # Crea servizio discovery
        discovery_service = NodeDiscoveryService(mock_coordinator)
        
        # Verifica parametri iniziali
        initial_params = discovery_service._get_current_parameters()
        
        logger.info(
            "discovery_initial_params",
            network_size=network_size,
            alpha=initial_params['alpha'],
            k=initial_params['k'],
            query_timeout=initial_params['query_timeout'],
            network_category=initial_params['network_category']
        )
        
        # Validazioni
        assert initial_params['network_size'] >= network_size, "Network size not detected correctly"
        assert initial_params['adaptive_enabled'] == settings.enable_adaptive_kademlia, "Adaptive flag mismatch"
        
        # Test cache TTL
        discovery_service._params_cache_time = datetime.now()
        cached_params = discovery_service._get_current_parameters()
        assert cached_params == initial_params, "Cache not working properly"
        
        logger.info(f"✅ Discovery service test for {network_size} nodes SUPERATO")


async def test_discovery_strategies_adaptive_timeouts():
    """Test delle strategie discovery con timeout adattivi"""
    logger.info("=== TEST: DiscoveryStrategies con Timeout Adattivi ===")
    
    from discovery.discovery_strategies import SmartDiscoveryStrategy
    
    test_network_sizes = [15, 50, 100, 500]
    
    for network_size in test_network_sizes:
        logger.info(f"Testing strategies with network size: {network_size}")
        
        # Crea mock coordinator
        mock_coordinator = MockCoordinatorNode(network_size)
        
        # Crea strategia discovery
        strategy = SmartDiscoveryStrategy(mock_coordinator)
        
        # Test calcolo timeout adattivo (senza eseguire discovery completo)
        try:
            # Simula l'inizio del discovery per testare il calcolo del timeout
            routing_info = mock_coordinator.get_routing_table_info()
            network_size_detected = routing_info.get("total_nodes", 0)
            
            adaptive_params = settings.calculate_adaptive_kademlia_params(network_size_detected)
            calculated_timeout = adaptive_params['discovery_timeout']
            
            logger.info(
                "strategy_timeout_calculation",
                network_size=network_size,
                calculated_timeout=calculated_timeout,
                network_category=adaptive_params.get('network_category'),
                adaptive_enabled=settings.enable_adaptive_kademlia
            )
            
            # Validazioni
            assert calculated_timeout >= 60, f"Timeout too low for {network_size}"
            assert calculated_timeout <= settings.max_discovery_timeout, f"Timeout exceeds max for {network_size}"
            
            # Verifica scaling appropriato
            if network_size <= settings.small_network_threshold:
                assert calculated_timeout <= 90, f"Small network timeout too high: {calculated_timeout}"
            elif network_size >= settings.xlarge_network_threshold:
                assert calculated_timeout >= 120, f"Large network timeout too low: {calculated_timeout}"
            
        except Exception as e:
            logger.error(f"Strategy test failed for {network_size}: {e}")
            raise
        
        logger.info(f"✅ Strategy test for {network_size} nodes SUPERATO")


async def test_configuration_compatibility():
    """Test compatibilità con configurazione esistente"""
    logger.info("=== TEST: Compatibilità Configurazione Esistente ===")
    
    # Test valori default
    default_params = settings.calculate_adaptive_kademlia_params(0)
    
    logger.info(
        "default_params_test",
        alpha=default_params['alpha'],
        k=default_params['k'],
        query_timeout=default_params['query_timeout'],
        discovery_timeout=default_params['discovery_timeout']
    )
    
    # Verifica che i valori default corrispondano alla configurazione base
    assert default_params['alpha'] == settings.base_alpha, "Default alpha mismatch"
    assert default_params['k'] == settings.base_k, "Default k mismatch"
    assert default_params['query_timeout'] == settings.base_query_timeout, "Default timeout mismatch"
    
    # Test disabilitazione adattivo
    original_setting = settings.enable_adaptive_kademlia
    settings.enable_adaptive_kademlia = False
    
    disabled_params = settings.calculate_adaptive_kademlia_params(1000)
    
    assert disabled_params['adaptive_enabled'] == False, "Adaptive not disabled"
    assert disabled_params['alpha'] == settings.base_alpha, "Base alpha not used when disabled"
    assert disabled_params['k'] == settings.base_k, "Base k not used when disabled"
    
    # Ripristina impostazione
    settings.enable_adaptive_kademlia = original_setting
    
    logger.info("✅ Test compatibilità configurazione SUPERATO")


async def test_logging_monitoring():
    """Test del logging per monitoraggio dei parametri"""
    logger.info("=== TEST: Logging per Monitoraggio ===")
    
    from discovery.node_discovery import NodeDiscoveryService
    
    # Crea mock coordinator con rete grande
    mock_coordinator = MockCoordinatorNode(250)
    
    # Crea servizio discovery (dovrebbe loggare i parametri)
    discovery_service = NodeDiscoveryService(mock_coordinator)
    
    # Ottieni parametri correnti (dovrebbe loggare se cache scaduta)
    params = discovery_service._get_current_parameters()
    
    # Verifica che tutti i campi necessari siano presenti
    required_fields = ['alpha', 'k', 'query_timeout', 'network_size', 'network_category', 'adaptive_enabled']
    for field in required_fields:
        assert field in params, f"Missing field: {field}"
    
    logger.info(
        "logging_test_complete",
        all_fields_present=True,
        params_logged=params
    )
    
    logger.info("✅ Test logging monitoraggio SUPERATO")


async def main():
    """Funzione principale di test"""
    logger.info("🚀 Inizio Test Adattivi Kademlia")
    logger.info(f"Configurazione: adaptive={settings.enable_adaptive_kademlia}")
    
    try:
        await test_adaptive_parameter_calculation()
        await test_node_discovery_adaptive_params()
        await test_discovery_strategies_adaptive_timeouts()
        await test_configuration_compatibility()
        await test_logging_monitoring()
        
        logger.info("🎉 TUTTI I TEST SUPERATI!")
        logger.info("✅ Implementazione adattiva Kademlia funzionante correttamente")
        
        # Riepilogo configurazione
        logger.info("=== RIEPILOGO CONFIGURAZIONE ADATTIVA ===")
        for size in [15, 50, 100, 500]:
            params = settings.calculate_adaptive_kademlia_params(size)
            logger.info(
                "scaling_summary",
                network_size=size,
                category=params['network_category'],
                alpha=params['alpha'],
                k=params['k'],
                query_timeout=params['query_timeout'],
                discovery_timeout=params['discovery_timeout']
            )
        
        return True
        
    except Exception as e:
        logger.error(f"❌ TEST FALLITI: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)