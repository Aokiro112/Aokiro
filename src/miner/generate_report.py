import json
import networkx as nx
from pathlib import Path

BASE_DATA_DIR = Path(__file__).parent.parent.parent / "datasets"
GRAPH_DIR = BASE_DATA_DIR / "graph_memory"
TRAIN_DIR = BASE_DATA_DIR / "training_pairs"
DOCS_DIR = Path(__file__).parent.parent.parent / "docs"

def generate_report():
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    out_file = DOCS_DIR / "architecture_coverage_report.md"
    
    total_graphs = 0
    total_nodes = 0
    total_edges = 0
    
    graph_stats = []
    
    if GRAPH_DIR.exists():
        for gml_file in GRAPH_DIR.glob("*.gml"):
            G = nx.read_gml(gml_file)
            n = G.number_of_nodes()
            e = G.number_of_edges()
            total_nodes += n
            total_edges += e
            total_graphs += 1
            
            socket_flows = len([1 for u, v, attr in G.edges(data=True) if attr.get("type") == "socket_flow"])
            import_flows = len([1 for u, v, attr in G.edges(data=True) if attr.get("type") == "imports_from"])
            
            graph_stats.append({
                "repo": gml_file.stem,
                "nodes": n,
                "edges": e,
                "sockets": socket_flows,
                "imports": import_flows
            })
            
    train_file = TRAIN_DIR / "train_architect.jsonl"
    train_pairs = 0
    if train_file.exists():
        with open(train_file, "r") as f:
            train_pairs = sum(1 for line in f)
            
    report = f"""# Aokiro Dataset Coverage & Architecture Report

## Overview
This report details the datasets generated during the **DATASET MINING + TRAINING phase**.

## Global Statistics
- **Total Repositories Processed:** {total_graphs}
- **Total Architectural Nodes Extracted:** {total_nodes}
- **Total Architectural Edges Mapped:** {total_edges}
- **Total QLoRA Instruction Pairs:** {train_pairs}

## Repository Breakdown
"""
    for stat in graph_stats:
        report += f"""
### {stat['repo']}
- Nodes: {stat['nodes']}
- Total Edges: {stat['edges']}
- Cross-File Imports Resolved: {stat['imports']}
- Cross-File Socket Flows Mapped: {stat['sockets']}
"""
    
    report += """
## Limitations & Future Scaling Paths
- **Memory Footprint**: Extremely large monorepos (>5,000 files) will produce massively dense graphs, causing `NetworkX` traversal to bottleneck.
- **Dynamic Routing**: Express/Next.js routes mapped as strings (e.g., `app.use('/api', router)`) require more complex Regex pattern matching to build explicit cross-file route edges.
- **LLM Summary Speed**: Generating 10,000 architectural summaries locally on a 7B model will take considerable time (estimated ~10-20 seconds per summary). Batching or cloud-offloading during dataset creation may be required for V3.
"""
    
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(report)
        
    print(f"[+] Coverage report generated at {out_file}")
    
    # Append to README.md
    readme_path = Path(__file__).parent.parent.parent / "README.md"
    if readme_path.exists():
        with open(readme_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n## 📊 Automated Dataset Mining Metrics\n")
            f.write(f"- Repositories Processed: {total_graphs}\n")
            f.write(f"- Nodes Extracted: {total_nodes}\n")
            f.write(f"- Cross-File Edges Mapped: {total_edges}\n")
        print("[+] Updated README.md with metrics.")

if __name__ == "__main__":
    generate_report()
