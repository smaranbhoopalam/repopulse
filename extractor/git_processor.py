import os
import ast
from git import Repo

def clone_and_get_commits(repo_url, local_path="./temp_repo"):
    """
    Clones a remote GitHub repository and returns a list of commit hashes.
    """
    # If the repository is already cloned, open it. Otherwise, clone it.
    if os.path.exists(local_path):
        print(f"Repository already exists at {local_path}. Opening...")
        repo = Repo(local_path)
    else:
        print(f"Cloning repository from {repo_url}...")
        repo = Repo.clone_from(repo_url, local_path)
    
    # Get all commits in the history (from oldest to newest)
    commits = list(repo.iter_commits('main'))  # or 'master' depending on the repo
    commits.reverse()  # Reverse so we process chronologically
    
    print(f"Successfully loaded {len(commits)} commits.")
    return repo, commits



def extract_imports_from_code(file_content):
    """
    Parses Python source code and extracts all imported module names.
    """
    imports = []
    try:
        # Parse the code text into an Abstract Syntax Tree (AST)
        tree = ast.parse(file_content)
        
        # Walk through every single element inside the code tree
        for node in ast.walk(tree):
            # Check for standard imports like: import os
            if isinstance(node, ast.Import):
                for name in node.names:
                    imports.append(name.name)
            # Check for from-imports like: from git import Repo
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
    except SyntaxError:
        # If a file has broken syntax at an old commit, skip it safely
        pass
        
    return imports