import json
from typing import TypedDict, Dict, Any, Optional, Tuple, Callable, List, Annotated, Union
from pydantic import create_model, Field
from langgraph.graph import StateGraph, START, END
from IPython.display import display, Image # For Graph Visualization

# Assuming you have the zen engine installed
import zen

# ---------------------------------------------------------
# 1. State Management & Reducers for Parallel Execution
# ---------------------------------------------------------
def merge_dicts(dict1: dict, dict2: dict) -> dict:
    """Reducer: Safely merges dictionaries from nodes executing in parallel."""
    dict1 = dict1 or {}
    dict2 = dict2 or {}
    merged = dict1.copy()
    merged.update(dict2)
    return merged

class GraphState(TypedDict):
    """
    Annotated tells LangGraph to use `merge_dicts` when state is updated.
    This prevents parallel nodes from overwriting each other's data!
    """
    input_data: Annotated[Dict[str, Any], merge_dicts]
    
    # We store statuses per node (e.g., {"node_1": {"status": "pass"}}) 
    # to avoid race conditions when parallel nodes report their status.
    node_results: Annotated[Dict[str, Dict[str, Any]], merge_dicts]


# ---------------------------------------------------------
# 2. Zen Engine Executor
# ---------------------------------------------------------
class GoRulesSingleExecutor:
    def __init__(self):
        self.engine = zen.ZenEngine()

    def execute_rule(self, input_rule: dict, context: dict):
        computations = input_rule.get("computations", {})
        validation_expr = input_rule.get("validation", "true")

        expressions = [{"id": "val_1", "key": "_passed", "value": validation_expr}]
        for var_name, formula in computations.items():
            expressions.append({"id": f"comp_{var_name}", "key": var_name, "value": formula})

        jdm_graph = {
            "contentType": "application/vnd.gorules.decision",
            "nodes": [
                {"id": "in", "type": "inputNode", "name": "Input"},
                {"id": "expr", "type": "expressionNode", "name": "Evaluate", "content": {"expressions": expressions}},
                {"id": "out", "type": "outputNode", "name": "Output"}
            ],
            "edges": [
                {"id": "edge1", "sourceId": "in", "targetId": "expr"},
                {"id": "edge2", "sourceId": "expr", "targetId": "out"}
            ]
        }

        decision = self.engine.create_decision(json.dumps(jdm_graph))
        try:
            evaluation_result = decision.evaluate(context)
            result_data = evaluation_result.get("result", {})
            
            passed = result_data.get("_passed", False)
            computed_updates = {k: result_data[k] for k in computations.keys() if k in result_data and result_data[k] is not None}
            return {"passed": passed, "error": None, "stateUpdates": computed_updates}

        except Exception as e:
            return {"passed": False, "error": f"Execution failed: {str(e)}", "stateUpdates": {}}


