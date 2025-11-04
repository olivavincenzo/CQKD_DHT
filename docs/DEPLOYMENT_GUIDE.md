# Guida Completa di Deployment - CQKD DHT

Questa guida fornisce istruzioni complete per buildare e deployare il sistema CQKD DHT a diverse scale (15, 50, 100+ nodi).

## 📋 Indice

1. [Prerequisiti](#prerequisiti)
2. [Build dell'immagine Docker](#build-dellimmagine-docker)
3. [Deployment 15 nodi (Small Scale)](#deployment-15-nodi-small-scale)
4. [Deployment 50 nodi (Medium Scale)](#deployment-50-nodi-medium-scale)
5. [Deployment 100 nodi (Large Scale)](#deployment-100-nodi-large-scale)
6. [Configurazione Parametri](#configurazione-parametri)
7. [Bootstrap Nodes](#bootstrap-nodes)
8. [Verifica Funzionamento](#verifica-funzionamento)
9. [Troubleshooting](#troubleshooting)
10. [Script Disponibili](#script-disponibili)

---

## 🔧 Prerequisiti

### Software Richiesto

- **Docker** (versione 20.10 o superiore)
- **Docker Compose** (versione 2.0 o superiore)
- **Python 3.11+** (per test locali)
- **Git** (per clonare il repository)

### Installazione Docker

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Installazione Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### Verifica Installazione

```bash
docker --version
docker-compose version
```

### Clonazione Repository

```bash
git clone <repository-url>
cd CQKD_DHT
```

---

## 🏗️ Build dell'Immagine Docker

Il sistema utilizza un multi-stage build per ottimizzare le dimensioni dell'immagine.

### Comando di Build

```bash
# Build dell'immagine base
docker build -t cqkd-dht-node:latest .

# Verifica immagine creata
docker images | grep cqkd-dht-node
```

### Struttura Dockerfile

- **Stage 1 (builder)**: Installa le dipendenze Python
- **Stage 2 (finale)**: Copia solo il necessario, crea utente non-root

### Dipendenze Python

Le dipendenze sono definite in `requirements.txt`:
```
aiohttp
asyncio
pydantic
fastapi
uvicorn
matplotlib
seaborn
pandas
```

---

## 📊 Deployment 15 Nodi (Small Scale)

### Configurazione Automatica

```bash
# Deployment small scale (15 worker + 2 bootstrap)
./scripts/deploy_scale.sh -s small -c -v -m
```

### Configurazione Manuale

```bash
# 1. Pulisci container esistenti
docker-compose down --remove-orphans

# 2. Avvia bootstrap nodes
docker-compose up -d bootstrap-primary bootstrap-secondary

# 3. Attendi 10 secondi
sleep 10

# 4. Avvia alice e bob
docker-compose up -d alice bob

# 5. Attendi 5 secondi
sleep 5

# 6. Avvia 15 worker
docker-compose up -d --scale worker=15
```

### File di Override (docker-compose.override.yml)

```yaml
version: '3.8'

services:
  worker:
    environment:
      - WORKER_COUNT=15
      - BOOTSTRAP_SCALE_STRATEGY=small
    deploy:
      replicas: 15
      resources:
        limits:
          memory: 128M
        reservations:
          memory: 64M

  # Disabilita bootstrap nodes non necessari
  bootstrap-tertiary:
    profiles: []
  bootstrap-quaternary:
    profiles: []
  bootstrap-quinary:
    profiles: []
  bootstrap-senary:
    profiles: []
```

### Parametri Configurati

- **Bootstrap Nodes**: 2 (primary, secondary)
- **Worker**: 15
- **ALPHA**: 3 (parallelismo query)
- **K**: 20 (bucket size)
- **Query Timeout**: 5.0 secondi
- **Discovery Timeout**: 60 secondi

---

## 📈 Deployment 50 Nodi (Medium Scale)

### Configurazione Automatica

```bash
# Deployment medium scale (30 worker + 3 bootstrap)
./scripts/deploy_scale.sh -s medium -c -v -m
```

### Configurazione Manuale

```bash
# 1. Pulisci container esistenti
docker-compose down --remove-orphans

# 2. Avvia bootstrap nodes
docker-compose up -d bootstrap-primary bootstrap-secondary bootstrap-tertiary

# 3. Attendi 10 secondi
sleep 10

# 4. Avvia alice e bob
docker-compose up -d alice bob

# 5. Attendi 5 secondi
sleep 5

# 6. Avvia 50 worker
docker-compose up -d --scale worker=50
```

### File di Override (docker-compose.override.yml)

```yaml
version: '3.8'

services:
  worker:
    environment:
      - WORKER_COUNT=50
      - BOOTSTRAP_SCALE_STRATEGY=medium
    deploy:
      replicas: 50
      resources:
        limits:
          memory: 128M
        reservations:
          memory: 64M

  # Disabilita bootstrap nodes non necessari
  bootstrap-quaternary:
    profiles: []
  bootstrap-quinary:
    profiles: []
  bootstrap-senary:
    profiles: []
```

### Parametri Configurati

- **Bootstrap Nodes**: 3 (primary, secondary, tertiary)
- **Worker**: 50
- **ALPHA**: 4 (parallelismo query)
- **K**: 26 (bucket size)
- **Query Timeout**: 8.0 secondi
- **Discovery Timeout**: 90 secondi

---

## 🚀 Deployment 100 Nodi (Large Scale)

### Configurazione Automatica

```bash
# Deployment large scale (100 worker + 4 bootstrap)
./scripts/deploy_scale.sh -s large -c -v -m
```

### Configurazione Manuale

```bash
# 1. Pulisci container esistenti
docker-compose down --remove-orphans

# 2. Avvia bootstrap nodes
docker-compose up -d bootstrap-primary bootstrap-secondary bootstrap-tertiary bootstrap-quaternary

# 3. Attendi 15 secondi
sleep 15

# 4. Avvia alice e bob
docker-compose up -d alice bob

# 5. Attendi 5 secondi
sleep 5

# 6. Avvia 100 worker
docker-compose up -d --scale worker=100
```

### File di Override (docker-compose.override.yml)

```yaml
version: '3.8'

services:
  worker:
    environment:
      - WORKER_COUNT=100
      - BOOTSTRAP_SCALE_STRATEGY=large
    deploy:
      replicas: 100
      resources:
        limits:
          memory: 128M
        reservations:
          memory: 64M

  # Disabilita bootstrap nodes non necessari
  bootstrap-quinary:
    profiles: []
  bootstrap-senary:
    profiles: []
```

### Parametri Configurati

- **Bootstrap Nodes**: 4 (primary, secondary, tertiary, quaternary)
- **Worker**: 100
- **ALPHA**: 6 (parallelismo query)
- **K**: 30 (bucket size)
- **Query Timeout**: 12.0 secondi
- **Discovery Timeout**: 120 secondi

---

## ⚙️ Configurazione Parametri

### Variabili d'Ambiente Principali

| Variabile | Descrizione | Default | Small | Medium | Large |
|-----------|-------------|---------|-------|--------|-------|
| `WORKER_COUNT` | Numero di worker | 15 | 15 | 50 | 100 |
| `BOOTSTRAP_NODES` | Lista bootstrap nodes | Tutti | 2 | 3 | 4 |
| `ALPHA` | Parallelismo query | 3 | 3 | 4 | 6 |
| `K` | Bucket size | 20 | 20 | 26 | 30 |
| `QUERY_TIMEOUT` | Timeout query (s) | 5.0 | 5.0 | 8.0 | 12.0 |
| `ENABLE_ADAPTIVE_KADEMLIA` | Parametri adattivi | true | true | true | true |

### File di Configurazione (config.py)

I parametri possono essere modificati nel file `config.py`:

```python
# Parametri base per reti piccole
base_alpha: int = 3
base_k: int = 20
base_query_timeout: float = 5.0

# Fattori di scaling
alpha_scaling_factor: float = 1.5
k_scaling_factor: float = 1.3
timeout_scaling_factor: float = 1.6

# Limiti massimi
max_alpha: int = 8
max_k: int = 40
max_query_timeout: float = 20.0
```

### Configurazione Adattiva

Il sistema calcola automaticamente i parametri ottimali basandosi sulla dimensione della rete:

```python
# Esempio: calcolo parametri per 75 nodi
params = settings.calculate_adaptive_kademlia_params(75)
# Risultato: {'alpha': 6, 'k': 30, 'query_timeout': 12.0, ...}
```

---

## 🌐 Bootstrap Nodes

### Architettura Bootstrap

Il sistema supporta fino a 6 bootstrap nodes:

| Node | Porta | Descrizione |
|------|-------|-------------|
| bootstrap-primary | 5678 | Bootstrap primario |
| bootstrap-secondary | 5679 | Bootstrap secondario |
| bootstrap-tertiary | 5680 | Bootstrap terziario |
| bootstrap-quaternary | 5681 | Bootstrap quaternario |
| bootstrap-quinary | 5682 | Bootstrap quinario |
| bootstrap-senary | 5683 | Bootstrap senario |

### Configurazione Bootstrap per Scala

```bash
# Small scale (≤15 worker): 2 bootstrap
BOOTSTRAP_NODES=bootstrap-primary:5678,bootstrap-secondary:5679

# Medium scale (16-50 worker): 3 bootstrap
BOOTSTRAP_NODES=bootstrap-primary:5678,bootstrap-secondary:5679,bootstrap-tertiary:5680

# Large scale (51-200 worker): 4 bootstrap
BOOTSTRAP_NODES=bootstrap-primary:5678,bootstrap-secondary:5679,bootstrap-tertiary:5680,bootstrap-quaternary:5681

# X-Large scale (>200 worker): 6 bootstrap
BOOTSTRAP_NODES=bootstrap-primary:5678,bootstrap-secondary:5679,bootstrap-tertiary:5680,bootstrap-quaternary:5681,bootstrap-quinary:5682,bootstrap-senary:5683
```

### Load Balancing Bootstrap

Il sistema supporta diverse strategie di load balancing:

- **round_robin**: Distribuzione circolare
- **least_loaded**: Sceglie il nodo con meno connessioni
- **priority**: Priorità ai nodi specifici
- **random**: Selezione casuale

```python
# Configurazione in config.py
bootstrap_selection_strategy: str = "round_robin"
enable_bootstrap_load_balancing: bool = True
bootstrap_max_connections_per_node: int = 50
```

---

## ✅ Verifica Funzionamento

### Comandi di Verifica

```bash
# 1. Verifica stato container
docker-compose ps

# 2. Verifica log worker
docker-compose logs -f worker

# 3. Verifica log bootstrap
docker-compose logs -f bootstrap-primary

# 4. Verifica utilizzo risorse
docker stats

# 5. Test API Alice
curl http://localhost:8001/docs

# 6. Test API Bob
curl http://localhost:8002/docs
```

### Test di Integrazione

```bash
# Test porte dinamiche
python test_dynamic_ports.py

# Test parametri adattivi
python test_adaptive_kademlia.py

# Test health check
python test_health_check_system.py
```

### Verifica Scaling

```bash
# Verifica numero worker attivi
docker ps --filter "name=worker" --format "{{.Names}}" | wc -l

# Verifica porte uniche
docker ps --filter "name=worker" --format "{{.Ports}}" | grep -o ":[0-9]*->" | grep -o "[0-9]*" | sort -u | wc -l

# Verifica bootstrap nodes attivi
docker ps --filter "name=bootstrap" --format "{{.Names}}"
```

### Metriche di Performance

```bash
# Monitoraggio CPU e memoria
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"

# Log dei parametri adattivi
docker-compose logs worker | grep "adaptive_params"

# Log health check
docker-compose logs worker | grep "health_check"
```

---

## 🔧 Troubleshooting

### Problemi Comuni

#### 1. Conflitti di Porte

**Sintomo**: Errori di binding sulle porte

**Soluzione**:
```bash
# Verifica porte in uso
netstat -tulpn | grep :7000

# Pulisci container
docker-compose down --remove-orphans

# Riavvia con pulizia
./scripts/deploy_scale.sh -s small -c
```

#### 2. Worker Non Si Connettono

**Sintomo**: Worker non appaiono nella rete DHT

**Soluzione**:
```bash
# Verifica bootstrap nodes
docker-compose logs bootstrap-primary

# Verifica log worker
docker-compose logs worker | grep "bootstrap"

# Riavvia bootstrap nodes
docker-compose restart bootstrap-primary bootstrap-secondary
```

#### 3. Memory Exhaustion

**Sintomo**: Container terminati per memoria insufficiente

**Soluzione**:
```bash
# Aumenta limiti memoria
# Modifica docker-compose.override.yml
services:
  worker:
    deploy:
      resources:
        limits:
          memory: 256M  # Aumenta da 128M
```

#### 4. Timeout Query

**Sintomo**: Query DHT lente o fallite

**Soluzione**:
```bash
# Aumenta timeout query
# Modifica config.py
base_query_timeout: float = 10.0  # Aumenta da 5.0

# Oppure usa parametri adattivi
ENABLE_ADAPTIVE_KADEMLIA=true
```

#### 5. Bootstrap Nodes Non Rispondono

**Sintomo**: Worker non riescono a contattare bootstrap

**Soluzione**:
```bash
# Verifica rete Docker
docker network ls
docker network inspect cqkd_dht_cqkd-network

# Riavvia rete
docker-compose down
docker network prune -f
docker-compose up -d
```

### Debug Avanzato

#### Log Dettagliati

```bash
# Abilita log dettagliati
export LOG_LEVEL=DEBUG

# Log con timestamp
docker-compose logs --timestamps worker

# Log ultimi 100 righe
docker-compose logs --tail=100 worker
```

#### Ispezione Container

```bash
# Entra in container worker
docker exec -it <container-id> bash

# Verifica processi
ps aux

# Verifica connessioni di rete
netstat -tulpn

# Verifica porte DHT
ss -uln | grep 7000
```

#### Test di Connessione

```bash
# Test connessione bootstrap
nc -u localhost 5678

# Test API Alice
curl -X GET http://localhost:8001/health

# Test API Bob
curl -X GET http://localhost:8002/health
```

### Recovery da Disaster

```bash
# 1. Stop completo
docker-compose down --remove-orphans

# 2. Pulizia risorse Docker
docker system prune -f

# 3. Riavvio pulito
./scripts/deploy_scale.sh -s small -c -v
```

---

## 📜 Script Disponibili

### scripts/deploy_scale.sh

Script principale per deployment automatizzato.

**Uso**:
```bash
./scripts/deploy_scale.sh [OPZIONI]

Opzioni:
    -s, --scale SCALE           Scala del deployment (small|medium|large|xlarge|custom)
    -w, --workers COUNT         Numero di worker (solo con scale=custom)
    -c, --clean                 Rimuovi tutti i container prima del deployment
    -d, --dry-run               Simula il deployment senza eseguirlo
    -v, --verbose               Output dettagliato
    -m, --monitor               Avvia monitoring dopo il deployment
    -h, --help                  Mostra questo help
```

**Esempi**:
```bash
# Deployment small con 15 worker
./scripts/deploy_scale.sh -s small

# Deployment medium con pulizia e verbose
./scripts/deploy_scale.sh -s medium -c -v

# Deployment custom con 75 worker
./scripts/deploy_scale.sh -s custom -w 75

# Simulazione deployment
./scripts/deploy_scale.sh -s large --dry-run
```

### scripts/entrypoint_worker.sh

Script per assegnazione dinamica delle porte ai worker.

**Funzionalità**:
- Calcola porte uniche per ogni worker (range 7000-8000)
- Verifica disponibilità porte
- Gestisce conflitti automaticamente
- Log dettagliati di assegnazione

**Log tipico**:
```
=== Dynamic Port Assignment for CQKD Worker ===
Container hostname: worker_1
Calculated port: 7000
Final assigned port: 7000
=== Worker Configuration ===
Hostname: worker_1
DHT Port: 7000
Bootstrap Nodes: bootstrap-primary:5678,bootstrap-secondary:5679
================================
```

### scripts/run_scaling_tests.sh

Script per test di scaling completi.

**Uso**:
```bash
./scripts/run_scaling_tests.sh [OPZIONI]

Opzioni:
    -h, --help              Mostra questo help
    -q, --quick             Esegue solo test rapidi (small, medium)
    -f, --full              Esegue test completi (default)
    -c, --cleanup-only      Solo pulizia ambiente
    -s, --skip-build        Salta build Docker
    -v, --verbose           Output dettagliato
    -r, --report-only       Genera report solo se esistono dati
    --dry-run               Simula esecuzione senza modifiche
```

**Test eseguiti**:
- Test scaling progressivo (15 → 50 → 100 → 200 → 500)
- Test porte dinamiche
- Test integrazione CQKD
- Test health check
- Raccolta metriche performance

### test_dynamic_ports.py

Script Python per test del sistema di porte dinamiche.

**Uso**:
```bash
python test_dynamic_ports.py
```

**Test verificati**:
- Unicità porte worker
- Range porte corretto (7000-8000)
- Log assegnazione porte
- Scaling progressivo

### test_adaptive_kademlia.py

Script Python per test dei parametri adattivi Kademlia.

**Uso**:
```bash
python test_adaptive_kademlia.py
```

**Test verificati**:
- Calcolo parametri adattivi
- Compatibilità configurazione
- Logging monitoraggio
- Timeout discovery adattivi

---

## 📊 Metriche e Monitoraggio

### Metriche Chiave

| Metrica | Descrizione | Small | Medium | Large |
|---------|-------------|-------|--------|-------|
| Worker/Bootstrap Ratio | Worker per bootstrap node | 7.5:1 | 16.7:1 | 25:1 |
| Memory per Worker | Memoria utilizzata per worker | 64MB | 64MB | 64MB |
| CPU per Worker | CPU utilizzata per worker | ~1% | ~1% | ~1% |
| Discovery Time | Tempo discovery rete | 60s | 90s | 120s |
| Query Success Rate | Success rate query DHT | >95% | >90% | >85% |

### Monitoring Tools

```bash
# Docker stats in tempo reale
watch -n 2 'docker stats --no-stream'

# Log con filtering
docker-compose logs -f worker | grep -E "(bootstrap|discovery|adaptive)"

# Container health status
docker ps --format "table {{.Names}}\t{{.Status}}"
```

### Prometheus Integration (Opzionale)

```python
# Abilita in config.py
enable_prometheus: bool = true
prometheus_port: int = 9090

# Access metrics
curl http://localhost:9090/metrics
```

---

## 🚀 Best Practices

### 1. Planning del Deployment

- Inizia sempre con small scale per test
- Verifica risorse disponibili prima di large scale
- Monitora continuamente durante deployment

### 2. Gestione Risorse

- Limita memoria per container
- Usa resource reservation per stabilità
- Monitora CPU e memoria continuamente

### 3. Networking

- Verifica configurazione rete Docker
- Usa porte dinamiche per evitare conflitti
- Configura firewall appropriatamente

### 4. Logging e Debugging

- Abilita log dettagliati per troubleshooting
- Usa log centralizzati per production
- Implementa alerting per errori critici

### 5. Scaling Strategy

- Usa parametri adattivi per ottimizzazione
- Monitora ratio worker/bootstrap
- Aumenta bootstrap nodes se necessario

---

## 📞 Supporto

Per problemi o domande:

1. Controlla i log dei container
2. Verifica la configurazione in config.py
3. Esegui gli script di test disponibili
4. Consulta il troubleshooting guide

---

*Questa guida è mantenuta aggiornata con le ultime versioni del sistema CQKD DHT. Per contributi o segnalazioni, consultare il repository del progetto.*