#!/bin/bash

# Script di entry point per worker con assegnazione dinamica delle porte
# Risolve il problema dei conflitti di porta quando si fa scaling con più istanze

set -e

# Configurazione range porte
PORT_RANGE_START=7000
PORT_RANGE_END=8000
MAX_WORKERS=$((PORT_RANGE_END - PORT_RANGE_START))

# Funzione per calcolare la porta unica basandosi sull'hostname
calculate_unique_port() {
    local hostname=$1
    local port
    
    # Estrai il numero dall'hostname (es: worker_1 -> 1)
    if [[ $hostname =~ worker_([0-9]+) ]]; then
        local instance_num=${BASH_REMATCH[1]}
        
        # Calcola la porta usando l'instance number
        # Assicura che sia nel range consentito
        port=$((PORT_RANGE_START + (instance_num - 1) % MAX_WORKERS))
        
        echo $port
        return 0
    fi
    
    # Fallback: usa hash dell'hostname per generare un numero
    local hash=$(echo -n "$hostname" | md5sum | cut -c1-8)
    local hash_num=$((0x${hash}))
    port=$((PORT_RANGE_START + (hash_num % MAX_WORKERS)))
    
    echo $port
    return 0
}

# Funzione per verificare se la porta è disponibile
is_port_available() {
    local port=$1
    
    # Controlla se la porta è già in uso
    if netstat -uln 2>/dev/null | grep -q ":$port "; then
        return 1
    fi
    
    # Controlla con ss come alternativa
    if command -v ss >/dev/null 2>&1; then
        if ss -uln 2>/dev/null | grep -q ":$port "; then
            return 1
        fi
    fi
    
    return 0
}

# Funzione per trovare una porta disponibile nel range
find_available_port() {
    local preferred_port=$1
    local attempts=0
    local max_attempts=50
    
    # Prima prova la porta preferita
    if is_port_available $preferred_port; then
        echo $preferred_port
        return 0
    fi
    
    # Se non è disponibile, cerca nel range
    while [ $attempts -lt $max_attempts ]; do
        local port=$((PORT_RANGE_START + RANDOM % MAX_WORKERS))
        
        if is_port_available $port; then
            echo $port
            return 0
        fi
        
        attempts=$((attempts + 1))
        sleep 0.1
    done
    
    # Fallback: usa la porta preferita comunque
    echo $preferred_port
    return 1
}

# Main script execution
main() {
    echo "=== Dynamic Port Assignment for CQKD Worker ==="
    
    # Ottieni l'hostname del container
    local hostname=${HOSTNAME:-$(hostname)}
    echo "Container hostname: $hostname"
    
    # Calcola la porta unica
    local calculated_port=$(calculate_unique_port "$hostname")
    echo "Calculated port: $calculated_port"
    
    # Verifica disponibilità e trova porta alternativa se necessario
    local final_port=$(find_available_port $calculated_port)
    echo "Final assigned port: $final_port"
    
    # Esporta la variabile d'ambiente per il worker
    export DHT_PORT=$final_port
    
    # Log della configurazione
    echo "=== Worker Configuration ==="
    echo "Hostname: $hostname"
    echo "DHT Port: $DHT_PORT"
    echo "Bootstrap Nodes: ${BOOTSTRAP_NODES:-not set}"
    echo "================================"
    
    # Esegui il worker node con la porta assegnata
    exec python -m scripts.worker_node
}

# Esegui il main
main "$@"