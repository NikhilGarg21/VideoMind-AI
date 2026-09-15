import json
import os


def save_artifact_json(name: str, data: dict) -> None:
    os.makedirs("artifact/dvc_meta", exist_ok=True)
    with open(f"artifact/dvc_meta/{name}.json", "w") as f:
        json.dump(data, f, indent=4)


def load_artifact_json(name: str) -> dict:
    with open(f"artifact/dvc_meta/{name}.json") as f:
        return json.load(f)
