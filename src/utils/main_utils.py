import os
import sys
import json
from src.exception import MyException

def save_artifact_json(name: str, data: dict) -> None:
    os.makedirs("artifact/dvc_meta", exist_ok=True)
    with open(f"artifact/dvc_meta/{name}.json", "w") as f:
        json.dump(data, f, indent=4)


def load_artifact_json(name: str) -> dict:
    with open(f"artifact/dvc_meta/{name}.json") as f:
        return json.load(f)


def save_json(
    data: dict,
    file_path: str,
) -> str:
    """Save dictionary data as a JSON file."""
    try:
        output_dir = os.path.dirname(file_path)

        if output_dir:
            os.makedirs(
                output_dir,
                exist_ok=True,
            )

        with open(
            file_path,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=4,
            )

        return file_path

    except Exception as e:
        raise MyException(e, sys)


def load_json(
    file_path: str,
) -> dict:
    """Load data from a JSON file."""

    try:
        with open(
            file_path,
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(file)
        return data

    except Exception as e:
        raise MyException(e, sys)


def format_timestamp(seconds: float) -> str:
    """Convert seconds to MM:SS format."""
    minutes = int(seconds // 60)
    seconds = int(seconds % 60)

    return f"{minutes:02d}:{seconds:02d}"
