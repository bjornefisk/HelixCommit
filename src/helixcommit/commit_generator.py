"""Commit message generator using LLMs."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

try:  # pragma: no cover - optional dependency guard
    from openai import OpenAI, RateLimitError
except ImportError:  # pragma: no cover - optional dependency guard
    OpenAI = None  # type: ignore[assignment]
    RateLimitError = None  # type: ignore[assignment]

if TYPE_CHECKING:  # pragma: no cover - type checking only
    # Precise type for messages passed to chat.completions.create
    from openai.types.chat import ChatCompletionMessageParam
else:  # Fallback so runtime doesn't require the types module
    ChatCompletionMessageParam = Dict[str, Any]  # type: ignore[misc,assignment]


class CommitGenerator:
    """Generates commit messages from git diffs using an LLM."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: Optional[str] = None,
    ) -> None:
        """Initialize the generator."""
        if OpenAI is None:
            raise ImportError(
                "The 'openai' package is required for AI features. "
                "Install it with 'pip install openai'."
            )

        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        # Use the official OpenAI message param type so type checkers match the SDK
        self.history: List[ChatCompletionMessageParam] = []

    def generate(self, diff: str) -> str:
        """Start the generation process with a diff."""
        system_prompt = (
            "You are an expert developer. "
            "Your task is to generate a concise and descriptive commit message based on the provided git diff. "
            "If the diff is large, complex, or ambiguous, ask the user clarifying questions to understand the intent. "
            "If the changes are clear, propose a commit message. "
            "Be concise and professional."
        )

        self.history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Here is the staged diff:\n\n{diff}"},
        ]

        return self._call_llm()

    def chat(self, user_input: str) -> str:
        """Continue the conversation with user input."""
        self.history.append({"role": "user", "content": user_input})
        return self._call_llm()

    def _call_llm(self, max_retries: int = 3) -> str:
        """Call the LLM and update history with exponential backoff retry logic."""
        last_error = None
        
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.history,
                )
                content = response.choices[0].message.content or ""
                self.history.append({"role": "assistant", "content": content})
                return content
            except RateLimitError as e:
                last_error = e
                if attempt < max_retries - 1:
                    # Calculate exponential backoff: 2^attempt seconds
                    wait_time = 2 ** attempt
                    print(
                        f"\n⚠️  Rate limit exceeded. Retrying in {wait_time} seconds "
                        f"(attempt {attempt + 1}/{max_retries})..."
                    )
                    time.sleep(wait_time)
                else:
                    # Last attempt failed
                    error_msg = str(e)
                    if "free-models-per-day" in error_msg:
                        raise RuntimeError(
                            "Rate limit exceeded on free-tier model. "
                            "You have exhausted your daily free requests. "
                            "Options:\n"
                            "1. Add credits to your OpenRouter account\n"
                            "2. Use a different LLM provider (OpenAI, Anthropic, etc.)\n"
                            "3. Try again tomorrow"
                        ) from e
                    raise
            except Exception as e:
                # Other errors should fail immediately
                raise
