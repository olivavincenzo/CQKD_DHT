import logging
import sys
import structlog
from config import settings


def setup_logging():
    """Configura logging strutturato per l'applicazione"""
    
    # ✅ SILENZIA LIBRERIE ESTERNE
    # Kademlia
    logging.getLogger('kademlia').setLevel(logging.WARNING)  # Solo WARNING ed errori
    # Oppure completamente disabilitato:
    # logging.getLogger('kademlia').setLevel(logging.CRITICAL)
    
    # Altri logger fastidiosi (se necessario)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    
    # File handler per log.txt
    file_handler = logging.FileHandler('log.txt', mode='w', encoding='utf-8')
    file_handler.setLevel(getattr(logging, settings.log_level.upper()))
    file_handler.setFormatter(logging.Formatter('%(message)s'))
    
    # Configura logging standard
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, settings.log_level.upper()),
        handlers=[
            logging.StreamHandler(sys.stdout),  # Console
            file_handler  # File log.txt
        ]
    )
    
    # Processors per structlog
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]
    
    if settings.log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    """Ottieni un logger strutturato"""
    return structlog.get_logger(name)
