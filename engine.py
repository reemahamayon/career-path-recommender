import csv
import difflib
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "careers.csv"
MODEL_PATH = BASE_DIR / "model" / "career_model.npz"


def _split(text):
    return [t.strip().lower() for t in str(text).split("|") if t.strip()]


class CareerRecommender:
    def __init__(self, csv_path=DATA_PATH, model_path=MODEL_PATH):
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))

        self.records = []
        for row in rows:
            row["skills_list"] = _split(row["skills"])
            row["interests_list"] = _split(row["interests"])
            row["path_list"] = [s.strip() for s in str(row["learning_path"]).split("|")]
            self.records.append(row)

        if not Path(model_path).exists():
            raise FileNotFoundError("Model file missing. Run: python train_model.py")

        data = np.load(model_path)
        self.vocab = [str(v) for v in data["vocab"]]
        self.index = {word: i for i, word in enumerate(self.vocab)}
        self.W1, self.b1 = data["W1"], data["b1"]
        self.W2, self.b2 = data["W2"], data["b2"]
        self.W3, self.b3 = data["W3"], data["b3"]

        if self.W3.shape[1] != len(self.records):
            raise ValueError("careers.csv changed. Run: python train_model.py again")

    def _predict(self, vec):
        h1 = np.maximum(0, vec @ self.W1 + self.b1)
        h2 = np.maximum(0, h1 @ self.W2 + self.b2)
        logits = h2 @ self.W3 + self.b3
        logits = logits - np.max(logits)
        exp = np.exp(logits)
        return (exp / exp.sum())[0]

    def _match_terms(self, raw):
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
    engine = CareerRecommender()
    result = engine.recommend("pyton, sql, pandas, statistics", "numbers, patterns")
    for r in result["recommendations"]:
        print(f"{r['role']} -> {r['match_score']}%")