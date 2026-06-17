from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from django.conf import settings
from langchain_google_genai import ChatGoogleGenerativeAI


class BaseLLMProvider(ABC):
    @abstractmethod
    def chat(self, messages: List[Dict], tools: Optional[List] = None) -> str:
        pass


class OpenAIProvider(BaseLLMProvider):
    def __init__(self):
        from langchain_openai import ChatOpenAI

        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set in environment variables.")

        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.OPENAI_API_KEY,
            temperature=0.1,
        )

    def chat(self, messages, tools=None):
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        lc_messages = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "user":
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))

        response = self.llm.invoke(lc_messages)
        return response.content


class GeminiProvider(BaseLLMProvider):
    def __init__(self):
        if not settings.GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY is not set in environment variables.")

        self.llm = ChatGoogleGenerativeAI(
            model=settings.LLM_MODEL,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.1,
        )

    def chat(self, messages, tools=None):
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, FunctionMessage

        lc_messages = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "user":
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
            # Gemini models might expect a different format for tool messages if tools are implemented.
            # For now, we're focusing on basic chat.
        
        response = self.llm.invoke(lc_messages)
        return response.content

