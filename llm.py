import os
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

def get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model = os.getenv("LLM_MODEL"),
        api_key = os.getenv("API_KEY"),
        base_url = os.getenv("BASE_URL")
    )