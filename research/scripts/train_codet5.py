import os
from pathlib import Path

from datasets import load_dataset
from transformers import (
    AutoTokenizer,
    AutoModelForSeq2SeqLM,
    DataCollatorForSeq2Seq,
    TrainingArguments,
    Trainer,
)

BASE_DIR = Path(__file__).resolve().parents[1]  # research/
DATA_DIR = BASE_DIR / "data" / "processed"
OUT_DIR = BASE_DIR / "models" / "codet5-small-commenter"

TRAIN_PATH = str(DATA_DIR / "train.jsonl")
VALID_PATH = str(DATA_DIR / "valid.jsonl")
TEST_PATH = str(DATA_DIR / "test.jsonl")

MODEL_NAME = "Salesforce/codet5-small"

MAX_INPUT_LEN = 256
MAX_TARGET_LEN = 128

TASK_PREFIX = "comment: "  # important for CodeT5


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading dataset...")
    data_files = {"train": TRAIN_PATH, "test": TEST_PATH}
    if os.path.exists(VALID_PATH) and os.path.getsize(VALID_PATH) > 0:
        data_files["validation"] = VALID_PATH

    ds = load_dataset("json", data_files=data_files)

    print("Loading tokenizer/model...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)

    def preprocess(examples):
        # Add task prefix to help model know what to do
        inputs = [TASK_PREFIX + c for c in examples["code"]]
        targets = examples["comment"]

        model_inputs = tokenizer(
            inputs,
            max_length=MAX_INPUT_LEN,
            truncation=True,
            padding="max_length",
        )

        labels = tokenizer(
            targets,
            max_length=MAX_TARGET_LEN,
            truncation=True,
            padding="max_length",
        )

        model_inputs["labels"] = labels["input_ids"]
        return model_inputs

    print("Tokenizing...")
    tokenized = ds.map(preprocess, batched=True, remove_columns=ds["train"].column_names)

    data_collator = DataCollatorForSeq2Seq(tokenizer=tokenizer, model=model)

    args = TrainingArguments(
        output_dir=str(OUT_DIR),
        per_device_train_batch_size=1,
        per_device_eval_batch_size=1,
        num_train_epochs=5,          # more epochs helps small data
        learning_rate=5e-5,
        logging_steps=1,
        save_steps=10,
        save_total_limit=2,
        eval_strategy="no",
        report_to="none",
        fp16=False,
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=tokenized["train"],
        tokenizer=tokenizer,
        data_collator=data_collator,
    )

    print("Training (CPU)...")
    trainer.train()

    print("Saving model...")
    trainer.save_model(str(OUT_DIR))
    tokenizer.save_pretrained(str(OUT_DIR))

    print("Done. Model saved to:", OUT_DIR)


if __name__ == "__main__":
    main()
