#!/usr/bin/env python3
"""
Script di test per verificare il funzionamento del sistema di porte dinamiche
per i worker CQKD DHT.
"""

import subprocess
import time
import re
import sys
from typing import List, Dict, Tuple

def run_command(cmd: List[str], timeout: int = 30) -> Tuple[int, str, str]:
    """Esegue un comando e restituisce exit code, stdout, stderr"""
    try:
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"

def get_worker_ports() -> List[int]:
    """Ottiene le porte DHT dei worker in esecuzione"""
    cmd = ["docker", "ps", "--filter", "name=cqkd", "--format", "{{.Names}}:{{.Ports}}"]
    exit_code, stdout, stderr = run_command(cmd)
    
    if exit_code != 0:
        print(f"Errore nel ottenere i container: {stderr}")
        return []
    
    ports = []
    for line in stdout.strip().split('\n'):
        if 'worker' in line.lower():
            # Estrai le porte UDP dal formato "0.0.0.0:7000->7000/udp"
            udp_ports = re.findall(r'(\d+)->\d+/udp', line)
            for port_str in udp_ports:
                ports.append(int(port_str))
    
    return ports

def test_scaling(worker_counts: List[int]) -> bool:
    """Testa lo scaling con diversi numeri di worker"""
    print("=== Test Dynamic Ports System ===\n")
    
    # Pulisci container esistenti
    print("1. Pulizia container esistenti...")
    run_command(["docker", "compose", "down", "--remove-orphans"])
    time.sleep(2)
    
    # Avvia i servizi base (bootstrap, alice, bob)
    print("2. Avvio servizi base...")
    exit_code, stdout, stderr = run_command(["docker", "compose", "up", "-d", "bootstrap-primary", "bootstrap-secondary", "alice", "bob"])
    
    if exit_code != 0:
        print(f"❌ Errore avvio servizi base: {stderr}")
        return False
    
    print("✓ Servizi base avviati")
    time.sleep(10)  # Attendi che i bootstrap siano pronti
    
    # Test con diversi numeri di worker
    for worker_count in worker_counts:
        print(f"\n3. Test con {worker_count} worker...")
        
        # Scala i worker
        exit_code, stdout, stderr = run_command([
            "docker", "compose", "up", "-d", "--scale", f"worker={worker_count}"
        ])
        
        if exit_code != 0:
            print(f"❌ Errore scaling a {worker_count} worker: {stderr}")
            return False
        
        print(f"✓ Scaling a {worker_count} worker avviato")
        time.sleep(15)  # Attendi che i worker si avviino
        
        # Controlla le porte assegnate
        ports = get_worker_ports()
        unique_ports = set(ports)
        
        print(f"   - Worker totali: {len(ports)}")
        print(f"   - Porte uniche: {len(unique_ports)}")
        print(f"   - Porte: {sorted(unique_ports)}")
        
        # Verifica che tutte le porte siano uniche
        if len(ports) != len(unique_ports):
            print(f"❌ Conflitto di porte rilevato! {len(ports)} worker ma solo {len(unique_ports)} porte uniche")
            return False
        
        # Verifica che le porte siano nel range corretto
        invalid_ports = [p for p in unique_ports if p < 7000 or p >= 8000]
        if invalid_ports:
            print(f"❌ Porte fuori range rilevate: {invalid_ports}")
            return False
        
        print(f"✓ Test {worker_count} worker superato")
    
    return True

def test_container_logs() -> bool:
    """Verifica i log dei container per messaggi di porta assegnata"""
    print("\n4. Analisi log container...")
    
    cmd = ["docker", "compose", "logs", "worker"]
    exit_code, stdout, stderr = run_command(cmd)
    
    if exit_code != 0:
        print(f"❌ Errore nel leggere i log: {stderr}")
        return False
    
    # Cerca messaggi di porta assegnata
    port_assignments = re.findall(r'Final assigned port: (\d+)', stdout)
    
    if not port_assignments:
        print("❌ Nessun messaggio di assegnazione porta trovato nei log")
        return False
    
    print(f"✓ Trovate {len(port_assignments)} assegnazioni di porte nei log")
    print(f"   - Porte assegnate: {sorted(set(map(int, port_assignments)))}")
    
    return True

def main():
    """Funzione principale di test"""
    print("CQKD DHT Dynamic Ports Test Suite")
    print("==================================\n")
    
    # Sequenza di test con scaling progressivo
    worker_counts = [1, 5, 10]
    
    try:
        # Esegui test di scaling
        if not test_scaling(worker_counts):
            print("\n❌ Test di scaling fallito")
            sys.exit(1)
        
        # Analizza i log
        if not test_container_logs():
            print("\n❌ Analisi log fallita")
            sys.exit(1)
        
        print("\n✅ Tutti i test superati con successo!")
        print("\nRiepilogo:")
        print(f"- Testato scaling con {worker_counts} worker")
        print("- Verificata unicità delle porte")
        print("- Verificato range porte (7000-8000)")
        print("- Verificati log di assegnazione")
        
    except Exception as e:
        print(f"\n❌ Errore durante i test: {e}")
        sys.exit(1)
    
    finally:
        # Pulizia finale
        print("\n5. Pulizia finale...")
        run_command(["docker", "compose", "down", "--remove-orphans"])

if __name__ == "__main__":
    main()