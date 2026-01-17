from pathlib import Path
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

BASE_DIR = Path(__file__).resolve().parents[1]  # research/
MODEL_DIR = BASE_DIR / "models" / "codet5-small-commenter"

MAX_INPUT_LEN = 256
TASK_PREFIX = "comment: "


def generate_comment(code: str) -> str:
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))
    model = AutoModelForSeq2SeqLM.from_pretrained(str(MODEL_DIR))

    prompt = TASK_PREFIX + code

    inputs = tokenizer(
        prompt,
        max_length=MAX_INPUT_LEN,
        truncation=True,
        return_tensors="pt"
    )

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=120,
            num_beams=4,
            no_repeat_ngram_size=3,
        )

    return tokenizer.decode(output_ids[0], skip_special_tokens=True)


def main():
    test_code = """\
function capitalize(text) {
  if (!text) return "";
  return text[0].toUpperCase() + text.slice(1);
}
"""

    print("Loaded model from:", MODEL_DIR)
    print("\n=== INPUT CODE ===")
    print(test_code)

    pred = generate_comment(test_code)

    print("\n=== GENERATED COMMENT ===")
    print(pred)


if __name__ == "__main__":
    main()
