import csv
import difflib
import random
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "careers.csv"

SEED = 42
random.seed(SEED)
np.random.seed(SEED)


def _split(text):
    """Turn 'a|b|c' into ['a', 'b', 'c']."""
    return [t.strip().lower() for t in str(text).split("|") if t.strip()]


class CareerRecommender:
    def __init__(self, csv_path=DATA_PATH):
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        self.records = []
        for row in rows:
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

        self.params = self._train()

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
        return np.array(X, dtype="float32"), np.array(y)

    def _train(self, epochs=150, hidden=64, lr=0.01):
        """A small neural network (one hidden layer) trained with Adam, in pure NumPy."""
        X, y = self._make_training_data()
        n, d = X.shape
        k = len(self.records)
        rng = np.random.default_rng(SEED)

        p = {
            "W1": rng.normal(0, np.sqrt(2.0 / d), (d, hidden)).astype("float32"),
            "b1": np.zeros(hidden, dtype="float32"),
            "W2": rng.normal(0, np.sqrt(2.0 / hidden), (hidden, k)).astype("float32"),
            "b2": np.zeros(k, dtype="float32"),
        }
        m = {key: np.zeros_like(val) for key, val in p.items()}
        v = {key: np.zeros_like(val) for key, val in p.items()}
        Y = np.eye(k, dtype="float32")[y]
        beta1, beta2, eps = 0.9, 0.999, 1e-8

        for t in range(1, epochs + 1):
            # forward pass
            z1 = X @ p["W1"] + p["b1"]
            a1 = np.maximum(0, z1)
            z2 = a1 @ p["W2"] + p["b2"]
            z2 -= z2.max(axis=1, keepdims=True)
            e = np.exp(z2)
            probs = e / e.sum(axis=1, keepdims=True)

            # backward pass
            dz2 = (probs - Y) / n
            grads = {
                "W2": a1.T @ dz2,
                "b2": dz2.sum(axis=0),
            }
            da1 = dz2 @ p["W2"].T
            dz1 = da1 * (z1 > 0)
            grads["W1"] = X.T @ dz1
            grads["b1"] = dz1.sum(axis=0)

            # Adam update
            for key in p:
                m[key] = beta1 * m[key] + (1 - beta1) * grads[key]
                v[key] = beta2 * v[key] + (1 - beta2) * (grads[key] ** 2)
                m_hat = m[key] / (1 - beta1 ** t)
                v_hat = v[key] / (1 - beta2 ** t)
                p[key] -= lr * m_hat / (np.sqrt(v_hat) + eps)

        return p

    def _predict(self, vec):
        p = self.params
        a1 = np.maximum(0, vec @ p["W1"] + p["b1"])
        z2 = a1 @ p["W2"] + p["b2"]
        z2 -= z2.max(axis=1, keepdims=True)
        e = np.exp(z2)
        return (e / e.sum(axis=1, keepdims=True))[0]

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
        probs = self._predict(vec)

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