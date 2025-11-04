# Analisi dei Problemi di Scalabilità della Rete DHT CQKD

## Problemi Identificati

### 1. **Porte Statiche (Bloccante)**
- **Problema**: Tutti i worker usano `DHT_PORT=7000` fisso in docker-compose.yml
- **Impatto**: Conflitti di porta quando si scalano a 50+ worker
- **Evidenza**: Linea 55 in docker-compose.yml: `- DHT_PORT=7000`
- **Soluzione Richiesta**: Sistema di porte dinamiche nel range 7000-8000

### 2. **Bootstrap Bottleneck (Critico)**
- **Problema**: Solo 2 bootstrap nodes per tutti i worker
- **Impatto**: Collasso del sistema con 50+ worker contemporanei
- **Evidenza**: bootstrap-primary (porta 5678) e bootstrap-secondary (porta 5679)
- **Soluzione Richiesta**: Architettura bootstrap multi-livello

### 3. **Timeout Insufficienti (Performance)**
- **Problema**: `QUERY_TIMEOUT=5.0` secondi troppo basso per reti grandi
- **Impatto**: Timeout frequenti con 50+ worker
- **Evidenza**: Linea 37 in discovery/node_discovery.py
- **Soluzione Richiesta**: Timeout adattivi basati sulla dimensione della rete

### 4. **Parametri Kademlia Conservativi (Limitante)**
- **Problema**: `ALPHA=3`, `K=20` inadeguati per scaling
- **Impatto**: Scoperta lenta e inefficiente in reti grandi
- **Evidenza**: Linee 33-34 in discovery/node_discovery.py
- **Soluzione Richiesta**: Parametri adattivi per reti 1000+ nodi

### 5. **Health Check Disabilitato (Affidabilità)**
- **Problema**: Ping commentato in discovery_strategies.py riga 332
- **Impatto**: Nodi non verificati, fallback a nodi non raggiungibili
- **Evidenza**: `# is_available = await self._ping_node(node)`
- **Soluzione Richiesta**: Health check ottimizzato e abilitato

### 6. **Refresh Rate Troppo Lento (Stabilità)**
- **Problema**: 300 secondi per routing table refresh
- **Impatto**: Routing table obsoleta in reti dinamiche
- **Evidenza**: Linea 315 in discovery/discovery_strategies.py
- **Soluzione Richiesta**: Refresh rate adattivo

## Architettura Attuale

### Componenti Principali
1. **Bootstrap Nodes**: 2 nodi fissi (porte 5678, 5679)
2. **Worker Nodes**: N numero di worker con porta fissa 7000
3. **Alice/Bob**: Nodi specializzati con porte fisse (6000, 6001)
4. **Discovery Service**: NodeDiscoveryService con parametri conservativi
5. **Smart Discovery**: SmartDiscoveryStrategy con cache e random walk

### Flusso Attuale
```
Bootstrap Nodes (2) → Worker Nodes (N) → Alice/Bob
        ↓
    Discovery Service → Smart Discovery → Cache
```

## Limitazioni di Scalabilità

### 1. **Collasso a 50+ Worker**
- Conflitti porta 7000
- Bootstrap nodes sovraccarichi
- Timeout frequenti
- Routing table non popolata

### 2. **Inefficienza con 1000+ Nodi**
- Parametri Kademlia non ottimali
- Health check disabilitato
- Refresh troppo lento
- Discovery lento

### 3. **Problemi di Affidabilità**
- Nodi morti non rimossi
- Cache non aggiornata
- Fallback a nodi non raggiungibili

## Requisiti di Scalabilità

### Target: 1000+ Worker
- **Porte**: Range 7000-8000 (1000 porte disponibili)
- **Bootstrap**: Multi-livello gerarchico
- **Timeout**: Adattivi basati su dimensione rete
- **Parametri**: ALPHA=6, K=40 per reti grandi
- **Health Check**: Abilitato e ottimizzato
- **Refresh**: Rate adattivo 30-300 secondi

### Compatibilità
- Mantenere compatibilità con test esistenti
- Implementazione incrementale
- Fallback a configurazione attuale

## Metriche di Successo

### Performance
- Bootstrap time < 60 secondi per 1000 nodi
- Discovery time < 30 secondi per 100 nodi
- Success rate > 95% per operazioni DHT

### Affidabilità
- Health check < 2 secondi per nodo
- Refresh routing table < 10 secondi
- Recovery da fallimenti < 30 secondi

### Scalabilità
- Supporto 1000+ worker senza conflitti
- Bootstrap nodes multi-livello
- Parametri adattivi automatici