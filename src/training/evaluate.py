import os
import json
import subprocess
import tempfile
from typing import List, Dict

def evaluate_patch_minimality(original: str, patch: str) -> float:
    # A simple minimality score: ratio of patch length to original length
    # A lower score is better, but we cap it and convert to a 0-100 score
    if not original:
        return 0.0
    ratio = len(patch) / len(original)
    if ratio > 1.0:
        return 0.0
    return (1.0 - ratio) * 100

def evaluate_compile_success(patch: str) -> bool:
    """
    Test if the patch parses correctly and passes basic TS checks.
    We write to a temp file and run tsc --noEmit.
    """
    with tempfile.NamedTemporaryFile(suffix=".tsx", delete=False) as tmp:
        tmp.write(patch.encode('utf-8'))
        tmp_path = tmp.name

    try:
        # We run tsc --noEmit on the file. If it has syntax errors, it will fail.
        # It may also fail on missing imports, which is a good test for dependency correctness.
        result = subprocess.run(["npx", "tsc", "--noEmit", "--skipLibCheck", tmp_path], capture_output=True, text=True)
        return result.returncode == 0
    except Exception as e:
        print(f"Error running tsc: {e}")
        return False
    finally:
        os.remove(tmp_path)

def run_evaluation(test_file: str):
    if not os.path.exists(test_file):
        print(f"[-] Test file not found: {test_file}")
        return

    print(f"[*] Starting Evaluation on {test_file}")
    with open(test_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    total = len(lines)
    if total == 0:
        print("[-] No test cases found.")
        return

    compile_success_count = 0
    total_minimality = 0.0

    for idx, line in enumerate(lines):
        try:
            data = json.loads(line)
            patch = data.get("output", "")
            original = data.get("input", "")

            # 1. Compile Success
            is_valid = evaluate_compile_success(patch)
            if is_valid:
                compile_success_count += 1

            # 2. Patch Minimality
            minimality = evaluate_patch_minimality(original, patch)
            total_minimality += minimality

        except Exception as e:
            print(f"  [-] Error evaluating row {idx}: {e}")

    compile_success_rate = (compile_success_count / total) * 100
    avg_minimality = total_minimality / total

    print("\n=== EVALUATION RESULTS ===")
    print(f"Total Cases: {total}")
    print(f"Compile Success Rate: {compile_success_rate:.2f}%")
    print(f"Average Patch Minimality: {avg_minimality:.2f}% (higher means smaller patches)")
    
    # Save results
    results = {
        "total_cases": total,
        "compile_success_rate": compile_success_rate,
        "average_patch_minimality": avg_minimality
    }
    
    os.makedirs("outputs", exist_ok=True)
    with open("outputs/eval_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("[+] Saved evaluation results to outputs/eval_results.json")

if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    sys.path.append(str(Path(__file__).parent.parent.parent))
    from core_engine.config import get_config
    
    cfg = get_config()
    run_evaluation(cfg.data.unseen_test_file)
