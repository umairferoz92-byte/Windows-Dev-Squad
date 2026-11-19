"""TensorFlow intent + code-security classifier scaffold.

Two independent TensorFlow models:
 - squad/models/intent_classifier/   : multi-class text classification for squad chat intents.
 - squad/models/security_classifier/ : binary/multilabel code-security classifier.

Training is driven by `squad/models/train.py`. A tiny synthetic dataset is
generated on first run so you can see the pipeline work without external data.
Replace the synthetic generator with your own CSV/JSONL loader as needed.
"""

from __future__ import annotations
