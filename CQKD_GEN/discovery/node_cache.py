import asyncio
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
import threading

from core.node_states import NodeInfo, NodeState, NodeRole
from utils.logging_config import get_logger


logger = get_logger(__name__)


@dataclass
class CachedNode:
    """Nodo con metadati di caching"""
    node_info: NodeInfo
    cached_at: datetime
    last_verified: datetime
    hit_count: int = 0  # Quante volte usato
    miss_count: int = 0  # Quante volte non disponibile
    availability_score: float = 1.0  # 0.0 - 1.0
    
    def is_expired(self, ttl: timedelta) -> bool:
        """Verifica se il nodo è scaduto nella cache"""
        return datetime.now() - self.cached_at > ttl
    
    def needs_refresh(self, refresh_interval: timedelta) -> bool:
        """Verifica se il nodo necessita refresh"""
        return datetime.now() - self.last_verified > refresh_interval
    
    def update_availability_score(self):
        """Aggiorna score di disponibilità basato su hit/miss"""
        total = self.hit_count + self.miss_count
        if total > 0:
            self.availability_score = self.hit_count / total


class NodeCache:
    """
    Cache LRU per nodi DHT con TTL e refresh automatico
    
    Caratteristiche:
    - TTL configurabile per eviction automatica
    - Refresh periodico per verificare disponibilità
    - Score di affidabilità per prioritizzazione
    - Thread-safe per accessi concorrenti
    """
    
    # Configurazione cache
    DEFAULT_TTL_SECONDS = 600  # 10 minuti (come IPFS)
    DEFAULT_REFRESH_INTERVAL = 300  # 5 minuti (metà TTL)
    DEFAULT_MAX_SIZE = 10000  # Massimo nodi in cache
    
    def __init__(
        self,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        refresh_interval_seconds: int = DEFAULT_REFRESH_INTERVAL,
        max_size: int = DEFAULT_MAX_SIZE
    ):
        self.ttl = timedelta(seconds=ttl_seconds)
        self.refresh_interval = timedelta(seconds=refresh_interval_seconds)
        self.max_size = max_size
        
        # Cache principale: node_id -> CachedNode
        self._cache: Dict[str, CachedNode] = {}
        
        # Indici per query veloci
        self._by_capability: Dict[NodeRole, Set[str]] = defaultdict(set)
        self._by_state: Dict[NodeState, Set[str]] = defaultdict(set)
        
        # Lock per thread-safety
        self._lock = threading.RLock()
        
        # Statistiche
        self.stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "refreshes": 0
        }
        
        logger.info(
            "node_cache_initialized",
            ttl_seconds=ttl_seconds,
            refresh_interval=refresh_interval_seconds,
            max_size=max_size
        )
    
    def add(self, node_info: NodeInfo) -> bool:
        """
        Aggiungi nodo alla cache
        
        Args:
            node_info: Informazioni del nodo
            
        Returns:
            bool: True se aggiunto, False se cache piena
        """
        with self._lock:
            # Evict se cache piena
            if len(self._cache) >= self.max_size:
                if not self._evict_lru():
                    logger.warning("cache_full_eviction_failed")
                    return False
            
            now = datetime.now()
            cached_node = CachedNode(
                node_info=node_info,
                cached_at=now,
                last_verified=now
            )
            
            # Aggiungi alla cache
            self._cache[node_info.node_id] = cached_node
            
            # Aggiorna indici
            for capability in node_info.capabilities:
                self._by_capability[capability].add(node_info.node_id)
            self._by_state[node_info.state].add(node_info.node_id)
            
            logger.debug(
                "node_cached",
                node_id=node_info.node_id[:8],
                total_cached=len(self._cache)
            )
            
            return True
    
    def get(self, node_id: str) -> Optional[NodeInfo]:
        """
        Recupera nodo dalla cache
        
        Args:
            node_id: ID del nodo
            
        Returns:
            NodeInfo se trovato e valido, None altrimenti
        """
        with self._lock:
            cached = self._cache.get(node_id)
            
            if cached is None:
                self.stats["misses"] += 1
                return None
            
            # Verifica TTL
            if cached.is_expired(self.ttl):
                logger.debug("node_cache_expired", node_id=node_id[:8])
                self._remove(node_id)
                self.stats["evictions"] += 1
                return None
            
            # Cache hit
            cached.hit_count += 1
            self.stats["hits"] += 1
            
            return cached.node_info
    
    def get_by_capabilities(
        self,
        required_capabilities: List[NodeRole],
        count: int,
        min_availability_score: float = 0.7
    ) -> List[NodeInfo]:
        """
        Recupera nodi con capacità specifiche
        
        Args:
            required_capabilities: Capacità richieste
            count: Numero di nodi desiderati
            min_availability_score: Score minimo di affidabilità
            
        Returns:
            List[NodeInfo]: Nodi che soddisfano i criteri
        """
        with self._lock:
            # Trova nodi con tutte le capacità richieste
            candidate_ids = None
            
            for capability in required_capabilities:
                capability_nodes = self._by_capability.get(capability, set())
                if candidate_ids is None:
                    candidate_ids = capability_nodes.copy()
                else:
                    candidate_ids &= capability_nodes
            
            if not candidate_ids:
                return []
            
            # Filtra per availability score e stato
            valid_nodes = []
            for node_id in candidate_ids:
                cached = self._cache.get(node_id)
                if cached and not cached.is_expired(self.ttl):
                    if (cached.availability_score >= min_availability_score and
                        cached.node_info.state == NodeState.ACTIVE):
                        valid_nodes.append((cached.availability_score, cached.node_info))
            
            # Ordina per availability score (decrescente)
            valid_nodes.sort(key=lambda x: x[0], reverse=True)
            
            return [node for _, node in valid_nodes[:count]]
    
    def get_all_active(self) -> List[NodeInfo]:
        """
        Recupera tutti i nodi attivi non scaduti
        
        Returns:
            List[NodeInfo]: Nodi attivi
        """
        with self._lock:
            active_nodes = []
            
            for node_id in list(self._cache.keys()):
                cached = self._cache.get(node_id)
                if cached and not cached.is_expired(self.ttl):
                    if cached.node_info.state == NodeState.ACTIVE:
                        active_nodes.append(cached.node_info)
            
            return active_nodes
    
    def mark_unavailable(self, node_id: str):
        """Marca un nodo come non disponibile (per aggiornare score)"""
        with self._lock:
            cached = self._cache.get(node_id)
            if cached:
                cached.miss_count += 1
                cached.update_availability_score()
                
                logger.debug(
                    "node_marked_unavailable",
                    node_id=node_id[:8],
                    score=cached.availability_score
                )
    
    def get_nodes_needing_refresh(self) -> List[NodeInfo]:
        """
        Ottieni nodi che necessitano refresh
        
        Returns:
            List[NodeInfo]: Nodi da verificare
        """
        with self._lock:
            to_refresh = []
            
            for cached in self._cache.values():
                if cached.needs_refresh(self.refresh_interval):
                    to_refresh.append(cached.node_info)
            
            return to_refresh
    
    def update_verification(self, node_id: str, is_available: bool):
        """
        Aggiorna timestamp di verifica dopo ping/check
        
        Args:
            node_id: ID del nodo
            is_available: Se il nodo è risultato disponibile
        """
        with self._lock:
            cached = self._cache.get(node_id)
            if cached:
                cached.last_verified = datetime.now()
                
                if is_available:
                    cached.hit_count += 1
                else:
                    cached.miss_count += 1
                
                cached.update_availability_score()
                self.stats["refreshes"] += 1
    
    def _remove(self, node_id: str):
        """Rimuovi nodo dalla cache (interno)"""
        cached = self._cache.pop(node_id, None)
        if cached:
            # Rimuovi dagli indici
            for capability in cached.node_info.capabilities:
                self._by_capability[capability].discard(node_id)
            self._by_state[cached.node_info.state].discard(node_id)
    
    def _evict_lru(self) -> bool:
        """
        Evict del nodo Least Recently Used con score più basso
        
        Returns:
            bool: True se eviction riuscita
        """
        if not self._cache:
            return False
        
        # Trova nodo con score più basso e meno usato
        min_score = float('inf')
        lru_node_id = None
        
        for node_id, cached in self._cache.items():
            score = cached.availability_score * (cached.hit_count + 1)
            if score < min_score:
                min_score = score
                lru_node_id = node_id
        
        if lru_node_id:
            logger.debug(
                "node_evicted_lru",
                node_id=lru_node_id[:8],
                score=min_score
            )
            self._remove(lru_node_id)
            self.stats["evictions"] += 1
            return True
        
        return False
    
    def cleanup_expired(self) -> int:
        """
        Pulisci nodi scaduti dalla cache
        
        Returns:
            int: Numero di nodi rimossi
        """
        with self._lock:
            expired_ids = []
            
            for node_id, cached in self._cache.items():
                if cached.is_expired(self.ttl):
                    expired_ids.append(node_id)
            
            for node_id in expired_ids:
                self._remove(node_id)
            
            if expired_ids:
                logger.info(
                    "cache_cleanup",
                    expired_count=len(expired_ids),
                    remaining=len(self._cache)
                )
            
            return len(expired_ids)
    
    def get_stats(self) -> Dict:
        """Ottieni statistiche cache"""
        with self._lock:
            hit_rate = 0.0
            total = self.stats["hits"] + self.stats["misses"]
            if total > 0:
                hit_rate = self.stats["hits"] / total
            
            return {
                **self.stats,
                "cache_size": len(self._cache),
                "hit_rate": hit_rate,
                "max_size": self.max_size
            }
