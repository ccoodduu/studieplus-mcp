import logging
import sys

def get_logger(name: str = "studieplus") -> logging.Logger:
    """Get a logger that outputs to stderr (safe for MCP servers)."""
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(
            "[%(levelname)s] %(message)s"
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

    return logger

logger = get_logger()
