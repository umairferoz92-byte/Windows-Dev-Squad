"""Load a trained classifier and score text at inference time.

Both models are saved as Keras .keras + a vocab.json (and labels.json for the
intent model). Rebuilding the TextVectorization layer with the same config as
training (squad.models.common.build_text_vectorizer) then restoring its
vocabulary keeps inference consistent without re-adapting.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import tensorflow as tf

from squad.models.common import build_text_vectorizer
from squad.models.train import ARTIFACTS


def _load_vectorizer(vocab: list[str]):
    vec = build_text_vectorizer()
    # set_vocabulary expects the [UNK] slot at index 1; keras populates it.
    vec.set_vocabulary(vocab)
    return vec


class IntentClassifier:
    """Loads squad/models/artifacts/intent and predicts the chat intent."""

    def __init__(self, dirpath: Path | str | None = None):
        d = Path(dirpath) if dirpath else ARTIFACTS / "intent"
        self.model = tf.keras.models.load_model(d / "model.keras")
        meta = json.loads((d / "vocab.json").read_text(encoding="utf-8"))
        self.vec = _load_vectorizer(meta["vocab"])
        labels = json.loads((d / "labels.json").read_text(encoding="utf-8"))
        self.labels: list[str] = labels["labels"]

    def predict(self, text: str) -> tuple[str, float]:
        probs = self.model.predict(self.vec([text]), verbose=0)[0]
        idx = int(np.argmax(probs))
        return self.labels[idx], float(probs[idx])


class SecurityClassifier:
    """Loads squad/models/artifacts/security and flags vulnerable snippets."""

    def __init__(self, dirpath: Path | str | None = None):
        d = Path(dirpath) if dirpath else ARTIFACTS / "security"
        self.model = tf.keras.models.load_model(d / "model.keras")
        meta = json.loads((d / "vocab.json").read_text(encoding="utf-8"))
        self.vec = _load_vectorizer(meta["vocab"])

    def predict(self, code: str) -> tuple[float, str]:
        p = float(self.model.predict(self.vec([code]), verbose=0)[0][0])
        verdict = "vulnerable" if p >= 0.5 else "likely-safe"
        return p, verdict


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("usage: python -m squad.models.infer <intent|security> '<text>'")
        raise SystemExit(1)
    which, text = sys.argv[1], sys.argv[2]
    if which == "intent":
        clf = IntentClassifier()
        label, conf = clf.predict(text)
        print(f"intent={label} conf={conf:.3f}")
    elif which == "security":
        clf = SecurityClassifier()
        p, v = clf.predict(text)
        print(f"verdict={v} prob={p:.3f}")
    else:
        print("unknown model: use 'intent' or 'security'")
        raise SystemExit(2)