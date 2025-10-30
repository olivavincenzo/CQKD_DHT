# Multi-stage build per ottimizzare dimensione immagine
FROM python:3.11-slim as builder

WORKDIR /app

# Copia solo i requirements per sfruttare la cache di Docker
COPY requirements.txt .

# Installa le dipendenze in una directory locale del builder
RUN pip install --no-cache-dir --prefix="/install" -r requirements.txt


# --- Stage finale ---
FROM python:3.11-slim

WORKDIR /app

# Imposta la variabile d'ambiente PYTHONPATH per includere le librerie installate
ENV PATH="/install/bin:$PATH"
ENV PYTHONPATH=/install/lib/python3.11/site-packages

# Copia le dipendenze installate dallo stage builder
COPY --from=builder /install /install

# Copia tutto il codice sorgente dell'applicazione
COPY . .

# Crea un utente non-root per maggiore sicurezza
RUN useradd -m -u 1000 cqkduser

# Assegna la proprietà della directory di lavoro all'utente cqkduser
RUN chown -R cqkduser:cqkduser /app

USER cqkduser

# Il comando di default verrà specificato nel docker-compose.yml
# ENTRYPOINT ["python", "-m"]

