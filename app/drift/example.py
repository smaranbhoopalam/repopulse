"""
Example Usage of the Architectural Drift Detector
"""

import json
import networkx as nx
from app.drift.detector import DriftDetector

def run_example():
    # 1. Define high-risk pattern configuration
    # E.g., we don't want "ui" directly importing "db"
    high_risk_patterns = [
        ("ui", "db"),
        ("frontend", "backend/core")
    ]
    detector = DriftDetector(high_risk_patterns=high_risk_patterns)

    # 2. Build Previous Graph
    prev_graph = nx.DiGraph()
    prev_graph.add_edges_from([
        ("app/ui.py", "app/api.py"),
        ("app/api.py", "app/db.py"),
        ("app/auth.py", "app/db.py")
    ])

    # 3. Build Current Graph (Introducing architectural drift)
    curr_graph = prev_graph.copy()
    
    # Drift A: High Risk Edge Addition
    curr_graph.add_edge("app/ui.py", "app/db.py")
    
    # Drift B: New Circular Dependency
    curr_graph.add_edge("app/db.py", "app/auth.py")

    # Drift C: Dependency Explosion
    # app/api.py suddenly imports many new files
    curr_graph.add_edges_from([(f"app/module_{i}.py", "app/api.py") for i in range(5)])

    # 4. Detect Drift
    report = detector.detect_drift(prev_graph, curr_graph)

    # 5. Output Results
    print(json.dumps(report, indent=4))

if __name__ == "__main__":
    run_example()
