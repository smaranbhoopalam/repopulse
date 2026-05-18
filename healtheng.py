import networkx as nx
import yaml
from typing import List, Dict, Any, Tuple

class HealthIntelligenceEngine:
    def __init__(self, architecture_rules_yaml: str):
        """
        Initializes the intelligence engine with developer-defined vision rules.
        """
        # Parse the YAML configuration rules safely
        parsed_config = yaml.safe_load(architecture_rules_yaml) or {}
        self.rules = parsed_config.get('rules', [])
        
    def build_networkx_graph(self, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> nx.DiGraph:
        """
        Converts the standardized JSON node/edge payload from the repository 
        parser into a NetworkX Directed Graph for analysis.
        """
        G = nx.DiGraph()
        
        # Add modules/files as nodes with their properties (e.g., layer, lines of code)
        for node in nodes:
            node_id = node['id']
            node_attributes = {k: v for k, v in node.items() if k != 'id'}
            G.add_node(node_id, **node_attributes)
            
        # Add code imports as directed edges (source file -> imports target file)
        for edge in edges:
            G.add_edge(edge['source'], edge['target'])
            
        return G