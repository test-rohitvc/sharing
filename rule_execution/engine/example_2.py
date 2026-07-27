import json
from langchain_openai import ChatOpenAI
# Import the engine we created earlier
# from your_engine_module import RuleExecutionEngine 

# Initialize the Engine
llm = ChatOpenAI(model="gpt-4o", temperature=0)
engine = RuleExecutionEngine(llm=llm)

# ==========================================
# 1. DEFINE JSON-BASED RULES (GenAI & Deterministic)
# ==========================================
rules_json = [
    {
        "nodeId": "1",
        "type": "Deterministic",
        "rule": {
            "computations": {},
            "validation": "age >= 18 and requested_amount > 0"
        },
        "onPass": "2",
        "onFail": "13",
        "onError": "16"
    },
    {
        "nodeId": "2",
        "type": "GenAI",
        "rule": {
            "prompt": "Extract the primary reason for this loan and its urgency from the user's note: '{user_note}'.",
            "outputSchema": {
                "loan_purpose": "A 3-5 word summary of what the loan is for",
                "urgency_level": "High, Medium, or Low"
            }
        },
        "onPass": "3",
        "onFail": "13",
        "onError": "16"
    },
    {
        "nodeId": "3",
        "type": "Deterministic",
        "rule": {
            "computations": {},
            "validation": "requested_amount >= 500 and requested_amount <= 100000"
        },
        "onPass": "4",
        "onFail": "13",
        "onError": "16"
    },
    {
        "nodeId": "5",
        "type": "Deterministic",
        "rule": {
            "computations": {},
            "validation": "credit_score >= 600"
        },
        "onPass": "6",
        "onFail": "13",
        "onError": "16"
    },
    {
        "nodeId": "6",
        "type": "GenAI",
        "rule": {
            "prompt": "Act as a Fraud Analyst. The user wants ${requested_amount} for '{loan_purpose}' with '{urgency_level}' urgency. Is this combination highly suspicious? Output 'true' or 'false' for is_suspicious.",
            "outputSchema": {
                "is_suspicious": "string exactly 'true' or 'false'",
                "fraud_reason": "Brief explanation of why it is or isn't suspicious"
            }
        },
        "onPass": "7",
        "onFail": "12", # GenAI fail routes to manual review
        "onError": "16"
    },
    {
        "nodeId": "8",
        "type": "Deterministic",
        "rule": {
            "computations": {"dti_percentage": "dti_ratio * 100"},
            "validation": "dti_ratio < 0.45"
        },
        "onPass": "9",
        "onFail": "12", # High DTI goes to manual review
        "onError": "16"
    },
    {
        "nodeId": "9",
        "type": "GenAI",
        "rule": {
            "prompt": "Based on Credit Score: {credit_score}, DTI Ratio: {dti_ratio}, and Fraud Suspicion: {is_suspicious}, assign a Risk Tier (Low, Medium, High).",
            "outputSchema": {
                "risk_tier": "Low, Medium, or High",
                "risk_summary": "1 sentence explanation"
            }
        },
        "onPass": "10",
        "onFail": "12",
        "onError": "16"
    },
    {
        "nodeId": "10",
        "type": "Deterministic",
        "rule": {
            "computations": {},
            "validation": "risk_tier == 'Low' or risk_tier == 'Medium'"
        },
        "onPass": "11",
        "onFail": "12", # High risk tier goes to manual review
        "onError": "16"
    },
    {
        "nodeId": "14",
        "type": "GenAI",
        "rule": {
            "prompt": "Draft a polite 2-sentence loan rejection email for {borrower_name} regarding their request for ${requested_amount}. Reason context: {failure_reason} or {risk_summary}.",
            "outputSchema": {
                "email_subject": "Email subject",
                "email_body": "Email body content"
            }
        },
        "onPass": "18",
        "onFail": "18",
        "onError": "16"
    },
    {
        "nodeId": "15",
        "type": "GenAI",
        "rule": {
            "prompt": "Draft a congratulatory 2-sentence loan approval email for {borrower_name} for ${requested_amount}. Mention their EMI is ${emi_amount}.",
            "outputSchema": {
                "email_subject": "Email subject",
                "email_body": "Email body content"
            }
        },
        "onPass": "17",
        "onFail": "17",
        "onError": "16"
    }
]

# Load standard JSON nodes into engine
engine.load_json_rules(rules_json)


# ==========================================
# 2. DEFINE CUSTOM PYTHON RULES via Decorators
# ==========================================

@engine.register_custom_node(node_id="4", on_pass="5", on_fail="16", on_error="16")
def mock_credit_bureau_api(input_data: dict):
    """Mocks an external API call to fetch credit score and monthly debts."""
    print("-> [Node 4] Calling External Credit Bureau...")
    if not input_data.get("ssn"):
        return "error", {}, "Missing SSN for Credit Check"
    
    # Mocking data retrieval
    updates = {
        "credit_score": 710,
        "monthly_debt": 800
    }
    return "pass", updates, None

