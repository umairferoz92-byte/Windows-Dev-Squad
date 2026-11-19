"""Shared TensorFlow text-classification utilities.

Both the intent and code-security classifiers are simple Keras
Embedding -> GlobalAveragePooling1D -> Dense text classifiers. This module
keeps tokenizer + model construction in one place so the two tasks stay small.
"""

from __future__ import annotations

import tensorflow as tf


def build_text_vectorizer(max_features: int = 20000, seq_len: int = 32):
    """Return a TextVectorization layer configured for classification."""
    vec = tf.keras.layers.TextVectorization(
        max_tokens=max_features,
        output_mode="int",
        output_sequence_length=seq_len,
        standardize="lower_and_strip_punctuation",
        split="whitespace",
    )
    return vec


def build_classifier(
    vocab_size: int,
    num_classes: int,
    seq_len: int = 32,
    embed_dim: int = 64,
    units: int = 64,
):
    """Small, fast text classifier: Embedding -> MaxPooling -> Dense head.

    num_classes == 1 => sigmoid (binary); else softmax over num_classes.
    Max pooling keeps the few informative tokens from being diluted by the
    padding that dominates short, padded sequences.
    """
    inputs = tf.keras.Input(shape=(seq_len,), dtype="int64", name="text")
    x = tf.keras.layers.Embedding(vocab_size, embed_dim)(inputs)
    x = tf.keras.layers.GlobalMaxPooling1D()(x)
    x = tf.keras.layers.Dense(units, activation="relu")(x)
    if num_classes == 1:
        out = tf.keras.layers.Dense(1, activation="sigmoid", name="pred")(x)
        loss = "binary_crossentropy"
        metrics = ["accuracy", tf.keras.metrics.AUC(name="auc")]
    else:
        out = tf.keras.layers.Dense(num_classes, activation="softmax", name="pred")(x)
        loss = "sparse_categorical_crossentropy"
        metrics = ["accuracy"]
    model = tf.keras.Model(inputs, out)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(1e-3),
        loss=loss,
        metrics=metrics,
    )
    return model


def train_classifier(
    texts,
    labels,
    vocab_size: int = 20000,
    seq_len: int = 32,
    num_classes: int = 1,
    epochs: int = 30,
    batch_size: int = 32,
    val_split: float = 0.2,
    seed: int = 0,
):
    """Fit a classifier; returns (model, vectorizer, class_names, history).

    For multiclass (num_classes > 1), string labels are mapped to integer
    indices over the sorted unique label set. Binary expects 0/1 float labels.

    The train/validation split is done manually (instead of Keras
    ``validation_split``) because that path hits a dtype-promotion error on
    Windows TensorFlow when fed numpy arrays, and a manual split also lets us
    shuffle so validation doesn't land on a single trailing class.
    """
    import numpy as np

    vec = build_text_vectorizer(vocab_size, seq_len)
    vec.adapt(texts)
    vocab = vec.get_vocabulary()
    vocab_size = min(len(vocab), vocab_size) + 1

    model = build_classifier(vocab_size, num_classes, seq_len)

    xs = vec(texts).numpy()
    if num_classes == 1:
        ys = np.asarray(labels, dtype="float32")
        class_names = None
    else:
        class_names = sorted(set(labels))
        index = {lab: i for i, lab in enumerate(class_names)}
        ys = np.asarray([index[lab] for lab in labels], dtype="int64")

    # Shuffle rows so the split isn't a single trailing class.
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(xs))
    xs = xs[perm]
    ys = ys[perm]

    n_val = max(1, int(len(xs) * val_split))
    x_train, y_train = xs[n_val:], ys[n_val:]
    x_val, y_val = xs[:n_val], ys[:n_val]

    history = model.fit(
        x_train,
        y_train,
        validation_data=(x_val, y_val),
        epochs=epochs,
        batch_size=batch_size,
        shuffle=True,
        verbose=2,
    )
    return model, vec, class_names, history
