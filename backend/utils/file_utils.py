import os
import json
import shutil
import stat

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
TEMP_DIR = os.path.join(os.path.dirname(__file__), "..", "temp_repos")

def init_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)

def save_json(file_path, data):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def load_json(file_path):
    if not os.path.exists(file_path):
        return None
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def cleanup_temp_dir(repo_dir):
    if os.path.exists(repo_dir):
        def onerror(func, path, exc_info):
            if not os.access(path, os.W_OK):
                os.chmod(path, stat.S_IWUSR)
                func(path)
        try:
            shutil.rmtree(repo_dir, onerror=onerror)
        except Exception as e:
            print(f"Error cleaning up temp dir: {e}")
