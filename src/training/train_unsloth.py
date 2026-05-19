import os
import sys
from pathlib import Path
from datasets import load_dataset
from trl import SFTTrainer
from transformers import TrainingArguments
from unsloth import FastLanguageModel
from unsloth.chat_templates import get_chat_template
import torch

sys.path.append(str(Path(__file__).parent.parent.parent))
from core_engine.config import get_config

max_seq_length = 2048 # We can keep this small because our JSON is <200 tokens
dtype = None
load_in_4bit = True

# 1. Load Model
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = "Qwen/Qwen2.5-Coder-1.5B",
    max_seq_length = max_seq_length,
    dtype = dtype,
    load_in_4bit = load_in_4bit,
    token = os.getenv("HF_TOKEN"), # Not strictly required for Qwen, but good practice
)

# 2. Add LoRA Adapters
model = FastLanguageModel.get_peft_model(
    model,
    r = 16, # Target attention & MLP
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                      "gate_proj", "up_proj", "down_proj",],
    lora_alpha = 16,
    lora_dropout = 0,
    bias = "none",
    use_gradient_checkpointing = "unsloth", 
    random_state = 3407,
    use_rslora = False,
    loftq_config = None,
)

# 3. Format Dataset
# We use the standard ChatML template for Qwen
tokenizer = get_chat_template(
    tokenizer,
    chat_template = "chatml",
    mapping = {"role" : "role", "content" : "content", "user" : "user", "assistant" : "assistant"}
)

def formatting_prompts_func(examples):
    texts = []
    for sys, user, asst in zip(examples['system'], examples['input'], examples['output']):
        # Map our flat JSON structure into conversation turns
        messages = [
            {"role": "system", "content": sys},
            {"role": "user", "content": user},
            {"role": "assistant", "content": asst}
        ]
        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
        texts.append(text)
    return {"text": texts}

cfg = get_config()
train_file = cfg.data.train_file

print(f"[*] Loading dataset from {train_file}...")
try:
    dataset = load_dataset("json", data_files=train_file, split="train")
    dataset = dataset.map(formatting_prompts_func, batched=True)
except Exception as e:
    print(f"[-] Failed to load dataset: {e}")
    sys.exit(1)

# 4. Train
# We are intentionally overfitting our small 10-row dataset to verify format compliance
trainer = SFTTrainer(
    model = model,
    tokenizer = tokenizer,
    train_dataset = dataset,
    dataset_text_field = "text",
    max_seq_length = max_seq_length,
    dataset_num_proc = 2,
    packing = False,
    args = TrainingArguments(
        per_device_train_batch_size = 2,
        gradient_accumulation_steps = 4,
        warmup_steps = 5,
        max_steps = 60, # Keep small for testing, but in prod change to num_train_epochs
        learning_rate = 2e-4,
        fp16 = not torch.cuda.is_bf16_supported(),
        bf16 = torch.cuda.is_bf16_supported(),
        logging_steps = 1,
        optim = "adamw_8bit",
        weight_decay = 0.01,
        lr_scheduler_type = "linear",
        seed = 3407,
        output_dir = "outputs",
        save_strategy = "epoch", # Phase 3: Save checkpoints per epoch
        save_total_limit = 3,
        report_to = "tensorboard", # Phase 3: Store loss curves
    ),
)

print("Starting Unsloth Fast Training...")
trainer_stats = trainer.train(resume_from_checkpoint=True) # Phase 3: Resume support

# 5. Export for llama.cpp testing
# Export to 4-bit GGUF for the RTX 3050 locally
print("Exporting to GGUF format...")
model.save_pretrained_gguf("architect-js-1.5b", tokenizer, quantization_method = "q4_k_m")
print("Successfully exported architect-js-1.5b-q4_k_m.gguf")
