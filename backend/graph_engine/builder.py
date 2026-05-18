import os
import networkx as nx
from parsers.parser_manager import parse_file, EXTENSION_MAP

def find_source_files(repo_path):
    src_files = []
    exclude_dirs = {'.git', 'venv', 'env', 'node_modules', 'build', 'dist', '__pycache__'}
    valid_exts = set(EXTENSION_MAP.keys())
    
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in valid_exts:
                src_files.append(os.path.join(root, file))
    return src_files

def get_module_name(repo_path, file_path):
    rel_path = os.path.relpath(file_path, repo_path)
    rel_path = rel_path.replace("\\", "/")
    path_no_ext = os.path.splitext(rel_path)[0]
    return rel_path, path_no_ext

def build_dependency_graph(repo_path):
    src_files = find_source_files(repo_path)
    module_to_file = {}
    language_summary = {}
    
    # Pre-compute module mappings
    for f in src_files:
        rel_path, path_no_ext = get_module_name(repo_path, f)
        module_to_file[rel_path] = rel_path
        module_to_file[path_no_ext] = rel_path
        
        # Python specific module mapping
        if rel_path.endswith('.py'):
            py_mod = path_no_ext.replace('/', '.')
            module_to_file[py_mod] = rel_path
            if py_mod.endswith('.__init__'):
                module_to_file[py_mod[:-9]] = rel_path
                
        # Base name fallback mapping for loose resolution
        base_name = os.path.basename(path_no_ext)
        if base_name not in module_to_file:
            module_to_file[base_name] = rel_path
            
    G = nx.DiGraph()
    
    # Create all nodes
    for f in src_files:
        rel_path, _ = get_module_name(repo_path, f)
        G.add_node(rel_path)
        
    # Extract imports and build edges
    for f in src_files:
        rel_path, _ = get_module_name(repo_path, f)
        lang, imports = parse_file(f)
        
        if lang:
            language_summary[lang] = language_summary.get(lang, 0) + 1
            
        for imp in imports:
            clean_imp = imp.replace('./', '').replace('../', '')
            
            # Exact match via mapped aliases
            if clean_imp in module_to_file:
                target_file = module_to_file[clean_imp]
                if rel_path != target_file:
                    G.add_edge(rel_path, target_file)
            else:
                # Loose base name match
                base_imp = os.path.basename(clean_imp)
                if base_imp in module_to_file:
                    target_file = module_to_file[base_imp]
                    if rel_path != target_file:
                        G.add_edge(rel_path, target_file)

    nodes = [{"id": n} for n in G.nodes()]
    edges = [{"source": u, "target": v} for u, v in G.edges()]
    
    return {
        "nodes": nodes,
        "edges": edges,
        "language_summary": language_summary
    }
