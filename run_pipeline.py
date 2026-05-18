import json
import networkx as nx
from extractor.git_processor import clone_and_get_commits
from extractor.ast_parser import extract_imports_from_code

def generate_repo_graph_history(repo_url):
    # 1. Clone the repo and get all its chronological commits
    repo, commits = clone_and_get_commits(repo_url)
    
    history_snapshots = []

    # 2. Loop through each commit in the timeline
    for commit in commits:
        print(f"Processing commit: {commit.hexsha[:7]} - {commit.summary}")
        
        # Checkout the repository files at this exact point in time
        repo.git.checkout(commit.hexsha)
        
        # Initialize a clean NetworkX Graph for this commit snapshot
        G = nx.DiGraph()
        
        # Look through all files in the repo at this commit state
        for root, dirs, files in os.walk("./temp_repo"):
            # Skip virtual environments or git hidden folders
            if 'venv' in root or '.git' in root:
                continue
                
            for file in files:
                if file.endswith(".py"):
                    file_path = os.path.join(root, file)
                    relative_module_name = file.replace(".py", "")
                    
                    # Read file content safely
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read()
                        
                        # Extract what this file imports
                        dependencies = extract_imports_from_code(content)
                        
                        # Add node and connections (edges) to our graph
                        G.add_node(relative_module_name)
                        for dep in dependencies:
                            G.add_edge(relative_module_name, dep)
                    except Exception:
                        pass # Skip files that can't be read safely

        # 3. Convert NetworkX graph into the exact JSON format Member 2 & 3 need
        graph_data = nx.node_link_data(G)
        
        snapshot = {
            "commit_sha": commit.hexsha,
            "author": commit.author.name,
            "message": commit.summary,
            "date": commit.authored_datetime.isoformat(),
            "graph": {
                "nodes": graph_data.get("nodes", []),
                "edges": graph_data.get("links", []) # NetworkX exports edges as 'links'
            }
        }
        history_snapshots.append(snapshot)
        
    # Reset git branch back to main safely
    repo.git.checkout('main')
    
    # Save the ultimate snapshot history to a JSON file for the team
    with open("repo_history_graph.json", "w") as out_file:
        json.dump(history_snapshots, out_file, indent=2)
        
    print("✨ Pipeline Complete! 'repo_history_graph.json' generated successfully.")

# Example usage (You can replace this with any public Python repo link)
if __name__ == "__main__":
    import os
    generate_repo_graph_history("https://github.com/psf/requests")