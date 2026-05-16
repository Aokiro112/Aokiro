import os
import json
import subprocess
import shutil
import tempfile
from pydriller import Repository

# Phase 6: Real-World Mined Dataset Pipeline
# Unmocked PyDriller integration with strict architecture signal scoring

TRUSTED_ECOSYSTEMS = [
    "facebook/react",
    "vercel/next.js",
    "TanStack/query",
    "remix-run/react-router"
]

IGNORE_WORDS = ["docs", "chore", "bump", "dependency", "lockfile", "format", "rename"]
PRIORITY_WORDS = ["hook", "refactor", "perf", "state", "render", "cleanup", "async"]

def calculate_trust_score(repo_url):
    score = 100
    if "facebook" in repo_url or "vercel" in repo_url:
        score += 20
    return score

def get_architecture_score(commit_msg, diff):
    score = 0
    msg = commit_msg.lower()
    for word in PRIORITY_WORDS:
        if word in msg:
            score += 10
            
    if "useEffect" in diff or "useState" in diff or "useMemo" in diff:
        score += 20
        
    return score

def run_node_script(script_path, arg):
    try:
        # Run node script, return stdout and handle errors
        result = subprocess.run(['node', script_path, arg], capture_output=True, text=True, check=False)
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return False, "", str(e)

def process_commit(commit, repo_url, batch_results):
    msg = commit.msg.lower()
    
    # 1. Filter noisy commits
    if any(word in msg for word in IGNORE_WORDS):
        return
        
    if "fix" not in msg and "refactor" not in msg and "perf" not in msg:
        return
        
    # Multi-file limit (do not accept massive repo-wide refactors)
    if len(commit.modified_files) > 5:
        return

    trust_score = calculate_trust_score(repo_url)

    for mod in commit.modified_files:
        if not mod.filename.endswith(('.tsx', '.ts', '.jsx', '.js')):
            continue
            
        # We need both before and after states
        if mod.source_code_before is None or mod.source_code is None:
            continue
            
        arch_score = get_architecture_score(msg, mod.diff)
        if arch_score < 10:
            continue # Too trivial

        # Disk Isolation: Write to temp files
        with tempfile.TemporaryDirectory() as tmpdir:
            before_path = os.path.join(tmpdir, "before.tsx")
            after_path = os.path.join(tmpdir, "after.tsx")
            
            with open(before_path, "w", encoding="utf-8") as f:
                f.write(mod.source_code_before)
            with open(after_path, "w", encoding="utf-8") as f:
                f.write(mod.source_code)
                
            # Tier 1 Validation: Babel parse on the AFTER code
            valid_syntax, _, _ = run_node_script("src/analyzer/babel_validator.js", after_path)
            if not valid_syntax:
                continue
                
            # AST Extraction
            success, ast_json_str, err = run_node_script("src/analyzer/ast_compressor.js", before_path)
            if not success or "Token count" not in err:
                continue
                
            # Success! Format the row.
            thought = f"Real-world fix extracted from commit {commit.hash}."
            diff_payload = mod.diff
            
            row = {
                "repo": repo_url,
                "commit": commit.hash,
                "file": mod.filename,
                "trust_score": trust_score,
                "arch_score": arch_score,
                "input": ast_json_str,
                "output": f"<thought>\n{thought}\n</thought>\n<diff>\n{diff_payload}\n</diff>"
            }
            batch_results.append(row)
            print(f"[ACCEPTED] {commit.hash} - {mod.filename} (Score: {arch_score})")

def mine_repository(repo_url, max_commits=50):
    print(f"\n--- Mining repository: {repo_url} ---")
    batch_results = []
    
    # We use limit to avoid cloning the entirety of massive histories locally during testing
    # shallow clone via PyDriller limits history traversal
    try:
        repo = Repository("https://github.com/" + repo_url, order='reverse')
        count = 0
        for commit in repo.traverse_commits():
            process_commit(commit, repo_url, batch_results)
            count += 1
            if count >= max_commits or len(batch_results) >= 20:
                break
    except Exception as e:
        print(f"Error traversing {repo_url}: {e}")
        
    return batch_results

def run_large_scale_extraction():
    all_results = []
    for repo in TRUSTED_ECOSYSTEMS:
        results = mine_repository(repo)
        all_results.extend(results)
        
    print(f"\n=== EXTRACTION COMPLETE ===")
    print(f"Total Validated Rows: {len(all_results)}")
    
    os.makedirs("../../datasets/v2_mined", exist_ok=True)
    out_file = "../../datasets/v2_mined/batch_001.json"
    with open(out_file, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"Saved to {out_file}")

if __name__ == "__main__":
    run_large_scale_extraction()
