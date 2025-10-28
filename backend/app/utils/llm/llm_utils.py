import os
from datetime import datetime


import tiktoken

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import AzureChatOpenAI
from langchain_openai import ChatOpenAI

from typing import Any

try:
    # Langfuse >=3 import path
    from langfuse.langchain import CallbackHandler  # type: ignore
except Exception:  # pragma: no cover - fallback for Langfuse <3
    try:
        # Langfuse <3 import path
        from langfuse.callback import CallbackHandler  # type: ignore
    except Exception:
        CallbackHandler = None  # type: ignore
from pydantic import BaseModel

import logging

from app.core.config import settings

# Legacy env var support - use config.py settings by default
try:
    LLM_SERVICE = os.getenv("LLM_SERVICE", settings.LLM_PROVIDER)
except KeyError:
    LLM_SERVICE = "OpenAI"


def get_langfuse_handler(session_id: str = None) -> Any:
    """Initialise a Langfuse callback handler"""
    if session_id is None:
        session_id = f"{datetime.today().isoformat()}"

    # The Langfuse LangChain CallbackHandler reads configuration from environment variables.
    # It does not accept user/session/keys as init kwargs.
    if CallbackHandler is None:
        return None
    return CallbackHandler()


def get_llm(model_name: str = None, temperature: float = None) -> ChatOpenAI:
    """Get an LLM instance

    Args:
        model_name: Name of the model to use
        temperature: Temperature setting for the model

    Returns:
        ChatOpenAI or AzureChatOpenAI instance
    """
    if LLM_SERVICE == "Azure":
        logging.info("Using Azure OpenAI")
        return AzureChatOpenAI(
            openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
            azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            openai_api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            temperature=temperature,
        )
    elif LLM_SERVICE == "OpenAI":
        if (model_name is None) or (temperature is None):
            raise ValueError(
                "Model name and temperature must be specified when not using Azure OpenAI."
            )
        logging.info("Using OpenAI")
        return ChatOpenAI(
            openai_api_key=settings.OPENAI_API_KEY,
            model_name=model_name,
            temperature=temperature,
            request_timeout=120.0,  # 2 minute timeout to prevent hanging
        )
    else:
        raise ValueError(
            f"Unknown LLM_SERVICE: {LLM_SERVICE}. Must be 'OpenAI' or 'Azure'. "
            f"Check your LLM_PROVIDER setting in config.py or LLM_SERVICE environment variable."
        )


def tokenize_text(text: str, model_name: str) -> int:
    """Tokenize text and return the number of tokens."""
    # Get tokenizer for the model
    tokenizer = tiktoken.encoding_for_model(model_name)
    tokens = tokenizer.encode(text)
    # Return both token count and tokens
    return len(tokens), tokens


def decode_tokens(tokens: list, model_name: str) -> str:
    """Decode tokens back into text using the specified model's tokenizer."""
    tokenizer = tiktoken.encoding_for_model(model_name)
    text = tokenizer.decode(tokens)
    return text


def truncate_to_max_tokens(input: str, model_name: str, max_tokens: int) -> bool:
    """Check token length and return truncated input if necessary."""
    n_tokens, tokens = tokenize_text(input, model_name)
    if n_tokens > max_tokens:
        logging.warning(
            f"Input text is too long ({n_tokens} tokens). Truncating to {max_tokens} tokens."
        )
        input = decode_tokens(tokens[:max_tokens], model_name=model_name)
    return input


class StructuredOutputGenerator:
    """Generate structured output from input text using a language model.

    Args:
        model_dict: A dictionary containing the model configuration, with the following
            keys: "model_name", "temperature", "max_tokens"
        output_class: A Pydantic model class for the structured output
        prompts: A dictionary containing the prompts for the structured output.
            Should contain "system_message" and "user_message" keys.
    """

    def __init__(
        self,
        model_dict: dict,
        output_class: BaseModel,
        prompts: dict,
        check_token_length: bool = True,
    ) -> None:
        """Initialise the structured output generator."""
        self.llm = get_llm(model_dict["model_name"], model_dict["temperature"])
        self.model_name = model_dict["model_name"]
        self.temperature = model_dict["temperature"]
        self.max_tokens = model_dict["max_tokens"]
        # self.langfuse_handler = get_langfuse_handler()
        self.output_class = output_class
        self.prompts = prompts
        self.check_token_length = check_token_length

    def generate(self, input_dict: dict) -> BaseModel:
        """Generate structured output from input text.

        Args:
            input_dict: A dictionary containing input data, should follow the format
                {field_name: field_value}, with the field_name corresponding to the
                placeholder in the prompt. Usually at least one of the fields should be "input"
        """
        # Initialise LLM
        structured_llm = self.llm.with_structured_output(self.output_class)
        # Prepare prompt
        structured_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", self.prompts["system_message"]),
                ("user", self.prompts["user_message"]),
            ]
        )
        # Check token length
        _input_dict = input_dict.copy()
        if self.check_token_length:
            _input_dict["input"] = truncate_to_max_tokens(
                input_dict["input"], self.model_name, self.max_tokens
            )
        structured_prompt = structured_prompt.format(**_input_dict)
        # Get response from LLM
        return structured_llm.invoke(
            structured_prompt,
            # config={"callbacks": [self.langfuse_handler]}
        )
