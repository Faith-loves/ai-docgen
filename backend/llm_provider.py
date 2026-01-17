import os
import json
from typing import Optional, Dict, Any

from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def llm_available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def _system_instructions() -> str:
    return (
        "You are a senior software engineer and technical writer. "
        "Generate beginner-friendly code comments and documentation. "
        "Be accurate. Do not invent behavior that is not present in the code. "
        "Keep comments helpful and not excessive."
    )


def build_prompt(language: str, code: str, file_path: Optional[str] = None) -> str:
    fp = f"File path: {file_path}\n" if file_path else ""
    return (
        f"{fp}"
        f"Language: {language}\n"
        "Task:\n"
        "1) Return commented_code: the same code with meaningful inline comments and docstrings/JSDoc where appropriate.\n"
        "2) Return documentation: a short README-style explanation (what it does, inputs/outputs, edge cases, example usage).\n\n"
        "Output format:\n"
        "Return ONLY valid JSON with exactly these keys:\n"
        '{ "commented_code": "...", "documentation": "..." }\n\n'
        "CODE:\n"
        "-----\n"
        f"{code}\n"
        "-----\n"
    )


def generate_with_llm(language: str, code: str, file_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Calls OpenAI Responses API and returns:
      {commented_code: str, documentation: str}
    """
    model = os.environ.get("DOCGEN_MODEL", "gpt-4o")
    prompt = build_prompt(language=language, code=code, file_path=file_path)

    response = client.responses.create(
        model=model,
        instructions=_system_instructions(),
        input=prompt,
    )

    text = response.output_text.strip()

    # Parse JSON strictly; try to recover if extra text exists
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start: end + 1])
            except Exception:
                pass

    return {
        "commented_code": code,
        "documentation": "LLM output parsing failed. Returned original code."
    }
