from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from rbac_manager import KeycloakRBACManager
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from typing import List

app = FastAPI()
security = HTTPBearer()

# 1. Initialize the Component
rbac = KeycloakRBACManager(
    server_url="http://localhost:8080",
    realm="ai-agents-realm",
    admin_user="admin",
    admin_pass="admin",
    backend_client_id="fastapi-backend",
    backend_client_secret="your-secret"
)

# 2. Define Tools
def approve_payment(payment_id: str): 
    return f"Approved {payment_id}"

def create_payment(amount: float): 
    return f"Created payment for {amount}"

# Create a master registry mapping strings to actual Python functions
TOOL_REGISTRY = {
    "approve_payment": approve_payment,
    "create_payment": create_payment
}

# 3. FastAPI Dependency for Runtime Role Checking
def get_verified_roles(credentials: HTTPAuthorizationCredentials = Security(security)) -> List[str]:
    try:
        # Validates the JWT cryptographically
        roles = rbac.verify_token_and_get_roles(credentials.credentials)
        return roles
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

# 4. Integrating with LangGraph
@app.post("/chat")
async def chat(prompt: str, target_agent: str, human_roles: List[str] = Depends(get_verified_roles)):
    
    # Check if the human has the role required to talk to this agent
    if f"invoke:{target_agent}" not in human_roles:
        raise HTTPException(status_code=403, detail="You lack permission to invoke this agent.")
        
    # Look up the agent's UUID
    agents = rbac.get_agents()
    agent_uuid = next((a['id'] for a in agents if a['clientId'] == target_agent), None)
    
    if not agent_uuid:
        raise HTTPException(status_code=404, detail="Agent not found.")

    # Fetch what tools the agent is currently allowed to use from Keycloak
    authorized_tool_names = rbac.get_agent_tools_directly(agent_uuid)
    
    # Build the actual tool list for LangGraph
    actual_tools = [TOOL_REGISTRY[t] for t in authorized_tool_names if t in TOOL_REGISTRY]
    
    if not actual_tools:
        return {"response": "This agent has no authorized tools configured."}

    # Initialize the LLM with only the authorized tools
    llm = ChatOpenAI(model="gpt-4o")
    agent_executor = create_react_agent(llm, tools=actual_tools)
    
    result = agent_executor.invoke({"messages": [HumanMessage(content=prompt)]})
    return {"response": result["messages"][-1].content}
@app.get("/admin/matrix/users")
async def user_matrix():
    """Returns: {'alice': ['agent-user', 'agent-reviewer'], 'bob': ['agent-admin']}"""
    return rbac.get_user_role_matrix()

@app.get("/admin/matrix/agents")
async def agent_matrix():
    """Returns: {'agent-user': ['create_payment'], 'agent-admin': ['create_payment', 'approve_payment']}"""
    return rbac.get_agent_role_matrix()

@app.get("/admin/sessions")
async def active_sessions():
    """Returns a list of currently logged-in humans and their IP addresses."""
    # This automatically checks sessions against your "fastapi-backend" client
    return rbac.get_active_sessions()
