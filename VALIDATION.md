# Validation Guide & Benchmarks 🧪

This document strictly defines how developers and contributors can verify that the Architect-JS training and inference pipelines are functioning correctly without hallucinations or structural failure.

Because Architect-JS relies on highly deterministic AST extraction and strict `<thought>`/`<diff>` XML tags, arbitrary LLM drift will break the system. **Run these validations before submitting any PRs or starting large-scale data ingestion.**

---

## 1. Environment Setup

To run the validation test suite, ensure your environment is configured:

1. **Python Dependencies:** `pip install -r requirements.txt`
2. **Node Dependencies:** `cd src/analyzer && npm install`
3. **Local Inference Engine:** Download `llama.cpp` and compile the `llama-server` binary.

---

## 2. AST Compression & Schema Validation

Before an AST is sent to the LLM, we must guarantee it maps to our minimal schema.

**Command:**
```bash
node src/analyzer/ast_compressor.js ./data/test_files/ComplexComponent.tsx
```

**Expected Output Checklist:**
- [x] Must contain the keys: `file`, `exports`, `imports`, `hooks`, `deps`, `children`.
- [x] Must enforce a strict token limit (<3500 tokens). If exceeded, the script must throw an explicit error.
- [x] Must accurately map `useEffect` external references to the `deps` object.

---

## 3. Dataset Generation Validation

The script merges ASTs with manual fixes.

**Command:**
```bash
node src/analyzer/build_dataset.js
```

**What it tests:**
- Schema validation of the generated JSON output.
- Checks that all manual patches properly contain the `<thought>` and `<diff>` tags.
- Verifies that no JSON rows exceed standard context lengths.

**Common Failure Case:**
- *Malformed XML:* A manual fix might be missing the closing `</thought>` tag. The dataset builder will automatically reject this row and log an error.

---

## 4. Evaluation Benchmark Execution

This is the core scientific validation engine. It hits a local LLM API, sends an unseen AST, and algorithmically grades the output.

### 4a. Setup Local Llama Server
```bash
./llama-server -m models/architect-js-1.5b-unsloth.Q4_K_M.gguf -c 2048 --port 8080
```

### 4b. Run the Evaluator
```bash
node src/distiller/inference_test.js
```

### 4c. What the Evaluator Checks:
1. **Formatting Score:** Evaluates regex match for `<thought>` and `<diff>`.
2. **Conversational Filler Detection:** Strips the XML blocks. If the string length > 0 (e.g. the LLM said "Sure, here is the fix:"), the run fails.
3. **Hallucination Detection:** If the `<thought>` mentions a variable like `socketId` but the AST imports/exports/hooks only mention `roomId`, it fails the semantic check.
4. **Unified Diff Compilation Check:** Extracts the patch, applies it to the `.tsx` file via the system `patch` command, and runs `tsc --noEmit`. 

---

## 5. Performance Benchmarks

When evaluating the `Qwen2.5-Coder-1.5B` GGUF running on an RTX 3050 (4GB VRAM):

| Metric | Target Value | Pass/Fail Criteria |
| :--- | :--- | :--- |
| **Token Compression** | ~70-150 Tokens/AST | Average AST must not exceed 250 tokens |
| **Formatting Adherence** | 100% | Any conversational filler = Immediate Fail |
| **Hallucination Rate** | < 2% | Semantic AST mismatch |
| **Diff Application Rate**| > 90% | `patch` succeeds and `tsc` verifies syntax |
| **Inference Latency** | ~2-4s | Depends on VRAM offloading |

---

## 6. Debugging Steps

If `inference_test.js` fails:
1. **Check Failure Logs:** Look inside `logs/failures/`. The exact AST, Prompt, and Raw output are logged.
2. **Inspect Temperature:** Ensure the `llama-server` is queried with a low temperature (e.g., `0.1`) to ensure deterministic output.
3. **Update SFT Data:** If the model hallucinates formatting, add 5 more perfectly formatted examples to `manual_fixes.json`, rebuild `train.jsonl`, and run the Unsloth notebook again for 50 more steps.

---

> [!IMPORTANT]
> The TypeScript validation step requires `tsc` to be installed globally or via your local `node_modules`. If the `patch` command succeeds but the syntax is bad, the training data patches are structurally unsound. Do not scale dataset extraction until syntax validity hits >90%.
