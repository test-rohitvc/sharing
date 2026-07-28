# assuming engine = RuleExecutionEngine(llm) has been initialized

# Load 15 JSON-based Rules (GenAI & Deterministic)
large_rules_json = [
    # ---- Phase 1: Intake ----
    {
        "nodeId": "1",
        "type": "Deterministic",
        "rule": {"computations": {}, "validation": "age >= 18"},
        "onPass": ["2", "3"], # PARALLEL FORK: Trigger GenAI and API simultaneously
        "onFail": "22",       # Direct to Rejection Custom Node
        "onError": "21"       # Direct to AI Exception Handler
    },
    {
        "nodeId": "2",
        "type": "GenAI",
        "rule": {
            "prompt": "Extract gross income from this text: {income_document}",
            "outputSchema": {"extracted_income": "Integer value of income"}
        },
        "onPass": "4",
        "onFail": "21",
        "onError": "21"
    },
    # Node 3 is a Custom API node (registered below)
    
    # ---- Phase 2: Validation ----
    {
        "nodeId": "4",
        "type": "Deterministic",
        "rule": {"computations": {}, "validation": "extracted_income > 30000"},
        "onPass": "6",
        "onFail": "22",
        "onError": "21"
    },
    {
        "nodeId": "5",
        "type": "Deterministic",
        "rule": {"computations": {}, "validation": "api_credit_score > 650"},
        "onPass": "6",
        "onFail": "22",
        "onError": "21"
    },
    # Node 6 is Custom merge node
    
    # ---- Phase 3: Deep Analysis ----
    {
        "nodeId": "7",
        "type": "Deterministic",
        "rule": {"computations": {"dti_ratio": "loan_amount / extracted_income"}, "validation": "true"},
        "onPass": ["8", "9"], # PARALLEL FORK
        "onFail": "END",
        "onError": "END"
    },
    {
        "nodeId": "8",
        "type": "Deterministic",
        "rule": {"computations": {}, "validation": "dti_ratio < 0.4"},
        "onPass": "10",
        "onFail": "22",
        "onError": "END"
    },
    {
        "nodeId": "9",
        "type": "GenAI",
        "rule": {
            "prompt": "Analyze loan risk based on purpose: {loan_purpose}",
            "outputSchema": {"ai_risk_assessment": "High or Low"}
        },
        "onPass": "11",
        "onFail": "21",
        "onError": "END"
    },
    # Nodes 10, 11, 12 are Custom logging/merge nodes
    
    # ---- Phase 4: Final AI Decision ----
    {
        "nodeId": "13",
        "type": "GenAI",
        "rule": {
            "prompt": "Review DTI {dti_ratio}, Risk {ai_risk_assessment}, Score {api_credit_score}. Approve or Deny?",
            "outputSchema": {"final_decision": "Approve or Deny"}
        },
        "onPass": "14",
        "onFail": "21",
        "onError": "21"
    },
    {
        "nodeId": "14",
        "type": "Deterministic",
        "rule": {"computations": {}, "validation": "final_decision == 'Approve'"},
        "onPass": ["15", "16", "17"], # MASSIVE PARALLEL FORK (Email, SMS, CRM)
        "onFail": "22",
        "onError": "END"
    },
    
    # ---- AI Exception Handlers ----
    {
        "nodeId": "21",
        "type": "GenAI",
        "rule": {
            "prompt": "An error occurred in processing: {error_reason}. Create an IT ticket summary.",
            "outputSchema": {"it_ticket": "Text description"}
        },
        "onPass": "END", "onFail": "END", "onError": "END"
    }
]

# Load into Engine
engine.load_json_rules(large_rules_json)

# Register the remaining Custom Python Nodes
@engine.register_custom_node(node_id="3", on_pass="5", on_fail="22", on_error="21")
def fetch_credit_api(input_data):
    return "pass", {"api_credit_score": 720}, None

@engine.register_custom_node(node_id="6", on_pass="7")
def sync_node_1(input_data):
    return "pass", {}, None

@engine.register_custom_node(node_id="10", on_pass="12")
def logging_node_a(input_data): return "pass", {}, None

@engine.register_custom_node(node_id="11", on_pass="12")
def logging_node_b(input_data): return "pass", {}, None

@engine.register_custom_node(node_id="12", on_pass="13")
def sync_node_2(input_data): return "pass", {}, None

# The Notification Fan-out Nodes
@engine.register_custom_node(node_id="15", on_pass="18")
def send_email(input_data): return "pass", {}, None

@engine.register_custom_node(node_id="16", on_pass="18")
def send_sms(input_data): return "pass", {}, None

@engine.register_custom_node(node_id="17", on_pass="18")
def update_crm(input_data): return "pass", {}, None

@engine.register_custom_node(node_id="18", on_pass="19")
def finalize_loan(input_data): return "pass", {}, None

@engine.register_custom_node(node_id="19", on_pass="20")
def generate_pdf(input_data): return "pass", {"pdf_url": "/loans/123.pdf"}, None

@engine.register_custom_node(node_id="20", on_pass="END")
def close_process(input_data): return "pass", {"status": "Complete"}, None

@engine.register_custom_node(node_id="22", on_pass="END")
def handle_rejection(input_data): return "pass", {"status": "Rejected"}, None


# 1. Compile the Graph
app = engine.compile(start_node_id="1")

# 2. EXPORT TO BPMN
export_to_bpmn_xml(engine, start_node_id="1", output_file="Loan_Origination_Process.bpmn")
