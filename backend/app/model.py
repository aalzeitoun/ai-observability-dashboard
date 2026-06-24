import random
import time
from uuid import uuid4

from sklearn.datasets import load_iris
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


class IrisModelSimulator:
    def __init__(self) -> None:
        dataset = load_iris()

        self.feature_names = [
            "sepal_length",
            "sepal_width",
            "petal_length",
            "petal_width",
        ]

        self.target_names = list(dataset.target_names)
        self.training_rows = dataset.data.tolist()

        self.model = make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=200),
        )
        self.model.fit(dataset.data, dataset.target)

    def _sample_normal_features(self) -> list[float]:
        row = random.choice(self.training_rows)

        return [
            max(0.1, round(value + random.gauss(0, 0.08), 2))
            for value in row
        ]

    def _sample_drifted_features(self) -> list[float]:
        row = random.choice(self.training_rows)

        drifted_row = [
            row[0] + random.gauss(0.35, 0.12),
            row[1] + random.gauss(-0.20, 0.10),
            row[2] + random.gauss(1.25, 0.25),
            row[3] + random.gauss(0.55, 0.15),
        ]

        return [
            max(0.1, round(value, 2))
            for value in drifted_row
        ]

    def simulate(self, profile: str = "normal") -> dict:
        if profile == "drift":
            features_list = self._sample_drifted_features()
            latency_ms = round(random.uniform(35, 120), 2)
        else:
            features_list = self._sample_normal_features()
            latency_ms = round(random.uniform(12, 45), 2)

        start_time = time.perf_counter()
        probabilities = self.model.predict_proba([features_list])[0].tolist()
        prediction = int(max(range(len(probabilities)), key=lambda index: probabilities[index]))
        confidence = round(float(probabilities[prediction]), 4)
        model_time_ms = round((time.perf_counter() - start_time) * 1000, 4)

        features = dict(zip(self.feature_names, features_list))

        return {
            "request_id": f"sim-{uuid4()}",
            "model_name": "iris-logistic-regression",
            "features": features,
            "prediction": prediction,
            "prediction_label": self.target_names[prediction],
            "confidence": confidence,
            "latency_ms": latency_ms + model_time_ms,
            "profile": profile,
        }

    def info(self) -> dict:
        return {
            "model_name": "iris-logistic-regression",
            "dataset": "iris",
            "features": self.feature_names,
            "target_labels": self.target_names,
            "simulated_profiles": ["normal", "drift"],
        }


model_simulator = IrisModelSimulator()
