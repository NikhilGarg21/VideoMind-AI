import os
import sys
import json

from src.exception import MyException


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
