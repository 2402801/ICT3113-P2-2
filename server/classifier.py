import random
import time

from categories import CATEGORIES

# Placeholder classifier for the baseline. Not yet wired up to Ollama
# swap this out for a real model call once the classification backend is
# decided, keeping the same classify(narrative) -> category signature.


def classify(narrative: str) -> str:
    time.sleep(0.05)
    return random.choice(CATEGORIES)
