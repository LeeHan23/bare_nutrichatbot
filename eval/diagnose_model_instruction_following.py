"""Standalone diagnostic: checks whether an Ollama model actually answers a
prompt or just echoes/continues it verbatim on the raw /api/generate
endpoint (no chat template applied).

Found via tsn_bot's report-generation eval: meditron:7b (EPFL's
continued-pretrain medical model, not heavily instruction/RLHF-tuned) was
just continuing the input prompt text rather than answering it -- inflating
"grounding" scores that only looked correct because the input numbers were
being echoed back, not reasoned about.

Import has no side effects -- call diagnose_instruction_following() directly
when you need to check a specific model/prompt pair.
"""
import os

import requests


def _looks_like_echo(prompt: str, response_text: str, sample_len: int = 100) -> bool:
    """True if the model's response contains a verbatim chunk of the start
    of the prompt -- the signature of a base/completion-style model
    continuing the input instead of responding to it."""
    sample = prompt.strip()[:sample_len]
    return bool(sample) and sample in response_text


def diagnose_instruction_following(
    prompt: str,
    model: str,
    base_url: str | None = None,
    required_headings: list[str] | None = None,
    max_tokens: int = 600,
    timeout_s: int = 60,
) -> dict:
    """Calls `model` on an Ollama server with `prompt` and reports whether it
    followed instructions: non-empty, not an echo of the prompt, and (if
    given) which required_headings actually appear in the response.
    """
    base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.5, "num_predict": max_tokens, "keep_alive": -1},
    }
    resp = requests.post(f"{base_url}/api/generate", json=payload, timeout=timeout_s)
    resp.raise_for_status()
    response_text = resp.json().get("response", "")

    return {
        "empty": not response_text,
        "looks_like_echo": _looks_like_echo(prompt, response_text),
        "headings_present": {h: h.lower() in response_text.lower() for h in (required_headings or [])},
        "raw_response": response_text,
    }


if __name__ == "__main__":
    assert _looks_like_echo(
        "You are drafting a report.\nPatient data here.",
        "You are drafting a report.\nPatient data here. And then some more.",
    )
    assert not _looks_like_echo(
        "You are drafting a report.",
        "A completely different, unrelated answer about the weather.",
    )
    print("diagnose_model_instruction_following: self-check passed.")
    print("Call diagnose_instruction_following(prompt, model) directly for a live check.")
