import json
import logging
import os
import time
from pathlib import Path

LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
LOG_FILE = LOG_DIR / "access.log"


def configure_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("ticket_triage.access")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # UTC with milliseconds so lines line up with JMeter's epoch-ms timestamps across machines.
    formatter = logging.Formatter("%(asctime)s.%(msecs)03dZ %(message)s", "%Y-%m-%dT%H:%M:%S")
    formatter.converter = time.gmtime

    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger


def format_fields(fields: dict) -> str:
    """Render key=value pairs; values containing spaces or quotes are JSON-quoted."""
    parts = []
    for key, value in fields.items():
        text = str(value)
        if not text or any(ch in text for ch in ' "='):
            text = json.dumps(text)
        parts.append(f"{key}={text}")
    return " ".join(parts)
