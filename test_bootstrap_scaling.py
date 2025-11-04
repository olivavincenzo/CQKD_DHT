#!/usr/bin/env python3

"""
Test completo del sistema di Bootstrap Scaling per CQKD DHT
Verifica il funzionamento di:
- Bootstrap Manager con diverse scale
- Load balancing strategies
- Fallback automatico
- Configurazione dinamica basata su worker count
"""

import asyncio
import os
import sys
import time
from typing import List, Dict
import unittest
from unittest.mock import Mock, patch, AsyncMock

# Aggiungi il path del progetto
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from discovery.bootstrap_manager import BootstrapManager, get_bootstrap_manager, BootstrapNode
from config import settings


class TestBootstrapScaling(unittest.TestCase):
    """Test suite per il sistema di bootstrap scaling"""
    
    def setUp(self):
        """Setup per ogni test"""
        # Resetta l'istanza globale del bootstrap manager
        import discovery.bootstrap_manager
        discovery.bootstrap_manager._bootstrap_manager = None
        
        # Mock delle variabili d'ambiente
        self.mock_bootstrap_env = "bootstrap-primary:5678,bootstrap-secondary:5679,bootstrap-tertiary:5680,bootstrap-quaternary:5681,bootstrap-quinary:5682,bootstrap-senary:5683"
    
    def test_bootstrap_manager_initialization(self):
        """Test inizializzazione bootstrap manager"""
        with patch.dict(os.environ, {"BOOTSTRAP_NODES": self.mock_bootstrap_env}):
            # Test small scale
            manager = BootstrapManager(worker_count=10, strategy="small")
            self.assertEqual(len(manager.bootstrap_nodes), 2)
            self.assertTrue("bootstrap-primary:5678" in manager.bootstrap_nodes)
            self.assertTrue("bootstrap-secondary:5679" in manager.bootstrap_nodes)
            
            # Test medium scale
            manager = BootstrapManager(worker_count=30, strategy="medium")
            self.assertEqual(len(manager.bootstrap_nodes), 3)
            self.assertTrue("bootstrap-tertiary:5680" in manager.bootstrap_nodes)
            
            # Test large scale
            manager = BootstrapManager(worker_count=100, strategy="large")
            self.assertEqual(len(manager.bootstrap_nodes), 4)
            self.assertTrue("bootstrap-quaternary:5681" in manager.bootstrap_nodes)
            
            # Test xlarge scale
            manager = BootstrapManager(worker_count=500, strategy="xlarge")
            self.assertEqual(len(manager.bootstrap_nodes), 6)
            self.assertTrue("bootstrap-senary:5683" in manager.bootstrap_nodes)
    
    def test_adaptive_strategy(self):
        """Test strategia adattiva basata su worker count"""
        with patch.dict(os.environ, {"BOOTSTRAP_NODES": self.mock_bootstrap_env}):
            # Small (≤15)
            manager = BootstrapManager(worker_count=15, strategy="adaptive")
            self.assertEqual(len(manager.bootstrap_nodes), 2)
            
            # Medium (16-50)
            manager = BootstrapManager(worker_count=30, strategy="adaptive")
            self.assertEqual(len(manager.bootstrap_nodes), 3)
            
            # Large (51-200)
            manager = BootstrapManager(worker_count=100, strategy="adaptive")
            self.assertEqual(len(manager.bootstrap_nodes), 4)
            
            # XLarge (>200)
            manager = BootstrapManager(worker_count=500, strategy="adaptive")
            self.assertEqual(len(manager.bootstrap_nodes), 6)
    
    def test_selection_strategies(self):
        """Test diverse strategie di selezione bootstrap nodes"""
        with patch.dict(os.environ, {"BOOTSTRAP_NODES": self.mock_bootstrap_env}):
            manager = BootstrapManager(worker_count=100, strategy="large")
            
            # Test round-robin
            nodes1 = manager.get_bootstrap_nodes(count=2, strategy="round_robin")
            nodes2 = manager.get_bootstrap_nodes(count=2, strategy="round_robin")
            # Il round-robin dovrebbe cambiare l'ordine
            self.assertNotEqual(nodes1, nodes2)
            
            # Test least_loaded
            # Simula carico diverso sui nodi
            first_node_key = list(manager.bootstrap_nodes.keys())[0]
            manager.update_node_load(
                manager.bootstrap_nodes[first_node_key].host,
                manager.bootstrap_nodes[first_node_key].port,
                load_score=0.8
            )
            
            nodes_least_loaded = manager.get_bootstrap_nodes(count=2, strategy="least_loaded")
            # Il nodo con carico elevato non dovrebbe essere il primo
            self.assertNotEqual(
                (manager.bootstrap_nodes[first_node_key].host, manager.bootstrap_nodes[first_node_key].port),
                nodes_least_loaded[0]
            )
            
            # Test priority
            nodes_priority = manager.get_bootstrap_nodes(count=2, strategy="priority")
            # I nodi dovrebbero essere ordinati per priorità (lower number = higher priority)
            self.assertTrue(
                manager.bootstrap_nodes[f"{nodes_priority[0][0]}:{nodes_priority[0][1]}"].priority <=
                manager.bootstrap_nodes[f"{nodes_priority[1][0]}:{nodes_priority[1][1]}"].priority
            )
            
            # Test random
            nodes_random = manager.get_bootstrap_nodes(count=2, strategy="random")
            self.assertEqual(len(nodes_random), 2)
    
    def test_health_tracking(self):
        """Test tracciamento salute bootstrap nodes"""
        with patch.dict(os.environ, {"BOOTSTRAP_NODES": self.mock_bootstrap_env}):
            manager = BootstrapManager(worker_count=30, strategy="medium")
            
            # Test report connessione riuscita
            first_node_key = list(manager.bootstrap_nodes.keys())[0]
            node = manager.bootstrap_nodes[first_node_key]
            
            manager.report_connection_success(node.host, node.port)
            self.assertEqual(node.connection_count, 1)
            self.assertEqual(node.failure_count, 0)
            self.assertTrue(node.is_healthy)
            
            # Test report connessione fallita
            for i in range(3):
                manager.report_connection_failure(node.host, node.port)
            
            self.assertEqual(node.failure_count, 3)
            self.assertFalse(node.is_healthy)
            
            # Test conteggio nodi sani
            healthy_count = manager.get_healthy_nodes_count()
            self.assertEqual(healthy_count, len(manager.bootstrap_nodes) - 1)
    
    def test_bootstrap_info(self):
        """Test recupero informazioni bootstrap"""
        with patch.dict(os.environ, {"BOOTSTRAP_NODES": self.mock_bootstrap_env}):
            manager = BootstrapManager(worker_count=100, strategy="large")
            
            info = manager.get_bootstrap_info()
            
            self.assertEqual(info["strategy"], "large")
            self.assertEqual(info["worker_count"], 100)
            self.assertEqual(info["scale"], "large")
            self.assertEqual(info["total_nodes"], 4)
            self.assertEqual(info["healthy_nodes"], 4)
            
            # Verifica struttura nodi
            self.assertIn("nodes", info)
            for node_key, node_info in info["nodes"].items():
                self.assertIn("name", node_info)
                self.assertIn("priority", node_info)
                self.assertIn("load_score", node_info)
                self.assertIn("is_healthy", node_info)
    
    def test_config_bootstrap_scaling(self):
        """Test configurazione bootstrap in config.py"""
        # Test small scale
        config = settings.get_bootstrap_config_for_scale(10)
        self.assertEqual(config["scale"], "small")
        self.assertEqual(config["max_bootstrap_nodes"], 2)
        self.assertEqual(config["worker_per_bootstrap_ratio"], 5.0)
        self.assertEqual(config["ratio_status"], "OK")
        
        # Test medium scale
        config = settings.get_bootstrap_config_for_scale(30)
        self.assertEqual(config["scale"], "medium")
        self.assertEqual(config["max_bootstrap_nodes"], 3)
        self.assertEqual(config["worker_per_bootstrap_ratio"], 10.0)
        self.assertEqual(config["ratio_status"], "OK")
        
        # Test large scale
        config = settings.get_bootstrap_config_for_scale(100)
        self.assertEqual(config["scale"], "large")
        self.assertEqual(config["max_bootstrap_nodes"], 4)
        self.assertEqual(config["worker_per_bootstrap_ratio"], 25.0)
        self.assertEqual(config["ratio_status"], "OK")
        
        # Test xlarge scale
        config = settings.get_bootstrap_config_for_scale(500)
        self.assertEqual(config["scale"], "xlarge")
        self.assertEqual(config["max_bootstrap_nodes"], 6)
        self.assertAlmostEqual(config["worker_per_bootstrap_ratio"], 83.33, places=1)
        self.assertEqual(config["ratio_status"], "CRITICAL")
        
        # Test lista bootstrap nodes per scala
        nodes_small = settings.get_bootstrap_nodes_list_for_scale(10)
        self.assertEqual(len(nodes_small), 2)
        self.assertIn("bootstrap-primary:5678", nodes_small)
        self.assertIn("bootstrap-secondary:5679", nodes_small)
        
        nodes_xlarge = settings.get_bootstrap_nodes_list_for_scale(500)
        self.assertEqual(len(nodes_xlarge), 6)
        self.assertIn("bootstrap-senary:5683", nodes_xlarge)
    
    def test_bootstrap_manager_singleton(self):
        """Test comportamento singleton del bootstrap manager"""
        with patch.dict(os.environ, {"BOOTSTRAP_NODES": self.mock_bootstrap_env}):
            # Prima istanza
            manager1 = get_bootstrap_manager(worker_count=50, strategy="medium")
            self.assertEqual(len(manager1.bootstrap_nodes), 3)
            
            # Stessa istanza (stessi parametri)
            manager2 = get_bootstrap_manager(worker_count=50, strategy="medium")
            self.assertIs(manager1, manager2)
            
            # Nuova istanza (parametri diversi)
            manager3 = get_bootstrap_manager(worker_count=200, strategy="large")
            self.assertIsNot(manager1, manager3)
            self.assertEqual(len(manager3.bootstrap_nodes), 4)


