import json
from typing import TypedDict, Dict, Any, Optional, Tuple, Callable
from pydantic import create_model, Field
from langgraph.graph import StateGraph, START, END

import zen

class GraphState(TypedDict):
    """The State object passed between nodes in LangGraph."""
    input_data: Dict[str, Any]
    status: str  # Will hold "pass", "fail", or "error" for routing
    failure_reason: Optional[str]
    error_reason: Optional[str]


class GoRulesSingleExecutor:
    """The deterministic Zen engine executor you provided."""
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
                {
                    "id": "expr",
                    "type": "expressionNode",
                    "name": "Evaluate Rule",
                    "content": {"expressions": expressions}
                },
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
            error_msg = None

        except Exception as e:
            passed = False
            computed_updates = {}
            error_msg = f"Execution failed due to missing or invalid data types: {str(e)}"

        return {
            "passed": passed,
            "error": error_msg,
            "stateUpdates": computed_updates,
        }


class RuleExecutionEngine:
    def __init__(self, llm):
        """
        :param llm: A LangChain Chat Model (e.g., ChatOpenAI)
        """
        self.llm = llm
        self.zen_executor = GoRulesSingleExecutor()
        self.nodes_config: Dict[str, dict] = {}
    
    def load_json_rules(self, rules: list):
        """Register a list of rule configurations from JSON."""
        for rule in rules:
            node_id = str(rule["nodeId"])  # Langgraph requires string IDs
            self.nodes_config[node_id] = rule
            
    def register_custom_node(self, node_id: str | int, on_pass: str | int = "END", on_fail: str | int = "END", on_error: str | int = "END"):
        """Decorator to register a custom python node."""
        def decorator(func: Callable[[Dict[str, Any]], Tuple[str, Dict[str, Any], Optional[str]]]):
            self.nodes_config[str(node_id)] = {
                "type": "Custom",
                "func": func,
                "onPass": str(on_pass),
                "onFail": str(on_fail),
                "onError": str(on_error)
            }
            return func
        return decorator

    def _create_node_executable(self, node_id: str, config: dict) -> Callable[[GraphState], GraphState]:
        """Creates the LangGraph node function based on the node type."""
        
        def node_function(state: GraphState) -> GraphState:
            input_data = state.get("input_data", {}).copy()
            node_type = config.get("type")
            
            try:
                # ---------------------------------------------
                # 1. Deterministic Rule (Zen / GoRules)
                # ---------------------------------------------
                if node_type == "Deterministic":
                    rule_def = config.get("rule", {})
                    res = self.zen_executor.execute_rule(rule_def, input_data)
                    
                    if res["error"]:
                        return {"input_data": input_data, "status": "error", "error_reason": res["error"], "failure_reason": None}
                    elif not res["passed"]:
                        return {"input_data": input_data, "status": "fail", "failure_reason": "Deterministic validation failed", "error_reason": None}
                    else:
                        input_data.update(res.get("stateUpdates", {}))
                        return {"input_data": input_data, "status": "pass", "failure_reason": None, "error_reason": None}

                # ---------------------------------------------
                # 2. GenAI Rule (LangChain)
                # ---------------------------------------------
                elif node_type == "GenAI":
                    rule_def = config.get("rule", {})
                    prompt_template = rule_def.get("prompt", "")
                    schema_def = rule_def.get("outputSchema", {})
                    
                    # Resolve prompt variables dynamically
                    prompt_str = prompt_template.format(**input_data)
                    
                    # Convert JSON schema to Pydantic Model
                    # Assuming all outputs are strings since the JSON only provided descriptions
                    pydantic_fields = {
                        k: (str, Field(description=v)) for k, v in schema_def.items()
                    }
                    DynamicOutputModel = create_model(f"GenAINode_{node_id}_Output", **pydantic_fields)
                    
                    llm_with_tools = self.llm.with_structured_output(DynamicOutputModel)
                    result = llm_with_tools.invoke(prompt_str)
                    
                    # Update state with LLM extraction
                    input_data.update(result.dict())
                    return {"input_data": input_data, "status": "pass", "failure_reason": None, "error_reason": None}

                # ---------------------------------------------
                # 3. Custom Python Rule
                # ---------------------------------------------
                elif node_type == "Custom":
                    func = config["func"]
                    # Custom function signature: (input_data) -> (status, updates_dict, message)
                    status, updates, msg = func(input_data)
                    
                    input_data.update(updates)
                    
                    return {
                        "input_data": input_data,
                        "status": status,
                        "error_reason": msg if status == "error" else None,
                        "failure_reason": msg if status == "fail" else None
                    }
                
                else:
                    raise ValueError(f"Unknown node type: {node_type}")

            except KeyError as e:
                return {"input_data": input_data, "status": "error", "error_reason": f"Missing variable in context: {str(e)}", "failure_reason": None}
            except Exception as e:
                return {"input_data": input_data, "status": "error", "error_reason": f"Exception occurred: {str(e)}", "failure_reason": None}

        return node_function

    def compile(self, start_node_id: str | int):
        """Compiles the rule configurations into a LangGraph executable."""
        start_node_id = str(start_node_id)
        
        # 1. Compile-Time Validation: Check if all routes exist
        valid_targets = set(self.nodes_config.keys()).union({"END"})
        for node_id, cfg in self.nodes_config.items():
            for route in ["onPass", "onFail", "onError"]:
                target = str(cfg.get(route, "END"))
                if target not in valid_targets:
                    raise ValueError(f"Compile Error: Node '{node_id}' routing '{route}' points to non-existent node '{target}'.")

        if start_node_id not in self.nodes_config:
            raise ValueError(f"Compile Error: Start node '{start_node_id}' is not registered.")

        # 2. Build the Graph
        workflow = StateGraph(GraphState)

        # Add Nodes
        for node_id, config in self.nodes_config.items():
            workflow.add_node(node_id, self._create_node_executable(node_id, config))

        # 3. Setup Routing edges
        workflow.add_edge(START, start_node_id)

        for node_id, config in self.nodes_config.items():
            pass_target = str(config.get("onPass", "END"))
            fail_target = str(config.get("onFail", "END"))
            error_target = str(config.get("onError", "END"))

            # Map to actual routing values. Langgraph uses the explicit END constant to terminate.
            path_map = {
                "pass": END if pass_target == "END" else pass_target,
                "fail": END if fail_target == "END" else fail_target,
                "error": END if error_target == "END" else error_target
            }

            workflow.add_conditional_edges(
                node_id,
                lambda state: state["status"], # Routes based on the status returned by the node
                path_map
            )

        return workflow.compile()
