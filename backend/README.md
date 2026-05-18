# RepoPulse Backend

Backend engine for the RepoPulse hackathon project. Responsible for ingesting Git repositories, traversing commits, extracting Python dependencies, and exporting dependency graphs as JSON.

## Setup

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the server:
   ```bash
   uvicorn main:app --reload
   ```

## API Usage

1. **Check Health**
   ```bash
   curl http://localhost:8000/health
   ```
   
2. **Start Analysis**
   ```bash
   curl -X POST http://localhost:8000/analyze \
        -H "Content-Type: application/json" \
        -d '{"repo_url": "https://github.com/pallets/flask"}'
   ```
   *Note: This runs in the background. It will clone the repository, process the latest commits, and generate snapshots in the `data/` folder.*

3. **List Processed Commits**
   ```bash
   curl http://localhost:8000/commits
   ```

4. **Get Graph Snapshot for a Commit**
   ```bash
   curl http://localhost:8000/graph/{commit_id}
   ```