# ---------------------------------------------------------
# 3. Enhanced Rule Execution Engine
# ---------------------------------------------------------
class RuleExecutionEngine:
    def __init__(self, llm):
        self.llm = llm
        self.zen_executor = GoRulesSingleExecutor()
        self.nodes_config: Dict[str, dict] = {}
    
    def load_json_rules(self, rules: list):
        """Register JSON rule configurations."""
        for rule in rules:
            node_id = str(rule["nodeId"])
            self.nodes_config[node_id] = rule
            
    def register_custom_node(self, node_id: str | int, on_pass: Union[str, List[str]] = "END", on_fail: Union[str, List[str]] = "END", on_error: Union[str, List[str]] = "END"):
        """Decorator to register python functions."""
        def decorator(func: Callable[[Dict[str, Any]], Tuple[str, Dict[str, Any], Optional[str]]]):
            self.nodes_config[str(node_id)] = {
                "type": "Custom",
                "func": func,
                "onPass": on_pass,
                "onFail": on_fail,
                "onError": on_error
            }
            return func
        return decorator

    def _create_node_executable(self, node_id: str, config: dict) -> Callable[[GraphState], GraphState]:
        """Creates the executable closure for a specific node."""
        def node_function(state: GraphState) -> GraphState:
            input_data = state.get("input_data", {})
            node_type = config.get("type")
            
            # Helper to return formatted state updates
            def wrap_result(status: str, updates: dict, fail_reason: str = None, err_reason: str = None):
                return {
                    "input_data": updates,
                    "node_results": {
                        node_id: {"status": status, "failure_reason": fail_reason, "error_reason": err_reason}
                    }
                }

            try:
                if node_type == "Deterministic":
                    res = self.zen_executor.execute_rule(config.get("rule", {}), input_data)
                    if res["error"]:
                        return wrap_result("error", {}, None, res["error"])
                    elif not res["passed"]:
                        return wrap_result("fail", {}, "Validation expression failed", None)
                    else:
                        return wrap_result("pass", res.get("stateUpdates", {}))

                elif node_type == "GenAI":
                    rule_def = config.get("rule", {})
                    prompt_str = rule_def.get("prompt", "").format(**input_data)
                    schema_def = rule_def.get("outputSchema", {})
                    
                    pydantic_fields = {k: (str, Field(description=v)) for k, v in schema_def.items()}
                    DynamicOutputModel = create_model(f"GenAINode_{node_id}_Output", **pydantic_fields)
                    
                    llm_with_tools = self.llm.with_structured_output(DynamicOutputModel)
                    result = llm_with_tools.invoke(prompt_str)
                    
                    return wrap_result("pass", result.dict())

                elif node_type == "Custom":
                    status, updates, msg = config["func"](input_data)
                    return wrap_result(
                        status, updates, 
                        fail_reason=msg if status == "fail" else None, 
                        err_reason=msg if status == "error" else None
                    )
                else:
                    return wrap_result("error", {}, None, f"Unknown node type: {node_type}")

            except Exception as e:
                return wrap_result("error", {}, None, f"Exception occurred: {str(e)}")

        return node_function

    def compile(self, start_node_id: str | int):
        """Compiles the nodes into a parallel-capable LangGraph StateGraph."""
        start_node_id = str(start_node_id)
        valid_targets = set(self.nodes_config.keys()).union({"END"})
        
        # Validation: Check if targets exist and normalize them to lists
        for node_id, cfg in self.nodes_config.items():
            for route in ["onPass", "onFail", "onError"]:
                targets = cfg.get(route, "END")
                # Normalize strings to lists so routing logic is uniform
                targets = [targets] if isinstance(targets, str) else targets
                
                for t in targets:
                    if str(t) not in valid_targets:
                        raise ValueError(f"Node '{node_id}' routing '{route}' points to missing node '{t}'.")

        # Build Graph
        workflow = StateGraph(GraphState)

        # Add Nodes
        for node_id, config in self.nodes_config.items():
            workflow.add_node(node_id, self._create_node_executable(node_id, config))

        # Setup entry point
        workflow.add_edge(START, start_node_id)

        # Setup Dynamic / Parallel Routing
        for node_id, config in self.nodes_config.items():
            
            # 1. Define the router function
            def edge_router(state: GraphState, current_node=node_id, cfg=config) -> Union[str, List[str]]:
                # Check how the CURRENT node finished
                node_status = state.get("node_results", {}).get(current_node, {}).get("status", "error")
                
                # Fetch target route mapping dynamically (onPass, onFail, onError)
                route_key = f"on{node_status.capitalize()}"
                targets = cfg.get(route_key, ["END"])
                targets = [targets] if isinstance(targets, str) else targets
                
                # Convert "END" to LangGraph's internal END token
                mapped_targets = [END if str(t) == "END" else str(t) for t in targets]
                
                # If length is 1, return string (Standard). If >1, return list (Parallel Fan-out)
                return mapped_targets[0] if len(mapped_targets) == 1 else mapped_targets

            # 2. Extract all possible destinations strictly for Graph Visualization
            possible_destinations = set()
            for route in ["onPass", "onFail", "onError"]:
                t_list = cfg.get(route, ["END"])
                t_list = [t_list] if isinstance(t_list, str) else t_list
                for t in t_list:
                    possible_destinations.add(END if str(t) == "END" else str(t))

            # 3. Add conditional edge to workflow
            workflow.add_conditional_edges(
                node_id,
                edge_router,
                list(possible_destinations) # Passed to help graph renderer draw all possible routes
            )

        return workflow.compile()
