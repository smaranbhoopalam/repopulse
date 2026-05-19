import math
from typing import List, Dict, Any

class CrashDetector:
    def analyze_commit_history(self, history: List[Dict[str, Any]], latest_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyzes the latest commit metrics against historical data to detect crashes.
        """
        latest_score = float(latest_metrics.get("health_score", 0.0))
        
        # If absolutely no history, we can't calculate drops
        if not history:
            return self._build_response(False, "NONE", "NONE", 0.0, 0.0, latest_score, {}, "LOW")

        historical_scores = [float(c.get("health_score", 0.0)) for c in history]
        hist_avg_score = sum(historical_scores) / len(historical_scores)
        
        prev_commit = history[-1]
        prev_score = float(prev_commit.get("health_score", 0.0))
        score_drop = prev_score - latest_score
        
        # Layer 1 & 4: Statistical Outlier Evaluation & Graceful Degradation
        z_score = 0.0
        z_anomaly = False
        
        if len(history) < 3:
            # Layer 4 Fallback: Absolute threshold check
            z_anomaly = score_drop > 15.0
        else:
            # Calculate mean (μ) and sample stddev (σ) of historical drops in health score
            drops = []
            for i in range(1, len(history)):
                drops.append(float(history[i-1].get("health_score", 0.0)) - float(history[i].get("health_score", 0.0)))
                
            mu = sum(drops) / len(drops)
            variance = sum((x - mu) ** 2 for x in drops) / (len(drops) - 1) if len(drops) > 1 else 0.0
            sigma = math.sqrt(variance)
            
            if sigma > 0:
                z_score = (score_drop - mu) / sigma
            else:
                z_score = 0.0
                if score_drop > 15.0:
                    z_score = 3.0 # Synthetic z-score for zero-variance fallback
                    
            z_anomaly = z_score > 2.0
            
        # Layer 2: Micro-Metric Trigger Safeguards
        prev_complexity = float(prev_commit.get("cyclomatic_complexity", 1.0))
        latest_complexity = float(latest_metrics.get("cyclomatic_complexity", prev_complexity))
        safe_prev_comp = prev_complexity if prev_complexity > 0 else 1.0
        complexity_spike = ((latest_complexity - safe_prev_comp) / safe_prev_comp) > 0.40
        
        prev_coverage = float(prev_commit.get("test_coverage", 0.0))
        latest_coverage = float(latest_metrics.get("test_coverage", prev_coverage))
        coverage_collapse = (prev_coverage - latest_coverage) > 15.0
        
        prev_violations = int(prev_commit.get("architectural_violations", 0))
        latest_violations = int(latest_metrics.get("architectural_violations", prev_violations))
        violation_surge = (latest_violations - prev_violations) >= 3
        
        triggers = {
            "statistical_anomaly": z_anomaly,
            "complexity_spike": complexity_spike,
            "coverage_collapse": coverage_collapse,
            "violation_surge": violation_surge
        }
        
        # Layer 3: Risk Vector & Severity Classification
        crash_detected = any(triggers.values())
        
        crash_type = "NONE"
        if crash_detected:
            if triggers["violation_surge"]:
                crash_type = "ARCHITECTURAL"
            elif triggers["complexity_spike"] or triggers["coverage_collapse"]:
                crash_type = "MAINTAINABILITY"
            else:
                crash_type = "VOLATILITY"
                
        severity = "NONE"
        if crash_detected:
            num_triggers = sum(1 for v in triggers.values() if v)
            if z_score > 3.0 or num_triggers >= 2 or (len(history) < 3 and score_drop > 25.0):
                severity = "CRITICAL"
            else:
                severity = "WARNING"
                
        mitigation_priority = "LOW"
        if crash_detected:
            mitigation_priority = "HIGH" if severity == "CRITICAL" else "MEDIUM"
            
        return self._build_response(
            crash_detected, crash_type, severity, score_drop, z_score, hist_avg_score, triggers, mitigation_priority
        )

    def _build_response(self, crash_detected: bool, crash_type: str, severity: str, 
                        score_drop: float, z_score: float, hist_avg_score: float, 
                        triggers: Dict[str, bool], mitigation_priority: str) -> Dict[str, Any]:
        if not triggers:
            triggers = {
                "statistical_anomaly": False,
                "complexity_spike": False,
                "coverage_collapse": False,
                "violation_surge": False
            }
            
        return {
            "crash_detected": crash_detected,
            "crash_type": crash_type,
            "severity": severity,
            "statistical_summary": {
                "score_drop": float(round(score_drop, 2)),
                "z_score": float(round(z_score, 2)),
                "historical_average_score": float(round(hist_avg_score, 2))
            },
            "triggered_by": triggers,
            "mitigation_priority": mitigation_priority
        }
