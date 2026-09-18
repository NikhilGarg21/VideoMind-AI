import os
import sys

from dotenv import load_dotenv
from langchain_groq import ChatGroq

from src.exception import MyException
from src.logger import logger

load_dotenv()


class LLMClient:
    def __init__(self):
        try:
            logger.info("Initializing Groq LLM")

            api_key = os.getenv("GROQ_API_KEY")

            if not api_key:
                raise ValueError("GROQ_API_KEY is not set in environment variables")

            self.llm = ChatGroq(
                model="openai/gpt-oss-120b",
                temperature=0,
                max_tokens=4096,
                reasoning_effort="medium",
                api_key=api_key,
            )

            logger.info("Groq LLM initialized successfully")

        except Exception as e:
            raise MyException(e, sys) from e

    def get_llm(self):
        """
            Return the initialized Groq LLM instance.
            Returns:
                The configured ChatGroq client.
        """
        return self.llm
