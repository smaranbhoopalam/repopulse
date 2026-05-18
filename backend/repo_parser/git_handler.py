import os
from git import Repo
import uuid
from utils.file_utils import TEMP_DIR

def clone_repository(repo_url):
    repo_id = str(uuid.uuid4())
    target_dir = os.path.join(TEMP_DIR, repo_id)
    repo = Repo.clone_from(repo_url, target_dir)
    return target_dir, repo

def get_commits(repo, max_commits=10, step=1):
    try:
        commits = list(repo.iter_commits(max_count=max_commits * step))
    except Exception as e:
        print(f"Error fetching commits: {e}")
        return []
        
    sampled_commits = []
    for i in range(0, len(commits), step):
        c = commits[i]
        sampled_commits.append({
            "commit_id": c.hexsha,
            "author": c.author.name,
            "timestamp": c.committed_datetime.isoformat(),
            "message": c.message.strip()
        })
        if len(sampled_commits) == max_commits:
            break
    return sampled_commits

def checkout_commit(repo, commit_id):
    repo.git.checkout(commit_id)
