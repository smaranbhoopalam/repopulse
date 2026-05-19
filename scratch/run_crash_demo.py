import sys
import os
import json

# Add the driftguard-backend directory to the python path to import app.crash.detector
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'driftguard-backend')))

# pyrefly: ignore [missing-import]
from app.crash.detector import CrashDetector

def main():
    detector = CrashDetector()

    # Mock a healthy history of 3 commits
    history = [
        {
            "health_score": 90.0,
            "cyclomatic_complexity": 1.2,
            "test_coverage": 85.0,
            "architectural_violations": 0
        },
        {
            "health_score": 88.5,
            "cyclomatic_complexity": 1.2,
            "test_coverage": 85.0,
            "architectural_violations": 0
        },
        {
            "health_score": 88.0,
            "cyclomatic_complexity": 1.3,
            "test_coverage": 84.5,
            "architectural_violations": 0
        }
    ]

    # Mock the latest commit which has a catastrophic crash!
    latest_metrics = {
        "health_score": 65.0,                  # Huge drop!
        "cyclomatic_complexity": 2.5,          # Spike > 40%!
        "test_coverage": 65.0,                 # Drop > 15%!
        "architectural_violations": 4          # Surge >= 3!
    }

    print("Analyzing Crash...")
    result = detector.analyze_commit_history(history, latest_metrics)
    
    print(json.dumps(result, indent=4))

if __name__ == "__main__":
    main()
