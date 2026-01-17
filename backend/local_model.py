from pathlib import Path
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

# Path to the trained model (from research folder)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = PROJECT_ROOT / "research" / "models" / "codet5-small-commenter"

TASK_PREFIX = "comment: "
MAX_INPUT_LEN = 256

_tokenizer = None
_model = None


def load_model():
    global _tokenizer, _model
    if _tokenizer is None or _model is None:
        _tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))
        _model = AutoModelForSeq2SeqLM.from_pretrained(str(MODEL_DIR))
        _model.eval()
    return _tokenizer, _model


def generate_comment(code: str) -> str:
    tokenizer, model = load_model()

    prompt = TASK_PREFIX + code
    inputs = tokenizer(
        prompt,
        max_length=MAX_INPUT_LEN,
        truncation=True,
        return_tensors="pt",
    )

    with torch.no_grad():
        out_ids = model.generate(
            **inputs,
            max_new_tokens=64,
            num_beams=4,
            no_repeat_ngram_size=3,
        )

    return tokenizer.decode(out_ids[0], skip_special_tokens=True).strip()

