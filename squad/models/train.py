"""Train both TensorFlow classifiers and save them under squad/models/.

Usage (from the repo root, venv activated):

  env -u PYTHONPATH .venv/Scripts/python.exe -m squad.models.train [--epochs 6]

Outputs:
  squad/models/artifacts/intent/       intent classifier (Keras model + vectorizer + labels)
  squad/models/artifacts/security/     security classifier (Keras model + vectorizer)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from squad.models import dataset
from squad.models.common import train_classifier

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


def _save(model, vec, class_names, out_dir: Path, task: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    model.save(out_dir / "model.keras")
    # Persist the vectorizer vocabulary + config so inference can rebuild it.
    vocab = vec.get_vocabulary()
    (out_dir / "vocab.json").write_text(
        json.dumps({"task": task, "vocab": vocab}), encoding="utf-8"
    )
    if class_names:
        (out_dir / "labels.json").write_text(
            json.dumps({"labels": class_names}), encoding="utf-8"
        )
    print(f"  saved -> {out_dir}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Train squad TF classifiers.")
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--intent-only", action="store_true")
    ap.add_argument("--security-only", action="store_true")
    args = ap.parse_args(argv)

    if not (args.intent_only or args.security_only):
        args.intent_only = args.security_only = True

    if args.intent_only:
        print("[intent] generating dataset + training...")
        texts, labels, classes = dataset.intent_dataset()
        model, vec, class_names, _ = train_classifier(
            texts, labels, num_classes=len(classes), epochs=args.epochs,
        )
        _save(model, vec, class_names, ARTIFACTS / "intent", "intent")

    if args.security_only:
        print("[security] generating dataset + training...")
        texts, labels = dataset.security_dataset()
        model, vec, _, _ = train_classifier(
            texts, labels, num_classes=1, epochs=args.epochs,
        )
        _save(model, vec, None, ARTIFACTS / "security", "security")

    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())