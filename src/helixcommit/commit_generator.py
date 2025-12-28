"""Commit message generator using LLMs."""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

try:  # pragma: no cover - optional dependency guard
    from openai import OpenAI, RateLimitError
except ImportError:  # pragma: no cover - optional dependency guard
    OpenAI = None  # type: ignore[assignment]
    RateLimitError = Exception  # type: ignore[assignment]

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

    def generate(self, diff: str, stream: bool = False, stream_callback: Optional[Callable[[str], None]] = None) -> str:
        """Start the generation process with a diff."""
        from .prompts import COMMIT_MESSAGE_SYSTEM_PROMPT

        system_prompt = COMMIT_MESSAGE_SYSTEM_PROMPT

        self.history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Here is the staged diff:\n\n{diff}"},
        ]

        # Set stream callback if provided
        if stream and stream_callback:
            self._stream_callback = stream_callback

        return self._call_llm(stream=stream)

    def to_subject(self, text: str) -> str:
        """Normalize an LLM response down to a single commit subject line."""
        message = self.to_message(text)
        if not message:
            return ""
        # Return only the first line (subject)
        first_line = message.split("\n")[0].strip()
        return first_line

    def to_message(self, text: str) -> str:
        """Extract the full commit message (subject + body) from an LLM response.

        Strips any preamble or explanatory text, returning only the actual
        commit message content including bullet points if present.
        """
        if not text:
            return ""

        text = text.replace("\r\n", "\n").strip()
        if not text:
            return ""

        lines = text.split("\n")

        # Patterns that indicate preamble (explanatory text before the commit message)
        preamble_patterns = [
            r"^here\s+is\s+",
            r"^here\'s\s+",
            r"^based\s+on\s+",
            r"^the\s+(?:provided\s+)?diff\s+",
            r"^this\s+(?:commit|change|diff)\s+",
            r"^i\s+(?:would\s+)?suggest",
            r"^a\s+(?:concise\s+)?commit\s+message",
            r"^(?:proposed\s+)?commit\s+message[:\-]",
            r"^the\s+following\s+",
        ]

        # Find where the actual commit message starts
        message_start_idx = 0
        for i, line in enumerate(lines):
            line_lower = line.strip().lower()
            is_preamble = any(re.match(p, line_lower) for p in preamble_patterns)
            if is_preamble:
                # Skip this line and any following empty lines
                message_start_idx = i + 1
                continue
            # Check if this looks like a commit message start (non-empty, not preamble)
            if line.strip() and not is_preamble:
                message_start_idx = i
                break

        # Extract the message from the detected start
        message_lines = lines[message_start_idx:]

        # Strip leading/trailing empty lines
        while message_lines and not message_lines[0].strip():
            message_lines.pop(0)
        while message_lines and not message_lines[-1].strip():
            message_lines.pop()

        if not message_lines:
            return ""

        # Clean up the subject line (first line)
        subject = message_lines[0].strip()

        # Remove markdown code block markers if the whole message is wrapped
        if subject.startswith("```"):
            message_lines.pop(0)
            # Also remove trailing ``` if present
            if message_lines and message_lines[-1].strip() == "```":
                message_lines.pop()
            # Strip again after removing code blocks
            while message_lines and not message_lines[0].strip():
                message_lines.pop(0)
            if message_lines:
                subject = message_lines[0].strip()
            else:
                return ""

        # Strip common subject prefixes
        subject = re.sub(
            r"^(?:(?:proposed\s+)?commit\s+message|message|subject)[:\-]\s*",
            "",
            subject,
            flags=re.IGNORECASE,
        )

        # Rebuild the message with cleaned subject
        message_lines[0] = subject

        # Deduplicate subject if it appears again at the start of the body
        def _norm_for_compare(s: str) -> str:
            """Normalize a line for reliable comparison (lower, strip punctuation)."""
            return re.sub(r"[^\w\s]", "", s.strip().lower())

        if len(message_lines) > 1:
            # Find first non-empty body line
            idx = 1
            while idx < len(message_lines) and not message_lines[idx].strip():
                idx += 1
            if idx < len(message_lines):
                first_body_line = message_lines[idx].strip()
                if _norm_for_compare(first_body_line) == _norm_for_compare(subject):
                    # Remove the duplicate subject line from the body
                    del message_lines[idx]
                    # If the next line is an empty separator, remove it too
                    if idx < len(message_lines) and not message_lines[idx].strip():
                        del message_lines[idx]

        # Join and return
        return "\n".join(message_lines).strip()

    def chat(self, user_input: str) -> str:
        """Continue the conversation with user input."""
        self.history.append({"role": "user", "content": user_input})
        return self._call_llm()

    def _call_llm(self, max_retries: int = 3, stream: bool = False) -> str:
        """Call the LLM and update history with exponential backoff retry logic."""
        last_error = None
        
        for attempt in range(max_retries):
            try:
                if stream:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=self.history,
                        stream=True,
                    )
                    content = ""
                    for chunk in response:
                        delta = chunk.choices[0].delta.content or ""
                        content += delta
                        # Yield partial content for streaming
                        if hasattr(self, '_stream_callback') and self._stream_callback:
                            self._stream_callback(delta)
                    self.history.append({"role": "assistant", "content": content})
                    return content
                else:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=self.history,
                        stream=False,
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
        
        # Should not reach here if max_retries > 0
        raise RuntimeError("Failed to call LLM after all retries")
