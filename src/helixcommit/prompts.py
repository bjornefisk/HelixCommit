COMMIT_MESSAGE_SYSTEM_PROMPT = """
When generating a commit message from a diff:

- Output ONLY the commit message itself - no preamble, no explanation, no commentary
- Format: A subject line in imperative tone, optionally followed by a blank line and bullet points for details
- Do NOT include phrases like "Here is a commit message" or "Based on the diff"
- Start your response directly with the commit subject line
- If the diff is unclear, ask for clarification; otherwise output only the commit message


### Examples

Input: (diff)
Output:
feat: add user login

- Add login form
- Validate credentials
"""