import json
import zen

class GoRulesSingleExecutor:
    def __init__(self, json_path: str):
        """Loads the JSON rule mapping and initializes the Zen Engine."""
        with open(json_path, 'r') as f:
            data = json.load(f)
            
        # Create a fast-lookup dictionary of rules by their ID
        self.rules_db = {rule["ruleId"]: rule for rule in data["nodes"]}
        self.engine = zen.ZenEngine()

    def execute_rule(self, rule_id: str, context: dict):
        """
        Builds a single-node JDM graph on the fly for the requested rule,
        executes it using Zen Engine, and returns the result and any state mutations.
        """
        rule = self.rules_db.get(rule_id)
        if not rule:
            raise ValueError(f"Rule ID '{rule_id}' not found.")

        # 1. Extract computations and validation from the rule
        zen_expr = rule["zenExpression"]
        computations = zen_expr.get("computations", {})
        validation_expr = zen_expr.get("validation", "true")

        # 2. Map them into GoRules Expression Node formats
        expressions = []

        expressions.append({"id": "val_1", "key": "_passed", "value": validation_expr})
        
        for var_name, formula in computations.items():
            expressions.append({"id": f"comp_{var_name}", "key": var_name, "value": formula})
            

        # 3. Construct a minimalist Single-Node Decision Graph (JDM)
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
                {"id":"edge1", "sourceId": "in", "targetId": "expr"},
                {"id":"edge2", "sourceId": "expr", "targetId": "out"}
            ]
        }

        # 4. Compile and evaluate the decision statelessly
        decision = self.engine.create_decision(json.dumps(jdm_graph))

        try:
            # Zen Engine throws a RuntimeError here if a math op hits a null/missing variable
            evaluation_result = decision.evaluate(context)
            result_data = evaluation_result.get("result", {})
            
            passed = result_data.get("_passed", False)
            computed_updates = {k: result_data[k] for k in computations.keys() if k in result_data and result_data[k] is not None}
            error_msg = None

        except Exception as e:
            # The payload was missing a variable required for a strict evaluation (e.g. math)
            passed = False
            computed_updates = {}
            error_msg = f"Execution failed due to missing or invalid data types: {str(e)}"

        return {
            "ruleId": rule_id,
            "passed": passed,
            "error": error_msg,
            "stateUpdates": computed_updates,
            "onFailure": rule["onFailure"] if not passed else None
        }

# ==========================================
# Testing the Execution
# ==========================================
if __name__ == "__main__":
    # Initialize the executor with your JSON file
    executor = GoRulesSingleExecutor("gorules_pure_rules.json")

    # --- Test 1: A Pure Validation Rule (S1-R1-D) ---
    print("--- Executing Validation Rule: S1-R1-D ---")
    payload_1 = {
        "borrower_name": "Acme Corp",
        "customer_id": "CUST-992",
        "facility_ref": None,
        # "requested_amount": 5000,
        "currency": "USD",
        "value_date": "2026-07-21",
        "channel": "API"
    }
    result_1 = executor.execute_rule("S1-R1-D", payload_1)
    print(json.dumps(result_1, indent=4))


    # --- Test 2: A Computational Rule (S10-R1) ---
    print("\n--- Executing Computational Rule: S10-R1 ---")
    payload_2 = {
        "benchmark_rate": 4.5,
        "spread_margin": 1.2
    }
    result_2 = executor.execute_rule("S10-R1", payload_2)
    print(json.dumps(result_2, indent=4))
