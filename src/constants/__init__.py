import os
from datetime import date
from dotenv import load_dotenv
load_dotenv()

PIPELINE_NAME: str = "VideoMind"
ARTIFACT_DIR: str = "artifact"

CURRENT_YEAR = date.today().year

# Application constants
APP_HOST: str = "0.0.0.0"
APP_PORT: int = 5000