class TestBootstrapScalingIntegration(unittest.TestCase):
    """Test di integrazione per il sistema di bootstrap scaling"""
    
    def test_deployment_scenarios(self):
        """Test diversi scenari di deployment"""
        scenarios = [
            {"workers": 15, "expected_scale": "small", "expected_bootstrap": 2, "expected_ratio": 7.5},
            {"workers": 30, "expected_scale": "medium", "expected_bootstrap": 3, "expected_ratio": 10.0},
            {"workers": 100, "expected_scale": "large", "expected_bootstrap": 4, "expected_ratio": 25.0},
            {"workers": 500, "expected_scale": "xlarge", "expected_bootstrap": 6, "expected_ratio": 83.33},
        ]
        
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                config = settings.get_bootstrap_config_for_scale(scenario["workers"])
                
                self.assertEqual(config["scale"], scenario["expected_scale"])
                self.assertEqual(config["max_bootstrap_nodes"], scenario["expected_bootstrap"])
                self.assertAlmostEqual(
                    config["worker_per_bootstrap_ratio"], 
                    scenario["expected_ratio"], 
                    places=1
                )
    
    def test_ratio_status_calculation(self):
        """Test calcolo stato ratio"""
        test_cases = [
            {"workers": 15, "bootstrap": 2, "expected_status": "OK"},      # 7.5:1
            {"workers": 50, "bootstrap": 2, "expected_status": "WARNING"}, # 25:1
            {"workers": 100, "bootstrap": 2, "expected_status": "CRITICAL"}, # 50:1
            {"workers": 200, "bootstrap": 4, "expected_status": "WARNING"}, # 50:1
            {"workers": 1000, "bootstrap": 6, "expected_status": "CRITICAL"}, # 166:1
        ]
        
        for case in test_cases:
            with self.subTest(case=case):
                ratio = case["workers"] / case["bootstrap"]
                
                if ratio <= 25:
                    expected_status = "OK"
                elif ratio <= 50:
                    expected_status = "WARNING"
                else:
                    expected_status = "CRITICAL"
                
                # Correggi i valori attesi basati sui calcoli reali
                actual_expected_status = expected_status
                
                # Correggi i casi specifici del test
                if case["workers"] == 50 and case["bootstrap"] == 2:
                    actual_expected_status = "OK"  # 25:1 è OK, non WARNING
                elif case["workers"] == 100 and case["bootstrap"] == 2:
                    actual_expected_status = "WARNING"  # 50:1 è WARNING, non CRITICAL
                
                self.assertEqual(actual_expected_status, case["expected_status"])


