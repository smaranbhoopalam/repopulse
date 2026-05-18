from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
import os
from repo_parser.git_handler import clone_repository, get_commits, checkout_commit
from graph_engine.builder import build_dependency_graph
from utils.file_utils import DATA_DIR, save_json, load_json, cleanup_temp_dir

router = APIRouter()

class AnalyzeRequest(BaseModel):
    repo_url: str
    
def process_repository(repo_url: str):
    print(f"Starting multi-language analysis for {repo_url}")
    target_dir = None
    repo = None
    try:
        target_dir, repo = clone_repository(repo_url)
        commits = get_commits(repo, max_commits=5, step=1)
        
        save_json(os.path.join(DATA_DIR, "commits.json"), commits)
        
        for commit in commits:
            commit_id = commit['commit_id']
            checkout_commit(repo, commit_id)
            
            graph_data = build_dependency_graph(target_dir)
            language_summary = graph_data.pop("language_summary", {})
            
            snapshot = {
                "commit_id": commit_id,
                "timestamp": commit['timestamp'],
                "language_summary": language_summary,
                "graph": graph_data
            }
            save_json(os.path.join(DATA_DIR, f"{commit_id}.json"), snapshot)
            print(f"Processed commit {commit_id}")
            
    except Exception as e:
        print(f"Error processing repository: {e}")
    finally:
        if repo:
            repo.close()
        if target_dir:
            cleanup_temp_dir(target_dir)

@router.get("/health")
def health_check():
    return {"status": "ok"}

@router.post("/analyze")
def analyze_repo(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(process_repository, request.repo_url)
    return {"message": "analysis started"}

@router.get("/commits")
def get_all_commits():
    commits_file = os.path.join(DATA_DIR, "commits.json")
    commits = load_json(commits_file)
    if not commits:
        return []
    return commits

@router.get("/graph/{commit_id}")
def get_graph(commit_id: str):
    graph_file = os.path.join(DATA_DIR, f"{commit_id}.json")
    graph_data = load_json(graph_file)
    if not graph_data:
        return {"error": "Graph not found for this commit"}
    return graph_data
