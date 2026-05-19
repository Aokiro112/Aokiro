import os
import sys
import json
import subprocess
import argparse
import time
from pathlib import Path
import shutil

# Add core_engine to sys.path so we can import config
sys.path.append(str(Path(__file__).parent.parent.parent))
from core_engine.config import get_config

# Repositories are cloned here
BASE_DATA_DIR = Path(__file__).parent.parent.parent / "datasets"
CHUNKS_DIR = BASE_DATA_DIR / "compressed_chunks"
ALLOWED_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx"}
IGNORE_DIRS = {".git", "node_modules", "dist", "build", "coverage", ".next", ".cache"}

def setup_dirs():
    repos_dir = Path(get_config().data.repos_dir)
    repos_dir.mkdir(parents=True, exist_ok=True)
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    return repos_dir

def clone_repo(repo_url: str, repos_dir: Path) -> Path:
    repo_name = repo_url.split("/")[-1].replace(".git", "")
    target_dir = repos_dir / repo_name
    
    print(f"\n[REPO INGESTION]")
    print(f"Name: {repo_name}")
    print(f"Path: {target_dir.absolute()}")
    
    if target_dir.exists():
        print(f"[*] Repository already exists. Pulling latest updates...")
        try:
            subprocess.run(["git", "pull"], cwd=target_dir, check=True, capture_output=True)
            print(f"[+] Successfully updated {repo_name}")
        except subprocess.CalledProcessError as e:
            print(f"[-] Failed to update {repo_name}. Manual intervention required.")
        return target_dir

    print(f"[*] Cloning {repo_url}...")
    try:
        subprocess.run(["git", "clone", "--depth", "1", repo_url, str(target_dir)], check=True)
        print(f"[+] Successfully cloned {repo_name}")
    except subprocess.CalledProcessError as e:
        print(f"[-] Failed to clone {repo_url}: {e}")
        if target_dir.exists():
            print(f"[*] Cleaning up failed clone directory...")
            shutil.rmtree(target_dir, ignore_errors=True)
        sys.exit(1)
        
    return target_dir

def install_dependencies(repo_dir: Path):
    print(f"[*] Checking dependencies in {repo_dir}...")
    if (repo_dir / "package-lock.json").exists():
        print("[*] Found package-lock.json. Running npm install --force...")
        subprocess.run(["npm", "install", "--force"], cwd=repo_dir, capture_output=True)
    elif (repo_dir / "yarn.lock").exists():
        print("[*] Found yarn.lock. Running yarn install...")
        subprocess.run(["yarn", "install"], cwd=repo_dir, capture_output=True)
    elif (repo_dir / "pnpm-lock.yaml").exists():
        print("[*] Found pnpm-lock.yaml. Running pnpm install...")
        subprocess.run(["pnpm", "install"], cwd=repo_dir, capture_output=True)
    else:
        print("[!] No lockfile found. Skipping dependency installation.")

def run_ast_compressor(file_path: Path) -> dict:
    # Path to the JS compressor script
    compressor_script = Path(__file__).parent.parent / "analyzer" / "ast_compressor.js"
    
    try:
        result = subprocess.run(
            ["node", str(compressor_script), str(file_path)],
            capture_output=True,
            text=True
        )
        
        # ast_compressor.js prints the JSON to stdout, and logs success to stderr
        if result.returncode != 0:
            return {}
            
        stdout = result.stdout.strip()
        if not stdout:
            return {}
            
        data = json.loads(stdout)
        return data
    except Exception as e:
        print(f"[-] Error parsing {file_path}: {e}")
        return {}

def process_repository(repo_url: str, skip_install: bool = False):
    repos_dir = setup_dirs()
    repo_dir = clone_repo(repo_url, repos_dir)
    repo_name = repo_dir.name
    
    if not skip_install:
        install_dependencies(repo_dir)
        
    print(f"[*] Scanning {repo_name} for source files...")
    aggregated_ast = {
        "repository": repo_url,
        "name": repo_name,
        "files": {}
    }
    
    file_count = 0
    start_time = time.time()
    
    for root, dirs, files in os.walk(repo_dir):
        # Exclude ignored directories
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        
        for file in files:
            path = Path(root) / file
            if path.suffix in ALLOWED_EXTENSIONS:
                relative_path = path.relative_to(repo_dir).as_posix()
                print(f"  -> Parsing: {relative_path}")
                
                nodes = run_ast_compressor(path)
                if nodes:
                    aggregated_ast["files"][relative_path] = nodes
                    file_count += 1

    elapsed = time.time() - start_time
    print(f"\n[+] Extracted {file_count} files in {elapsed:.2f} seconds.")
    
    out_file = CHUNKS_DIR / f"{repo_name}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(aggregated_ast, f, indent=2)
        
    print(f"[+] Saved compressed ASTs to {out_file}")
    
    # Phase 1: Call semantic graph builder
    try:
        from src.miner.global_graph import build_global_graph
        build_global_graph(repo_name)
    except ImportError as e:
        print(f"[-] Could not import global_graph: {e}")
        
    return out_file

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aokiro Repository Processor")
    parser.add_argument("repo_url", help="GitHub repository URL")
    parser.add_argument("--skip-install", action="store_true", help="Skip npm/yarn install")
    
    args = parser.parse_args()
    process_repository(args.repo_url, skip_install=args.skip_install)