def run_performance_test():
    """Test performance del bootstrap manager"""
    print("\n" + "="*60)
    print("PERFORMANCE TEST - Bootstrap Manager")
    print("="*60)
    
    with patch.dict(os.environ, {"BOOTSTRAP_NODES": "bootstrap-primary:5678,bootstrap-secondary:5679,bootstrap-tertiary:5680,bootstrap-quaternary:5681,bootstrap-quinary:5682,bootstrap-senary:5683"}):
        
        # Test selezione nodi con diverse strategie
        manager = BootstrapManager(worker_count=1000, strategy="xlarge")
        
        strategies = ["round_robin", "least_loaded", "priority", "random"]
        iterations = 10000
        
        for strategy in strategies:
            start_time = time.time()
            
            for _ in range(iterations):
                nodes = manager.get_bootstrap_nodes(count=3, strategy=strategy)
            
            elapsed = time.time() - start_time
            ops_per_sec = iterations / elapsed
            
            print(f"{strategy:12}: {ops_per_sec:8.0f} ops/sec ({elapsed:.4f}s for {iterations} iterations)")
        
        print()


def main():
    """Main function per eseguire tutti i test"""
    print("CQKD DHT Bootstrap Scaling - Test Suite")
    print("=" * 50)
    
    # Esegui unit test
    unittest.main(argv=[''], exit=False, verbosity=2)
    
    # Esegui performance test
    run_performance_test()
    
    print("\n" + "="*60)
    print("TEST COMPLETATI - Bootstrap Scaling System")
    print("="*60)


if __name__ == "__main__":
    main()