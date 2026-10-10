import csv
import os

os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

import random
from pathlib import Path

import numpy as np
import tensorflow as tf

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "careers.csv"
OUT_PATH = BASE_DIR / "model" / "career_model.npz"

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
tf.random.set_seed(SEED)


def split(text):
    return [t.strip().lower() for t in str(text).split("|") if t.strip()]


with open(DATA_PATH, newline="", encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))

records = []
skill_set, interest_set = set(), set()
for row in rows:
    skills = split(row["skills"])
    interests = split(row["interests"])
    records.append({"skills": skills, "interests": interests})
    skill_set.update(skills)
    interest_set.update(interests)

vocab = sorted(skill_set | interest_set)
index = {word: i for i, word in enumerate(vocab)}

X, y = [], []
for role_idx, rec in enumerate(records):
    core = rec["skills"] + rec["interests"]
    for _ in range(300):
        vec = np.zeros(len(vocab), dtype="float32")
        keep_rate = random.uniform(0.3, 0.9)
        chosen = [t for t in core if random.random() < keep_rate]
        if not chosen:
            chosen = [random.choice(core)]
        for t in chosen:
            vec[index[t]] = 1.0
        for _ in range(random.randint(0, 3)):
            vec[random.randrange(len(vocab))] = 1.0
        X.append(vec)
        y.append(role_idx)

X = np.array(X)
y = np.array(y)

model = tf.keras.Sequential([
    tf.keras.layers.Input(shape=(len(vocab),)),
    tf.keras.layers.Dense(64, activation="relu"),
    tf.keras.layers.Dropout(0.2),
    tf.keras.layers.Dense(32, activation="relu"),
    tf.keras.layers.Dense(len(records), activation="softmax"),
])
model.compile(
    optimizer="adam",
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"],
)
history = model.fit(X, y, epochs=15, batch_size=32, verbose=0, validation_split=0.1)

W1, b1, W2, b2, W3, b3 = model.get_weights()
OUT_PATH.parent.mkdir(exist_ok=True)
np.savez(
    OUT_PATH,
    W1=W1, b1=b1, W2=W2, b2=b2, W3=W3, b3=b3,
    vocab=np.array(vocab),
)

print("Saved:", OUT_PATH)
print("Final accuracy:", round(float(history.history["accuracy"][-1]), 3))