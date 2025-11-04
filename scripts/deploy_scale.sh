#!/bin/bash

# Deployment Script per CQKD DHT con Bootstrap Scaling
# Supporta diversi scenari di scaling: small, medium, large, xlarge, custom

set -e

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configurazione default
SCALE="small"
WORKER_COUNT=15
CUSTOM_WORKERS=0
DRY_RUN=false
VERBOSE=false
CLEAN=false
MONITOR=false

# Funzioni di utilità
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

show_usage() {
    cat << EOF
Uso: $0 [OPZIONI]

Opzioni:
    -s, --scale SCALE           Scala del deployment (small|medium|large|xlarge|custom)
    -w, --workers COUNT         Numero di worker (solo con scale=custom)
    -c, --clean                 Rimuovi tutti i container prima del deployment
    -d, --dry-run               Simula il deployment senza eseguirlo
    -v, --verbose               Output dettagliato
    -m, --monitor               Avvia monitoring dopo il deployment
    -h, --help                  Mostra questo help

Scale predefinite:
    small    (≤15 worker)   - 2 bootstrap nodes
    medium   (16-50 worker)  - 3 bootstrap nodes  
    large    (51-200 worker) - 4 bootstrap nodes
    xlarge   (>200 worker)   - 6 bootstrap nodes

Esempi:
    $0 -s small                    # Deployment small con 15 worker
    $0 -s medium                    # Deployment medium con 30 worker
    $0 -s custom -w 100             # Deployment custom con 100 worker
    $0 -s large -c -v               # Deployment large con clean e verbose
    $0 -s xlarge -m                 # Deployment xlarge con monitoring

EOF
}

# Funzione per validare la scala
validate_scale() {
    local scale=$1
    case $scale in
        small|medium|large|xlarge|custom)
            return 0
            ;;
        *)
            log_error "Scala non valida: $scale"
            log_info "Scale valide: small, medium, large, xlarge, custom"
            exit 1
            ;;
    esac
}

# Funzione per calcolare il numero ottimale di worker
calculate_worker_count() {
    local scale=$1
    
    case $scale in
        small)
            echo 15
            ;;
        medium)
            echo 30
            ;;
        large)
            echo 100
            ;;
        xlarge)
            echo 500
            ;;
        custom)
            echo $CUSTOM_WORKERS
            ;;
    esac
}

# Funzione per determinare la configurazione bootstrap
get_bootstrap_config() {
    local worker_count=$1
    local scale=$2
    
    if [ "$scale" = "custom" ]; then
        if [ $worker_count -le 15 ]; then
            echo "small"
        elif [ $worker_count -le 50 ]; then
            echo "medium"
        elif [ $worker_count -le 200 ]; then
            echo "large"
        else
            echo "xlarge"
        fi
    else
        echo $scale
    fi
}

# Funzione per calcolare il ratio worker/bootstrap
calculate_bootstrap_ratio() {
    local worker_count=$1
    local bootstrap_scale=$2
    
    case $bootstrap_scale in
        small)
            echo "scale=2; ratio=$(echo "scale=2; $worker_count / 2" | bc)"
            ;;
        medium)
            echo "scale=2; ratio=$(echo "scale=2; $worker_count / 3" | bc)"
            ;;
        large)
            echo "scale=2; ratio=$(echo "scale=2; $worker_count / 4" | bc)"
            ;;
        xlarge)
            echo "scale=2; ratio=$(echo "scale=2; $worker_count / 6" | bc)"
            ;;
    esac
}

# Funzione per determinare lo stato del ratio
get_ratio_status() {
    local ratio=$1
    
    if (( $(echo "$ratio <= 25" | bc -l) )); then
        echo "OK"
    elif (( $(echo "$ratio <= 50" | bc -l) )); then
        echo "WARNING"
    else
        echo "CRITICAL"
    fi
}

# Funzione per pulire i container esistenti
clean_containers() {
    log_info "Pulizia dei container esistenti..."
    
    if [ "$DRY_RUN" = false ]; then
        # Ferma e rimuovi tutti i container CQKD
        docker compose down --remove-orphans 2>/dev/null || true
        
        # Rimuovi container dangling
        docker container prune -f 2>/dev/null || true
        
        log_success "Pulizia completata"
    else
        log_info "[DRY-RUN] Verrebbe eseguito: docker compose down --remove-orphans"
    fi
}

# Funzione per generare il file docker compose.override.yml
generate_override_file() {
    local worker_count=$1
    local bootstrap_scale=$2
    
    local override_file="docker-compose.override.yml"
    
    log_info "Generazione file di override: $override_file"
    
    cat > "$override_file" << EOF
version: '3.8'

# Override file per deployment con $worker_count worker (scala: $bootstrap_scale)
# Generato automaticamente da deploy_scale.sh

services:
  worker:
    environment:
      - WORKER_COUNT=$worker_count
      - BOOTSTRAP_SCALE_STRATEGY=$bootstrap_scale
    deploy:
      replicas: $worker_count
      resources:
        limits:
          memory: 128M
        reservations:
          memory: 64M
EOF

    # Disabilita bootstrap nodes non necessari basandosi sulla scala
    case $bootstrap_scale in
        small)
            cat >> "$override_file" << EOF

  # Bootstrap nodes non necessari per scala small
  bootstrap-tertiary:
    profiles: []
  bootstrap-quaternary:
    profiles: []
  bootstrap-quinary:
    profiles: []
  bootstrap-senary:
    profiles: []
