"""Commit message generator using LLMs."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

try:  # pragma: no cover - optional dependency guard
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency guard
    OpenAI = None  # type: ignore[assignment]

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
        today = datetime.now().strftime("%m-%d-%Y")
        system_prompt = (
            f"You are an expert developer. Today is {today}. "
            "Your task is to generate a concise and descriptive commit message based on the provided git diff. "
            "The final commit message format must be 'MM-DD-YYYY: {message}', but you should focus on drafting the '{message}' part first. "
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

    def _call_llm(self) -> str:
        """Call the LLM and update history."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=self.history,
        )
        content = response.choices[0].message.content or ""
        self.history.append({"role": "assistant", "content": content})
        return content
