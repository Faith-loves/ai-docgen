from pathlib import Path
import json

import torch
import evaluate
from nltk.translate.meteor_score import meteor_score
import nltk
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

BASE_DIR = Path(__file__).resolve().parents[1]  # research/
MODEL_DIR = BASE_DIR / "models" / "codet5-small-commenter"
DATA_DIR = BASE_DIR / "data" / "processed"
TEST_PATH = DATA_DIR / "test.jsonl"

TASK_PREFIX = "comment: "
MAX_INPUT_LEN = 256


def to_summary(text: str) -> str:
    if not text:
        return ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("@"):
            continue
        return line
    return text.strip()


def load_test_examples(path: Path):
    examples = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        code = obj.get("code", "")
        ref = to_summary(obj.get("comment", ""))
        if code.strip() and ref.strip():
            examples.append((code, ref))
    return examples


def generate_predictions(codes):
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))
    model = AutoModelForSeq2SeqLM.from_pretrained(str(MODEL_DIR))

    preds = []
    for code in codes:
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
        pred = tokenizer.decode(out_ids[0], skip_special_tokens=True).strip()
        preds.append(pred)
    return preds


def main():
    try:
        nltk.data.find("tokenizers/punkt")
    except LookupError:
        nltk.download("punkt")

    if not TEST_PATH.exists():
        print("ERROR: test.jsonl not found:", TEST_PATH)
        return

    if not MODEL_DIR.exists():
        print("ERROR: trained model not found:", MODEL_DIR)
        print("Run: python train_codet5.py")
        return

    examples = load_test_examples(TEST_PATH)
    if not examples:
        print("ERROR: No test examples found.")
        return

    codes = [c for c, _ in examples]
    refs = [r for _, r in examples]

    preds = generate_predictions(codes)

    print("\n--- SAMPLE OUTPUTS ---")
    for i in range(min(3, len(preds))):
        print("\nPRED:", preds[i])
        print("REF :", refs[i])

    bleu = evaluate.load("sacrebleu")
    rouge = evaluate.load("rouge")

    bleu_result = bleu.compute(predictions=preds, references=[[r] for r in refs])
    rouge_result = rouge.compute(predictions=preds, references=refs)

    meteor_scores = []
    for p, r in zip(preds, refs):
        meteor_scores.append(
            meteor_score([nltk.word_tokenize(r)], nltk.word_tokenize(p))
        )

    print("\n=== EVALUATION RESULTS ===")
    print("BLEU:", round(bleu_result["score"], 4))
    print("ROUGE-1:", round(rouge_result["rouge1"], 4))
    print("ROUGE-2:", round(rouge_result["rouge2"], 4))
    print("ROUGE-L:", round(rouge_result["rougeL"], 4))
    print("METEOR:", round(sum(meteor_scores) / len(meteor_scores), 4))
    print("\nDone.")


if __name__ == "__main__":
    main()
