from langchain_openai import ChatOpenAI

# 1. Initialize Engine
llm = ChatOpenAI(model="gpt-4o")
engine = RuleExecutionEngine(llm=llm)

# 2. Load standard nodes from JSON
rules_json = [
    {
        "nodeId": "1",
        "type": "Deterministic",
        "rule": {
            "computations": {"requested_amount": "requested_amount * 1.1"},
            "validation": "requested_amount > 1000"
        },
        "onPass": "2",
        "onFail": "3",
        "onError": "END"
    },
    {
        "nodeId": "2",
        "type": "GenAI",
        "rule": {
            "prompt": "Evaluate the risk of lending ${requested_amount} to {borrower_name}.",
            "outputSchema": {
                "risk_level": "High, Medium, or Low",
                "risk_reason": "A brief explanation"
            }
        },
        "onPass": "END",
        "onFail": "END",
        "onError": "END"
    }
]
engine.load_json_rules(rules_json)

# 3. Decorator for Custom Code (Node 3)
@engine.register_custom_node(node_id="3", on_pass="END", on_fail="END", on_error="END")
def manual_review_node(input_data: dict):
    print("Sending to manual review due to failure...")
    
    # You must return a Tuple of: (status, dict_of_updates, failure_or_error_message)
    updates = {"review_status": "pending"}
    
    return "pass", updates, None 

# 4. Compile the Graph
# This will validate the routes and create the state machine
app = engine.compile(start_node_id="1")

# 5. Execute!
initial_state = {
    "input_data": {
        "borrower_name": "John Doe",
        "requested_amount": 1500
    },
    "status": "pass",
    "failure_reason": None,
    "error_reason": None
}

final_state = app.invoke(initial_state)

print(json.dumps(final_state, indent=2))
