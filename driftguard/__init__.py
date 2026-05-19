"""
DriftGuard — AI-assisted Repository Health Intelligence Platform.

Tracks how software architecture evolves, degrades, and drifts away from
developer intent over time by analyzing repository dependency graphs
commit-by-commit using graph intelligence and temporal analysis.
"""

from driftguard.engines.health import HealthScoreEngine, ArchitectureMetrics
from driftguard.engines.vision import VisionRuleEngine
from driftguard.engines.drift import DriftEngine, DriftReport
from driftguard.engines.complexity import ComplexityEngine, ComplexityMetrics
from driftguard.engines.dependency import DependencyEngine, DependencyMetrics
from driftguard.engines.evolution import EvolutionEngine, EvolutionMetrics
from driftguard.engines.team import TeamEngine, TeamMetrics
from driftguard.engines.testing import TestingEngine, TestingMetrics
from driftguard.graph.builder import GraphBuilder
from driftguard.graph.knowledge import KnowledgeGraph
from driftguard.graph.analysis import GraphAnalysis
from driftguard.scoring.engine import ScoringEngine, HealthReport
from driftguard.scoring.weights import WeightProfile, PROFILES
from driftguard.insight.narrator import Narrator, InsightCard
from driftguard.insight.predictor import Predictor, CollapseEstimate
from driftguard.insight.recommendations import Recommender, Recommendation
from driftguard.pipeline import DriftGuardPipeline, EnrichedReport

__version__ = "2.0.0"
__all__ = [
    # Core engines (v1)
    "HealthScoreEngine", "ArchitectureMetrics",
    "VisionRuleEngine",
    "DriftEngine", "DriftReport",
    # New metric engines (v2)
    "ComplexityEngine", "ComplexityMetrics",
    "DependencyEngine", "DependencyMetrics",
    "EvolutionEngine", "EvolutionMetrics",
    "TeamEngine", "TeamMetrics",
    "TestingEngine", "TestingMetrics",
    # Graph
    "GraphBuilder", "KnowledgeGraph", "GraphAnalysis",
    # Scoring
    "ScoringEngine", "HealthReport", "WeightProfile", "PROFILES",
    # Insight
    "Narrator", "InsightCard",
    "Predictor", "CollapseEstimate",
    "Recommender", "Recommendation",
    # Pipeline
    "DriftGuardPipeline", "EnrichedReport",
]