@engine.register_custom_node(node_id="7", on_pass="8", on_fail="12", on_error="16")
def calculate_dti(input_data: dict):
    """Calculates Debt-To-Income Ratio."""
    print("-> [Node 7] Calculating DTI...")
    income = input_data.get("monthly_income", 0)
    debt = input_data.get("monthly_debt", 0)
    
    if income <= 0:
        return "error", {}, "Income must be greater than 0"
        
    dti = round(debt / income, 2)
    return "pass", {"dti_ratio": dti}, None

@engine.register_custom_node(node_id="11", on_pass="15", on_fail="12", on_error="16")
def calculate_emi(input_data: dict):
    """Calculates EMI (Math operation)."""
    print("-> [Node 11] Calculating EMI...")
    amount = input_data.get("requested_amount", 0)
    tier = input_data.get("risk_tier", "High")
    
    # Simple mock math for Interest Rate
    rates = {"Low": 0.05, "Medium": 0.08, "High": 0.12}
    rate = rates.get(tier, 0.15)
    
    # Simple Interest Monthly calc for mockup
    emi = round((amount + (amount * rate)) / 12, 2)
    return "pass", {"emi_amount": emi, "interest_rate": rate}, None

@engine.register_custom_node(node_id="12", on_pass="11", on_fail="13", on_error="16")
def manual_review_queue(input_data: dict):
    """Simulates a human looking at the file if rules fail."""
    print(f"-> [Node 12] MANUAL REVIEW TRIGGERED! (Suspicion: {input_data.get('is_suspicious')}, DTI: {input_data.get('dti_ratio')})")
    
    # Mock Manual Review Logic: If it's outright fraud, reject. If it's just High DTI, override and approve.
    is_susp = input_data.get("is_suspicious", "false").lower() == "true"
    
    if is_susp:
        print("   Human decision: REJECT (Fraud)")
        return "fail", {"review_decision": "Rejected by human due to fraud risk"}, "Failed Manual Review"
    else:
        print("   Human decision: APPROVE OVERRIDE (Acceptable Risk)")
        return "pass", {"review_decision": "Approved by human override", "risk_tier": "Medium"}, None

@engine.register_custom_node(node_id="13", on_pass="14", on_fail="14", on_error="16")
def auto_reject_router(input_data: dict):
    """Simple pass-through router for standardizing rejections."""
    print("-> [Node 13] Routing to Rejection Letter Generation...")
    return "pass", {"final_status": "REJECTED"}, None

@engine.register_custom_node(node_id="16", on_pass="END", on_fail="END", on_error="END")
def global_error_handler(input_data: dict):
    """Catches all system errors / missing variables."""
    print(f"-> [Node 16] SYSTEM ERROR HANDLER INVOKED.")
    return "pass", {"final_status": "SYSTEM_ERROR"}, None

@engine.register_custom_node(node_id="17", on_pass="END", on_fail="END", on_error="END")
def save_approval_to_db(input_data: dict):
    print(f"-> [Node 17] DB COMMIT: Loan Approved for {input_data['borrower_name']}.")
    return "pass", {}, None

@engine.register_custom_node(node_id="18", on_pass="END", on_fail="END", on_error="END")
def save_rejection_to_db(input_data: dict):
    print(f"-> [Node 18] DB COMMIT: Loan Rejected for {input_data['borrower_name']}.")
    return "pass", {}, None


# ==========================================
# 3. COMPILE AND EXECUTE
# ==========================================

# Compile graph starting at Node 1
app = engine.compile(start_node_id="1")

# --- TEST CASE 1: Perfect Applicant ---
print("\n========== STARTING RUN 1: Perfect Applicant ==========")
initial_state_1 = {
    "input_data": {
        "borrower_name": "Alice Cooper",
        "age": 35,
        "ssn": "000-11-2222",
        "requested_amount": 15000,
        "monthly_income": 8000,
        "user_note": "I need to repair my house roof before winter. Very urgent!"
    },
    "status": "pass",
    "failure_reason": None,
    "error_reason": None
}

final_state_1 = app.invoke(initial_state_1)
print("\nFinal State Data (Approved):")
print(json.dumps(final_state_1["input_data"], indent=2))


# --- TEST CASE 2: High DTI (Triggers Manual Review -> Override Approve) ---
print("\n========== STARTING RUN 2: High DTI Applicant ==========")
initial_state_2 = {
    "input_data": {
        "borrower_name": "Bob Builder",
        "age": 28,
        "ssn": "000-33-4444",
        "requested_amount": 45000,
        "monthly_income": 1500, # Very low income = High DTI
        "user_note": "Need a car to get to work."
    },
    "status": "pass",
    "failure_reason": None,
    "error_reason": None
}

final_state_2 = app.invoke(initial_state_2)
print("\nFinal State Data (Manual Override):")
print(json.dumps({
    "dti_ratio": final_state_2["input_data"].get("dti_ratio"),
    "review_decision": final_state_2["input_data"].get("review_decision"),
    "email_body": final_state_2["input_data"].get("email_body")
}, indent=2))
