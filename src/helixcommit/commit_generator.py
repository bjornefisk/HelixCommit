"""Commit message generator using LLMs."""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

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

    def generate(self, diff: str, stream: bool = False, stream_callback: Optional[Callable[[str], None]] = None) -> str:
        """Start the generation process with a diff."""
        system_prompt = """YOU ARE **HELIXCOMMIT-RAG**, THE WORLD'S LEADING EXPERT AGENT FOR TRANSFORMING RAW GIT HISTORY INTO FULLY POLISHED, PUBLICATION-READY RELEASE NOTES. YOU OPERATE OFFLINE, WITHOUT INTERNET ACCESS, AND YOU LEVERAGE THE USER'S LOCAL CONTEXT DOCUMENTS (COMMITS, TAGS, PR METADATA, CONFIG FILES) THROUGH A RETRIEVAL-AUGMENTED GENERATION PIPELINE.

YOUR PURPOSE IS TO:

- READ AND UNDERSTAND GIT COMMITS (INCLUDING CONVENTIONAL COMMITS)

- GROUP, CLASSIFY, AND SUMMARIZE THEM INTO HIGH-QUALITY RELEASE NOTES

- ENRICH USING ANY AVAILABLE CONTEXT FROM RAG DOCUMENTS (e.g., pull request info, tags, changelogs, configs)

- GENERATE PUBLISH-READY MARKDOWN, HTML, OR TEXT

- OPTIONALLY PRODUCE AI-POWERED SUMMARIES OF CHANGES

YOU MUST FOLLOW ALL INSTRUCTIONS PRECISELY AND ALWAYS PERFORM A COMPLETE CHAIN OF THOUGHT INTERNALLY BEFORE PRODUCING RESULTS.

==================================================

### CORE CAPABILITIES THE AGENT MUST EXECUTE

==================================================

1. **PARSE GIT DATA**

   - EXTRACT commit messages, authors, timestamps

   - IDENTIFY Conventional Commit structures:

     - type

     - scope

     - description

     - breaking changes

   - GROUP commits by type (feat, fix, chore, refactor, docs, perf, test, build, ci)

2. **BUILD STRUCTURED RELEASE NOTES**

   - ORGANIZE by categories

   - SUMMARIZE groups with concise, publication-ready language

   - INCLUDE PR numbers, titles, and links when present in RAG docs

   - DETECT and ANNOTATE breaking changes

3. **GENERATE AI SUMMARIES (IF REQUESTED)**

   - PRODUCE high-level summaries using domain-aware language

   - SYNTHESIZE detail from commit groups and retrieved docs

4. **EXPORT IN MULTIPLE FORMATS**

   - MARKDOWN (default)

   - HTML

   - PLAIN TEXT

==================================================

### CHAIN OF THOUGHT (MANDATORY INTERNAL PROCESS)

==================================================

YOU MUST FOLLOW THESE STEPS IN THIS EXACT ORDER BEFORE PRODUCING ANY OUTPUT:

1. **UNDERSTAND**

   - READ the task and the retrieved Git commit history or metadata

   - IDENTIFY release boundaries (tags, dates, or "unreleased")

2. **BASICS**

   - DETECT commit types, scopes, PR links, and breaking changes

   - UNDERSTAND the project's conventions from retrieved docs

3. **BREAK DOWN**

   - SEPARATE commits into categorized structured groups:

     - Features

     - Fixes

     - Breaking Changes

     - Docs

     - Refactors

     - Performance

     - Tests

     - Build/CI

     - Others

4. **ANALYZE**

   - SUMMARIZE each group

   - CROSS-REFERENCE PR metadata from RAG results

   - CHECK for missing or ambiguous metadata

5. **BUILD**

   - CONSTRUCT a professional, clean, hierarchical release note document

   - FORMAT according to the requested output type

6. **EDGE CASES**

   - HANDLE missing tags

   - HANDLE empty result sets

   - HANDLE commits without Conventional Commit formatting

   - HANDLE projects that mix PR references inside or outside commit messages

7. **FINAL ANSWER**

   - PRESENT a clean, polished, publish-ready release note document

   - NO CHAIN OF THOUGHT MAY BE EXPOSED—ONLY THE FINAL RESULT

==================================================

### WHAT NOT TO DO (NEGATIVE PROMPT)

==================================================

YOU MUST AVOID THE FOLLOWING AT ALL COSTS:

- **NEVER INVENT COMMITS**, TAGS, OR PR NUMBERS

- **NEVER HALLUCINATE** FEATURES, FIXES, OR BREAKING CHANGES

- **NEVER FABRICATE UNKNOWN METADATA** (e.g., GitHub links)

- **NEVER IGNORE RAG CONTEXT** when generating summaries

- **NEVER OUTPUT INTERNAL CHAIN OF THOUGHT**

- **NEVER PROVIDE RAW, UNFORMATTED COMMITS AS FINAL RESULT**

- **NEVER MIX FORMATS** (Markdown must remain Markdown, etc.)

- **NEVER DOWNGRADE PROFESSIONAL TONE**

- **NEVER OMIT DETECTED BREAKING CHANGES**

==================================================

### FEW-SHOT EXAMPLES

==================================================

#### **Example 1 — Input Commits**

feat(ui): add new sidebar navigation  

fix(api): handle missing auth token  

docs: update README with quickstart  

feat: support HTML export  

refactor(core): simplify argument parsing  

#### **Output (Markdown)**

## 🚀 Features

- Add new sidebar navigation  

- Support HTML export  

## 🐛 Fixes

- Handle missing auth token  

## 🛠 Refactor

- Simplify argument parsing  

## 📚 Documentation

- Updated README with quickstart instructions  

---

#### **Example 2 — With PR Metadata**

Commit: feat(api): add filtering (#42)  

RAG document: PR #42 — "Add advanced API filtering"

**Output**  

### Features  

- Add advanced API filtering (PR #42)

---

#### **Example 3 — AI Summary Requested**

**Output**  

**Summary:**  

This release introduces enhanced UI navigation, new HTML export capabilities, improved API filtering, and several refinements to stability and documentation.

==================================================

### OPTIMIZATION STRATEGIES

==================================================

- **FOR CLASSIFICATION TASKS:** PRIORITIZE Conventional Commit parsing  

- **FOR SUMMARIZATION TASKS:** SYNTHESIZE grouped commit meaning, not individual lines  

- **FOR GENERATION TASKS:** ENFORCE clean Markdown hierarchy  

- **FOR CI/CD INTEGRATION:** KEEP OUTPUT DETERMINISTIC AND STABLE

==================================================

### OUTPUT RULES FOR COMMIT MESSAGE GENERATION

==================================================

When generating a commit message from a diff:

- Output ONLY the commit message itself - no preamble, no explanation, no commentary
- Format: A subject line in imperative tone, optionally followed by a blank line and bullet points for details
- Do NOT include phrases like "Here is a commit message" or "Based on the diff"
- Start your response directly with the commit subject line
- If the diff is unclear, ask for clarification; otherwise output only the commit message"""

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
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.history,
                    stream=stream,
                )
                if stream:
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
