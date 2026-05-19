import json
import networkx as nx
import argparse
from pathlib import Path

BASE_DATA_DIR = Path(__file__).parent.parent.parent / "datasets"
CHUNKS_DIR = BASE_DATA_DIR / "compressed_chunks"
GRAPH_DIR = BASE_DATA_DIR / "graph_memory"

def build_global_graph(repo_name: str):
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    json_path = CHUNKS_DIR / f"{repo_name}.json"
    
    if not json_path.exists():
        print(f"[-] Could not find AST chunks for {repo_name} at {json_path}")
        return
        
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    G = nx.DiGraph(repo_name=repo_name, repository=data.get("repository", ""))
    
    files = data.get("files", {})
    
    exports_map = {} 
    socket_emits = []
    socket_listens = []
    imports = []
    
    for file_path, nodes_dict in files.items():
        G.add_node(file_path, type="File", name=file_path)
        
        for node_id, node in nodes_dict.items():
            G.add_node(node_id, **node, file=file_path)
            G.add_edge(file_path, node_id, type="contains")
            
            for child_id in node.get("children", []):
                G.add_edge(node_id, child_id, type="contains")
                
            node_type = node.get("type")
            node_name = node.get("name")
            node_val = node.get("value")
            
            if node_type == "Export" and node_name:
                exports_map[node_name] = node_id
            elif node_type == "SocketEvent":
                if node_val == "emit":
                    socket_emits.append((node_id, node_name))
                elif node_val == "on":
                    socket_listens.append((node_id, node_name))
            elif node_type == "Import":
                specifiers = [s.strip() for s in str(node_val).split(",") if s.strip()]
                imports.append((node_id, node_name, specifiers))
            
            # Phase 1: Semantic Graph extraction enhancements
            elif node_type in ("FunctionDeclaration", "ArrowFunctionExpression", "Function") and node_name:
                if node_name.startswith("use"):
                    G.nodes[node_id]["semantic_type"] = "Hook"
            elif node_type == "ClassDeclaration":
                G.nodes[node_id]["semantic_type"] = "Class"
                if "schema" in (node_name or "").lower() or "model" in (node_name or "").lower():
                    G.nodes[node_id]["semantic_type"] = "DatabaseSchema"
            elif node_type == "CallExpression" and node_name in ("fetch", "axios", "request"):
                G.nodes[node_id]["semantic_type"] = "APIContract"
            elif node_type == "JSXElement" and node_name in ("Route", "Link"):
                G.nodes[node_id]["semantic_type"] = "Route"
                
    import_edges = 0
    for imp_node_id, source_file, specifiers in imports:
        for spec in specifiers:
            if spec in exports_map:
                target_node_id = exports_map[spec]
                G.add_edge(imp_node_id, target_node_id, type="imports_from")
                import_edges += 1
                
    socket_edges = 0
    for emit_id, emit_name in socket_emits:
        for listen_id, listen_name in socket_listens:
            if emit_name == listen_name:
                G.add_edge(emit_id, listen_id, type="socket_flow", event=emit_name)
                socket_edges += 1
                
    print(f"[+] Built global graph for {repo_name}")
    print(f"  -> Nodes: {G.number_of_nodes()}")
    print(f"  -> Edges: {G.number_of_edges()}")
    print(f"  -> Cross-File Import Edges: {import_edges}")
    print(f"  -> Cross-File Socket Flows: {socket_edges}")
    
    out_path = GRAPH_DIR / f"{repo_name}.gml"
    nx.write_gml(G, out_path)
    print(f"[+] Saved graph to {out_path}")
    return G

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("repo_name")
    args = parser.parse_args()
    build_global_graph(args.repo_name)
