import os
import sys
import time
import numpy as np
from huggingface_hub import InferenceClient

from src.exception import MyException
from src.logger import logger


def embed_texts(
    texts: list,
    model_name: str,
    max_retries: int = 3,
    retry_delay: float = 3.0,
) -> list:
    try:
        api_key = os.getenv("HF_TOKEN")

        if not api_key:
            raise ValueError("HF_TOKEN is not set in environment variables")

        client = InferenceClient(token=api_key)

        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"HF embedding attempt {attempt}/{max_retries}")

                embeddings = client.feature_extraction(
                    texts,
                    model=model_name,
                )

                return np.asarray(embeddings, dtype="float32").tolist()

            except Exception as e:
                last_error = e

                logger.warning(
                    f"HF embedding attempt " f"{attempt}/{max_retries} failed: {e}"
                )

                if attempt < max_retries:
                    wait_time = retry_delay * attempt

                    logger.info(
                        f"Retrying HF embedding request in " f"{wait_time} seconds..."
                    )

                    time.sleep(wait_time)

        raise last_error

    except Exception as e:
        raise MyException(e, sys) from e
