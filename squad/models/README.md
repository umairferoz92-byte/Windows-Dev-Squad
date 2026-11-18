# TensorFlow classifiers (intent + code-security)

Two small TensorFlow text classifiers that power the `squad chat` assistant:

| Model      | Task                                   | Output |
|------------|----------------------------------------|--------|
| `intent`   | route a chat message to a `squad` action | softmax over 12 intents (review, scan, fetch, status, …) |
| `security` | flag vulnerable code snippets           | sigmoid 0..1 + verdict (vulnerable / likely-safe) |

## Layout

```
squad/models/
  dataset.py    synthetic training data (replace with your own loader)
  common.py     shared vectorizer + Keras classifier builder + training loop
  train.py      entry point; trains both models, saves artifacts/
  infer.py      load artifacts and predict at runtime
  artifacts/    trained models (gitignored; retrain locally)
```

## Architecture

Embedding -> GlobalMaxPooling1D -> Dense(64, relu) -> output head
(softmax for intent, sigmoid for security). Max pooling is used because
short, heavily-padded sequences otherwise drown the few informative tokens
in an average pool.

## Train

From the repo root, with the venv active:

```powershell
env -u PYTHONPATH .venv/Scripts/python.exe -m squad.models.train --epochs 30
```

Options: `--epochs N`, `--intent-only`, `--security-only`.

## Predict

```powershell
env -u PYTHONPATH .venv/Scripts/python.exe -m squad.models.infer intent  "review C:/code/app.py"
env -u PYTHONPATH .venv/Scripts/python.exe -m squad.models.infer security "eval(request.args.get('code'))"
```

## Wiring into the chat

`squad/chat/classifier.py` loads both models lazily. When the rule-based
parser (offline tier) only reaches its LLM catch-all, the intent classifier
can confidently route the message to a real `squad` action instead. It
degrades to `None` (never raises) if TensorFlow or the artifacts are absent,
so the chatbot stays fully usable in offline installs.

The synthetic datasets are deliberately small so the pipeline runs anywhere
in seconds. For production use, replace `dataset.py` with your own labeled
examples (e.g. real chat logs for intents; a curated vuln/safe code corpus for
security) and retrain.