EOF
            ;;
        medium)
            cat >> "$override_file" << EOF

  # Bootstrap nodes non necessari per scala medium
  bootstrap-quaternary:
    profiles: []
  bootstrap-quinary:
    profiles: []
  bootstrap-senary:
    profiles: []
EOF
            ;;
        large)
            cat >> "$override_file" << EOF

  # Bootstrap nodes non necessari per scala large
  bootstrap-quinary:
    profiles: []
  bootstrap-senary:
    profiles: []
EOF
            ;;
    esac
    
    log_success "File $override_file generato"
}

# Funzione per mostrare il riepilogo del deployment
show_deployment_summary() {
    local worker_count=$1
    local bootstrap_scale=$2
    
    local ratio_info=$(calculate_bootstrap_ratio $worker_count $bootstrap_scale)
    local ratio=$(echo $ratio_info | cut -d';' -f2 | cut -d'=' -f2)
    local ratio_status=$(get_ratio_status $ratio)
    
    echo
    echo "=========================================="
    echo "    CQKD DHT DEPLOYMENT SUMMARY"
    echo "=========================================="
    echo "Scale:              $bootstrap_scale"
    echo "Worker Count:        $worker_count"
    echo "Bootstrap Strategy:  $bootstrap_scale"
    echo "Worker/Bootstrap:    $ratio:1"
    echo "Ratio Status:        $ratio_status"
    echo "=========================================="
    
    # Mostra warning se il ratio è problematico
    case $ratio_status in
        WARNING)
            log_warning "Ratio worker/bootstrap elevato. Considera scala superiore."
            ;;
        CRITICAL)
            log_error "Ratio worker/bootstrap critico! Il sistema potrebbe essere instabile."
            ;;
    esac
    
    echo
}

# Funzione per eseguire il deployment
deploy_system() {
    local worker_count=$1
    local bootstrap_scale=$2
    
    log_info "Inizio deployment CQKD DHT..."
    
    if [ "$DRY_RUN" = false ]; then
        # Avvia i bootstrap nodes prima
        log_info "Avvio bootstrap nodes..."
        docker compose up -d bootstrap-primary bootstrap-secondary
        
        # Avvia bootstrap nodes aggiuntivi basandosi sulla scala
        case $bootstrap_scale in
            medium|large|xlarge)
                docker compose up -d bootstrap-tertiary
                ;;
            large|xlarge)
                docker compose up -d bootstrap-quaternary
                ;;
            xlarge)
                docker compose up -d bootstrap-quinary bootstrap-senary
                ;;
        esac
        
        # Attendi che i bootstrap nodes siano pronti
        log_info "Attesa bootstrap nodes..."
        sleep 10
        
        # Avvia alice e bob
        log_info "Avvio alice e bob..."
        docker compose up -d alice bob
        
        # Attendi che alice e bob siano pronti
        sleep 5
        
        # Avvia i worker
        log_info "Avvio $worker_count worker..."
        docker compose up -d worker
        
        log_success "Deployment completato!"
    else
        log_info "[DRY-RUN] Verrebbe eseguito il deployment con:"
        log_info "[DRY-RUN] - $worker_count worker"
        log_info "[DRY-RUN] - Scala: $bootstrap_scale"
        log_info "[DRY-RUN] - Bootstrap nodes configurati per scala $bootstrap_scale"
    fi
}

# Funzione per monitoring
start_monitoring() {
    log_info "Avvio monitoring..."
    
    echo
    echo "Comandi utili per monitoring:"
    echo "  docker compose ps                    # Stato container"
    echo "  docker compose logs -f worker        # Log worker"
    echo "  docker compose logs -f bootstrap-primary  # Log bootstrap primary"
    echo "  docker stats                         # Utilizzo risorse"
    echo
    echo "Per testare il sistema:"
    echo "  curl http://localhost:8001/docs       # API Alice"
    echo "  curl http://localhost:8002/docs       # API Bob"
    echo
    
    if [ "$DRY_RUN" = false ]; then
        # Mostra stato attuale
        docker compose ps
    fi
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -s|--scale)
            SCALE="$2"
            shift 2
            ;;
        -w|--workers)
            CUSTOM_WORKERS="$2"
            shift 2
            ;;
        -c|--clean)
            CLEAN=true
            shift
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -m|--monitor)
            MONITOR=true
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            log_error "Opzione non valida: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Validazioni
validate_scale $SCALE

if [ "$SCALE" = "custom" ] && [ $CUSTOM_WORKERS -le 0 ]; then
    log_error "Con scale=custom è necessario specificare --workers COUNT"
    exit 1
fi

# Calcola numero worker e scala bootstrap
WORKER_COUNT=$(calculate_worker_count $SCALE)
BOOTSTRAP_SCALE=$(get_bootstrap_config $WORKER_COUNT $SCALE)

# Mostra riepilogo
show_deployment_summary $WORKER_COUNT $BOOTSTRAP_SCALE

# Pulizia se richiesto
if [ "$CLEAN" = true ]; then
    clean_containers
fi

# Genera file override
generate_override_file $WORKER_COUNT $BOOTSTRAP_SCALE

# Esegui deployment
deploy_system $WORKER_COUNT $BOOTSTRAP_SCALE

# Monitoring se richiesto
if [ "$MONITOR" = true ]; then
    start_monitoring
fi

log_success "Script completato!"