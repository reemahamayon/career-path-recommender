import os

# Keep the terminal clean (must be set before importing tensorflow)
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

import difflib
import random
from pathlib import Path

import numpy as np
import pandas as pd
import tensorflow as tf

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "careers.csv"

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
tf.random.set_seed(SEED)


def _split(text):
    """Turn 'a|b|c' into ['a', 'b', 'c']."""
    return [t.strip().lower() for t in str(text).split("|") if t.strip()]


class CareerRecommender:
    def __init__(self, csv_path=DATA_PATH):
        df = pd.read_csv(csv_path)
        self.records = []
        for row in df.to_dict("records"):
            row["skills_list"] = _split(row["skills"])
            row["interests_list"] = _split(row["interests"])
            row["path_list"] = [step.strip() for step in str(row["learning_path"]).split("|")]
            self.records.append(row)

        # Build vocabulary of every skill and interest in the dataset
        skill_set, interest_set = set(), set()
        for r in self.records:
            skill_set.update(r["skills_list"])
            interest_set.update(r["interests_list"])
        self.skill_vocab = sorted(skill_set)
        self.interest_vocab = sorted(interest_set)
        self.vocab = sorted(skill_set | interest_set)
        self.index = {word: i for i, word in enumerate(self.vocab)}

        self.model = self._train()

    # ---------- Training ----------
    def _make_training_data(self, samples_per_role=300):
        """Create realistic fake profiles for each role so the network can learn."""
        X, y = [], []
        for role_idx, row in enumerate(self.records):
            core = row["skills_list"] + row["interests_list"]
            for _ in range(samples_per_role):
                vec = np.zeros(len(self.vocab), dtype="float32")
                keep_rate = random.uniform(0.3, 0.9)
                chosen = [t for t in core if random.random() < keep_rate]
                if not chosen:
                    chosen = [random.choice(core)]
                for t in chosen:
                    vec[self.index[t]] = 1.0
                # add a little random noise, like real users have
                for _ in range(random.randint(0, 3)):
                    vec[random.randrange(len(self.vocab))] = 1.0
                X.append(vec)
                y.append(role_idx)
        return np.array(X), np.array(y)

    def _train(self):
        X, y = self._make_training_data()
        model = tf.keras.Sequential([
            tf.keras.layers.Input(shape=(len(self.vocab),)),
            tf.keras.layers.Dense(64, activation="relu"),
            tf.keras.layers.Dropout(0.2),
            tf.keras.layers.Dense(32, activation="relu"),
            tf.keras.layers.Dense(len(self.records), activation="softmax"),
        ])
        model.compile(
            optimizer="adam",
            loss="sparse_categorical_crossentropy",
            metrics=["accuracy"],
        )
        model.fit(X, y, epochs=15, batch_size=32, verbose=0, validation_split=0.1)
        return model

    # ---------- Understanding user input ----------
    def _match_terms(self, raw):
        """Clean user text, fix small typos, and separate unknown terms."""
        if isinstance(raw, str):
            raw = raw.split(",")
        matched, unknown = [], []
        for term in raw:
            t = term.strip().lower()
            if not t:
                continue
            if t in self.index:
                matched.append(t)
                continue
            close = difflib.get_close_matches(t, self.vocab, n=1, cutoff=0.8)
            if close:
                matched.append(close[0])
            else:
                unknown.append(t)
        return sorted(set(matched)), unknown

    # ---------- Recommending ----------
    def recommend(self, skills, interests, top_n=3):
        s_matched, s_unknown = self._match_terms(skills)
        i_matched, i_unknown = self._match_terms(interests)
        user_terms = set(s_matched) | set(i_matched)

        if not user_terms:
            return {
                "error": "We couldn't recognize any of those skills or interests. Try terms like python, sql, creativity.",
                "unrecognized": s_unknown + i_unknown,
            }

        vec = np.zeros((1, len(self.vocab)), dtype="float32")
        for t in user_terms:
            vec[0, self.index[t]] = 1.0
        probs = self.model.predict(vec, verbose=0)[0]

        results = []
        for i, row in enumerate(self.records):
            role_skills = set(row["skills_list"])
            have = sorted(role_skills & user_terms)
            missing = sorted(role_skills - user_terms)
            overlap = len(have) / len(role_skills)
            score = 0.6 * float(probs[i]) + 0.4 * overlap
            results.append({
                "role": row["role"],
                "category": row["category"],
                "description": row["description"],
                "match_score": min(99, round(score * 100)),
                "skills_you_have": have,
                "skills_to_learn": missing,
                "learning_path": row["path_list"],
            })

        results.sort(key=lambda r: r["match_score"], reverse=True)
        return {
            "recommendations": results[:top_n],
            "recognized_skills": s_matched,
            "recognized_interests": i_matched,
            "unrecognized": s_unknown + i_unknown,
        }


if __name__ == "__main__":
    print("Training the model, please wait...")
    engine = CareerRecommender()
    result = engine.recommend(
        skills="pyton, sql, pandas, statistics",
        interests="numbers, patterns",
        top_n=3,
    )
    print("\nRecognized skills:", result["recognized_skills"])
    print("Recognized interests:", result["recognized_interests"])
    print("Not recognized:", result["unrecognized"])
    for r in result["recommendations"]:
        print(f"\n{r['role']}  ->  {r['match_score']}% match")
        print("  You have:", ", ".join(r["skills_you_have"]))
        print("  To learn:", ", ".join(r["skills_to_learn"]))