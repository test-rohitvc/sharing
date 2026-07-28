import json
from typing import TypedDict, Dict, Any, Optional, Tuple, Callable, List, Annotated, Union
from pydantic import create_model, Field
from langgraph.graph import StateGraph, START, END

# Assuming you have the zen engine installed
import zen

# ---------------------------------------------------------
# 1. State Management & Reducers
# ---------------------------------------------------------
def merge_dicts(dict1: dict, dict2: dict) -> dict:
    """Reducer: Safely merges dictionaries from nodes executing in parallel."""
    if not dict1: return dict2 or {}
    if not dict2: return dict1 or {}
    merged = dict1.copy()
    merged.update(dict2)
    return merged

class GraphState(TypedDict):
    input_data: Annotated[Dict[str, Any], merge_dicts]
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
# 3. Rule Execution Engine
# ---------------------------------------------------------
class RuleExecutionEngine:
    def __init__(self, llm):
        self.llm = llm
        self.zen_executor = GoRulesSingleExecutor()
        self.nodes_config: Dict[str, dict] = {}
    
    def load_json_rules(self, rules: list):
        for rule in rules:
            self.nodes_config[str(rule["nodeId"])] = rule
            
    def register_custom_node(self, node_id: str | int, on_pass: Union[str, List[str]] = "END", on_fail: Union[str, List[str]] = "END", on_error: Union[str, List[str]] = "END"):
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
        def node_function(state: GraphState) -> GraphState:
            input_data = state.get("input_data", {})
            node_type = config.get("type")
            
            def wrap_result(status: str, updates: dict, fail_reason: str = None, err_reason: str = None):
                return {
                    "input_data": updates,
                    "node_results": {node_id: {"status": status, "failure_reason": fail_reason, "error_reason": err_reason}}
                }

            try:
                if node_type == "Deterministic":
                    res = self.zen_executor.execute_rule(config.get("rule", {}), input_data)
                    if res["error"]: return wrap_result("error", {}, None, res["error"])
                    elif not res["passed"]: return wrap_result("fail", {}, "Validation expression failed", None)
                    else: return wrap_result("pass", res.get("stateUpdates", {}))

                elif node_type == "GenAI":
                    rule_def = config.get("rule", {})
                    prompt_str = rule_def.get("prompt", "").format(**input_data)
                    schema_def = rule_def.get("outputSchema", {})
                    
                    pydantic_fields = {k: (str, Field(description=v)) for k, v in schema_def.items()}
                    DynamicOutputModel = create_model(f"GenAINode_{node_id}_Output", **pydantic_fields)
                    
                    result = self.llm.with_structured_output(DynamicOutputModel).invoke(prompt_str)
                    return wrap_result("pass", result.dict())

                elif node_type == "Custom":
                    status, updates, msg = config["func"](input_data)
                    return wrap_result(status, updates, msg if status == "fail" else None, msg if status == "error" else None)
                else:
                    return wrap_result("error", {}, None, f"Unknown node type: {node_type}")

            except Exception as e:
                return wrap_result("error", {}, None, f"Exception occurred: {str(e)}")

        return node_function

    def compile(self, start_node_id: str | int):
        start_node_id = str(start_node_id)
        
        # Build Graph
        workflow = StateGraph(GraphState)

        # Add Nodes
        for node_id, config in self.nodes_config.items():
            workflow.add_node(node_id, self._create_node_executable(node_id, config))

        # Setup entry point
        workflow.add_edge(START, start_node_id)

        # ---------------------------------------------------------
        # THE FIX: Directly return target arrays from the router
        # ---------------------------------------------------------
        for node_id, config in self.nodes_config.items():
            
            # 1. The router dynamically returns the node name string OR the parallel node array. 
            # LangGraph handles list returns natively.
            def get_status_router(nid: str, cfg: dict):
                def router(state: GraphState) -> Union[str, List[str]]:
                    status = state.get("node_results", {}).get(nid, {}).get("status", "error")
                    route_key = f"on{status.capitalize()}" # onPass, onFail, onError
                    
                    targets = cfg.get(route_key, "END")
                    if isinstance(targets, str):
                        return END if targets == "END" else str(targets)
                    elif isinstance(targets, list):
                        return [END if str(t) == "END" else str(t) for t in targets]
                    return END
                return router
            
            # 2. Collect all possible unique destinations this node could reach
            possible_destinations = set()
            for route in ["onPass", "onFail", "onError"]:
                targets = config.get(route, "END")
                targets = [targets] if isinstance(targets, str) else targets
                for t in targets:
                    possible_destinations.add(END if str(t) == "END" else str(t))

            # 3. Supply the list of possible destinations to LangGraph 
            # This completely avoids dictionaries, preventing the "unhashable list" error,
            # while giving LangGraph's visualizer everything it needs to draw the connections!
            workflow.add_conditional_edges(
                node_id,
                get_status_router(node_id, config),
                list(possible_destinations)
            )

        return workflow.compile()
