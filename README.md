# Repo Health Intelligence Engine

Track how a codebase evolves over time — and determine whether engineering quality is improving or degrading.

Unlike traditional static-analysis platforms that only analyze the current repository state, this system models repositories as evolving temporal structures. It transforms commit history into an analyzable knowledge graph and detects architectural drift, maintainability decay, ownership risk, and systemic instability across time.

---

# Core Philosophy

Most repository analysis tools answer:

> “What does the codebase look like today?”

This system answers:

> “How did the codebase evolve into its current state, and which commits changed its long-term health trajectory?”

The platform prioritizes:
- deterministic structural analysis
- AST-driven parsing
- graph intelligence
- temporal evolution modeling
- minimal, justified LLM usage

This is **not** a generic RAG chatbot over source code.

---

# System Architecture

```text
[Git Repo]
    │
    ▼
[libgit2 Extraction Layer]
    │
    ├── Commit DAG Reconstruction
    ├── Raw Diff Extraction
    └── Contributor Timeline Analysis
    │
    ▼
[Multi-threaded AST Parsing Pipeline]
    │
    ├── Tree-sitter Parsing
    ├── Symbol Extraction
    ├── Dependency Detection
    ├── Call Graph Generation
    └── Structural Change Detection
    │
    ▼
[Graph Transformation Engine]
    │
    ├── Temporal Knowledge Graph Construction
    ├── Symbol Lineage Tracking
    ├── Dependency Evolution Mapping
    └── Architectural State Versioning
    │
    ▼
[Deterministic Analytics Engine]
    │
    ├── Architectural Drift Detection
    ├── Complexity Delta Analysis
    ├── Bus Factor Computation
    ├── Hotspot Detection
    ├── Centrality / PageRank Metrics
    ├── Coupling Instability Metrics
    └── Ownership Entropy Analysis
    │
    ├────────────────────────────────────┐
    │                                    │
    ▼                                    ▼
[Filtered Subgraph Pipeline]      [Health Metric Aggregation]
    │                                    │
    ▼                                    ▼
[LLM Reasoning Engine]           [Unified Health State]
    │                                    │
    └────────────────────────────────────┘
                     │
                     ▼
       [WebSocket Streaming Interface]
                     │
                     ▼
       [WebGL / Three.js Visualization]