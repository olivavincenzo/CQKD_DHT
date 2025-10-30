
# Analisi del Processo di Setup in `test_complete_cqkd_protocol`

Questo documento analizza i passaggi iniziali (fino allo Step 3) della funzione `test_complete_cqkd_protocol` nel file `test.py`, spiegando come la rete DHT viene creata e come Alice e Bob si connettono.

## Step 1: Creazione della Rete DHT (`setup_dht_network`)

Il primo passo consiste nella creazione di una rete DHT (Distributed Hash Table) che servirà da infrastruttura di comunicazione per tutti i partecipanti.

1.  **Bootstrap Node**: Viene creato un singolo nodo, chiamato `bootstrap`, su una porta nota (5678). Questo nodo funge da **punto di ingresso** per tutti gli altri nodi che vorranno unirsi alla rete. È un `CQKDNode`, che è l'implementazione di un nodo Kademlia.

2.  **Worker Nodes**: Viene creato un numero specificato di nodi "lavoratori" (`workers`), in questo caso 100. Questi nodi costituiscono la spina dorsale della rete.
    *   Ogni worker viene avviato su una porta sequenziale (da 7000 in poi).
    *   Subito dopo l'avvio, ogni worker esegue il comando `worker.bootstrap([("127.0.0.1", 5678)])`. Questa è l'istruzione chiave: dice al nuovo nodo di contattare il `bootstrap` node per scoprire altri nodi già presenti nella rete.

3.  **Riempimento della Routing Table (Worker)**: Il processo di bootstrap di un nodo Kademlia (come `CQKDNode`) è il meccanismo con cui la sua tabella di routing viene popolata. Funziona così:
    *   Il nuovo nodo (il `worker`) invia una richiesta `FIND_NODE` al nodo di bootstrap.
    *   Il nodo di bootstrap risponde con un elenco di altri nodi che conosce (altri worker che si sono già connessi).
    *   Il nuovo nodo contatta questi nodi a sua volta per ottenere elenchi di altri nodi, e così via. Questo processo iterativo gli permette di riempire i suoi "bucket" di routing con informazioni di contatto per nodi sparsi in tutta la rete, garantendo una connettività decentralizzata.

Alla fine di questo step, abbiamo una rete DHT stabile e popolata da 100 worker nodes.

## Step 2: Connessione di Alice e Bob

Successivamente, i due protagonisti del protocollo, Alice e Bob, si uniscono alla rete.

1.  **Creazione dei Nodi**: Vengono create due istanze separate di `CQKDNode`, una per Alice (`alice_node`) e una per Bob (`bob_node`), su porte dedicate (6000 e 6001).

2.  **Bootstrap di Alice e Bob**: Esattamente come i worker, sia Alice che Bob usano lo stesso nodo di bootstrap per connettersi alla rete:
    *   `alice_node.bootstrap([("127.0.0.1", 5678)])`
    *   `bob_node.bootstrap([("127.0.0.1", 5678)])`

3.  **Riempimento della Routing Table (Alice e Bob)**: Eseguendo il bootstrap, Alice e Bob popolano le loro tabelle di routing con i nodi worker presenti nella DHT. Il test stampa esplicitamente le informazioni sulla tabella di routing di Alice, mostrando il numero di nodi totali che conosce e come sono distribuiti nei suoi bucket. Questo conferma che Alice è ora "consapevole" della rete e può usarla per trovare altri nodi.

In questo momento, Alice e Bob sono due nodi come gli altri all'interno della DHT. Non hanno ancora comunicato direttamente, ma entrambi conoscono la topologia della rete.

## Step 3: Inizializzazione del Protocollo

Questo step non riguarda più la rete DHT, ma la logica applicativa del protocollo CQKD.

1.  **Creazione degli Interpreti (`Alice` e `Bob`)**: Vengono create le istanze delle classi `Alice` e `Bob`.
    *   Queste classi **non sono nodi di rete**. Sono "interpreti" o "gestori del protocollo".
    *   Ognuna di esse riceve come argomento il rispettivo `CQKDNode` (`alice_node` per Alice, `bob_node` per Bob). Useranno questo nodo per tutte le comunicazioni sulla rete DHT.
    *   L'istanza di `Alice` riceve anche l'indirizzo di Bob (`bob_address`). Questo le indica chi è il destinatario finale della chiave che genererà. Bob, invece, si metterà in ascolto, in attesa di una comunicazione avviata da Alice.

## Riepilogo del Setup

| Ruolo             | Implementazione | Scopo                                                                                                                                 |
| ----------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| **Bootstrap Node**  | `CQKDNode`      | Punto di ingresso con indirizzo noto per consentire a tutti gli altri nodi di entrare nella rete DHT.                                   |
| **Worker Node**     | `CQKDNode`      | Forma la struttura della rete DHT. Vengono usati per instradare messaggi e come nodi intermedi nel protocollo di generazione della chiave. |
| **Alice/Bob Node**  | `CQKDNode`      | Nodi DHT dedicati ad Alice e Bob, che permettono loro di partecipare alla rete e comunicare.                                          |
| **Alice/Bob Class** | `Alice`/`Bob`   | Gestori della logica del protocollo CQKD. Usano i loro nodi (`CQKDNode`) per eseguire azioni sulla rete (es. trovare nodi, inviare dati). |

### Nota di Progettazione: Il Parametro `ksize=100`

Un dettaglio implementativo cruciale della classe `CQKDNode` è l'impostazione `self.server = Server(ksize=100)`.

Il parametro `ksize` (noto come `k` nel protocollo Kademlia) definisce la dimensione massima di ogni "k-bucket", ovvero gli elenchi che compongono la tabella di routing di un nodo. Un valore tipico per `k` è 20.

La scelta di un valore così alto (100) è voluta e ottimizzata per i requisiti del protocollo CQKD:

1.  **Esigenza del Protocollo**: Per generare una chiave, Alice deve scoprire e allocare un gran numero di nodi worker disponibili sulla rete.
2.  **Beneficio**: Impostando `k=100`, ogni nodo nella DHT mantiene una tabella di routing molto "densa", ovvero conosce l'indirizzo di moltissimi altri nodi. Di conseguenza, quando Alice ha bisogno di trovare 100 worker, ha una probabilità estremamente alta di trovarli quasi tutti direttamente nella sua tabella di routing locale.
3.  **Ottimizzazione**: Questo evita la necessità di una lenta ricerca ricorsiva attraverso la rete (chiedendo ai vicini di conoscere altri nodi), rendendo la fase di **node discovery quasi istantanea**.

In sintesi, il progetto sacrifica consapevolmente una maggiore quantità di memoria su ogni nodo per accelerare drasticamente una delle operazioni più critiche del protocollo.

---

In sintesi, il setup crea una rete Kademlia standard dove un bootstrap node introduce i worker, Alice e Bob. Una volta connessi, tutti i nodi conoscono una porzione significativa della rete, permettendo ad Alice di avviare il protocollo per trovare nodi intermedi e stabilire un canale quantistico con Bob.
