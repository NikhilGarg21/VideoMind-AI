import os
import sys
import json
from src.exception import MyException

def save_artifact_json(name: str, data: dict) -> None:
    """
    Save a stage's artifact summary to the DVC metadata directory, used
    for lightweight run tracking outside of DVC's own artifact outputs.

    Args:
        name: The stage name, used as the output filename (e.g. "audio_ingestion").
        data: The artifact data to serialize.

    Raises:
        MyException: If saving fails.
    """
    try:
        os.makedirs("artifact/dvc_meta", exist_ok=True)
        with open(f"artifact/dvc_meta/{name}.json", "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        raise MyException(e, sys)


def load_artifact_json(name: str) -> dict:
    """
    Load a previously saved stage artifact summary from the DVC metadata
    directory.

    Args:
        name: The stage name whose artifact summary to load.

    Returns:
        The parsed artifact data dict.

    Raises:
        MyException: If loading fails.
    """
    try:
        with open(f"artifact/dvc_meta/{name}.json") as f:
            return json.load(f)
    except Exception as e:
        raise MyException(e, sys)


def save_json(data: dict,file_path: str) -> str:
    """Save dictionary data as a JSON file."""
    try:
        output_dir = os.path.dirname(file_path)

        if output_dir:
            os.makedirs(
                output_dir,
                exist_ok=True,
            )

        with open(file_path, "w", encoding="utf-8") as file:
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
