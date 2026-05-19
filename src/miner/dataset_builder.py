import sys
import json
import networkx as nx
import argparse
from pathlib import Path

# Add core_engine to sys.path so we can import llm_client
sys.path.append(str(Path(__file__).parent.parent.parent))
from core_engine.llm_client import LLMClient

BASE_DATA_DIR = Path(__file__).parent.parent.parent / "datasets"
GRAPH_DIR = BASE_DATA_DIR / "graph_memory"
TRAIN_DIR = BASE_DATA_DIR / "training_pairs"

def get_subgraph_context(G, center_node, radius=2):
    """Extract a small subgraph around a center node to serve as context."""
    # Use ego_graph to get neighbors up to 'radius' hops
    sub_g = nx.ego_graph(G, center_node, radius=radius, undirected=False)
    
    # Serialize to a lightweight JSON for the LLM
    nodes_data = []
    for n, attr in sub_g.nodes(data=True):
        if n != center_node:
            # Drop heavy attributes for neighbors to save tokens
            nodes_data.append({"id": n, "type": attr.get("type"), "name": attr.get("name")})
        else:
            nodes_data.append({"id": n, **attr})
            
    edges_data = []
    for u, v, attr in sub_g.edges(data=True):
        edges_data.append({"source": u, "target": v, "type": attr.get("type", "")})
        
    return json.dumps({"focus_node": center_node, "nodes": nodes_data, "edges": edges_data})

def generate_qlora_pairs(repo_name: str, max_pairs: int = 20):
    TRAIN_DIR.mkdir(parents=True, exist_ok=True)
    out_file = TRAIN_DIR / "train_architect.jsonl"
    
    graph_path = GRAPH_DIR / f"{repo_name}.gml"
    if not graph_path.exists():
        print(f"[-] Graph not found at {graph_path}")
        return
        
    G = nx.read_gml(graph_path)
    client = LLMClient()
    
    if not client.is_alive():
        print("[-] llama-server is not running. Cannot generate LLM summaries. Start it on port 8080.")
        return

    # Find interesting nodes to query: Components and Global Sockets
    interesting_nodes = []
    for n, attr in G.nodes(data=True):
        ntype = attr.get("type")
        if ntype in ("Component", "SocketEvent"):
            interesting_nodes.append(n)
            
    print(f"[*] Found {len(interesting_nodes)} interesting nodes. Generating up to {max_pairs} pairs...")
    
    count = 0
    generated = 0
    
    # We will use an array of specific instruction prompts
    task_types = [
        "You are an AI Architect. Analyze this AST subgraph. Your task is to output a minimal, deterministic code patch that refactors this node safely for better performance. Output ONLY the minimal patch.",
        "You are an AI Architect. Find a potential bug in this AST subgraph and generate a minimal safe patch to fix it. Ensure the patch is TypeScript-safe. Output ONLY the minimal patch.",
        "You are an AI Architect. Analyze this AST subgraph. Generate a dependency-aware modification that adds proper error handling to this node. Do not hallucinate imports. Output ONLY the minimal patch.",
        "You are an AI Architect. Modify this node to integrate with a standard REST API using fetch. Output a deterministic, architecture-consistent patch without rewriting the entire file."
    ]
    
    with open(out_file, "a", encoding="utf-8") as f:
        for idx, node in enumerate(interesting_nodes):
            instruction = task_types[idx % len(task_types)]
            if generated >= max_pairs:
                break
                
            context = get_subgraph_context(G, node, radius=1)
            
            # Simple skip if context is too small (e.g., a disconnected node)
            if len(json.loads(context)["nodes"]) <= 1:
                continue
                
            prompt = f"Architecture Context (AST Subgraph):\n{context}\n\nTask: {instruction}"
            
            try:
                # We use generic completion with a system prompt
                sys_prompt = "You are an expert software architect. You output clean, production-grade, deterministic code patches. No hallucinations. Output only the patch."
                res = client.complete(user_message=prompt, system_prompt=sys_prompt, temperature=0.2, max_tokens=300)
                
                output_text = res.content.strip()
                if output_text:
                    row = {
                        "instruction": instruction,
                        "input": context,
                        "output": output_text,
                        "repo": repo_name,
                        "focus_node": node
                    }
                    f.write(json.dumps(row) + "\n")
                    generated += 1
                    print(f"  -> Generated pair {generated}/{max_pairs} for {node}")
            except Exception as e:
                print(f"  [-] Error generating for {node}: {e}")
                
            count += 1
            
    print(f"[+] Saved {generated} new training pairs to {out_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("repo_name")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    generate_qlora_pairs(args.repo_name, args.limit)
