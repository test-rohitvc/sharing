# Keycloak RBAC Manager

## Overview

The `KeycloakRBACManager` is a robust, reusable Python component designed to bridge your backend services with Keycloak Identity and Access Management (IAM). It provides a seamless interface for managing both Human-to-Machine (H2M) and Machine-to-Machine (M2M) authorization, specifically tailored for AI Agent ecosystems.

It handles token validation natively (air-gapped via cached public keys), manages user and agent provisioning, and includes built-in tracing for observability.

## Features

* **Human User Management:** Register, authenticate, and manage standard users.
* **Agent (Client) Management:** Provision service accounts for AI agents and manage their credentials.
* **Dynamic Role Binding:** Assign Keycloak Realm Roles as "Tools" for agents and "Invoke Permissions" for humans.
* **Zero-Latency Token Verification:** Validates JWTs locally using cached public keys, bypassing network limits.
* **Auditing & Telemetry:** Built-in matrix generation for dashboarding active sessions and permission maps, fully instrumented with custom tracing.

## Prerequisites

* A running Keycloak server (v20+ recommended).
* A dedicated Realm (e.g., `ai-agents-realm`).
* A dedicated backend client in Keycloak (e.g., `fastapi-backend`) with **Service Accounts Enabled** and **Direct Access Grants Enabled**.

## Installation

Ensure you have the required dependencies installed in your environment:

```bash
pip install python-keycloak PyJWT fastapi uvicorn

```

## Initialization

To use the manager, instantiate it with your Keycloak server details and your backend client credentials. It is highly recommended to load these from environment variables.

```python
import os
from rbac import KeycloakRBACManager

rbac = KeycloakRBACManager(
    server_url=os.getenv("KEYCLOAK_URL", "http://localhost:8080"),
    realm=os.getenv("KEYCLOAK_REALM", "ai-agents-realm"),
    admin_user=os.getenv("KEYCLOAK_ADMIN_USER", "admin"),
    admin_pass=os.getenv("KEYCLOAK_ADMIN_PASS", "admin_password"),
    backend_client_id=os.getenv("KEYCLOAK_CLIENT_ID", "fastapi-backend"),
    backend_client_secret=os.getenv("KEYCLOAK_CLIENT_SECRET", "your-client-secret")
)

```

---

## Example 1: Agent & Tool Provisioning (Python Script)

You can use the manager in standalone scripts to bootstrap your environment, create agents, and assign tools to their service accounts.

```python
from rbac import KeycloakRBACManager

# Initialize the manager
rbac = KeycloakRBACManager(...)

# 1. Create a new AI Agent
agent_uuid = rbac.create_agent("finance-agent")
print(f"Agent created with UUID: {agent_uuid}")

# 2. Grant the agent permission to use specific tools
rbac.assign_agent_tool(agent_uuid, "tool:process_refund")
rbac.assign_agent_tool(agent_uuid, "tool:view_ledger")

# 3. Create a human user and grant them permission to invoke the agent
user_id = rbac.create_user("alice_finance", "alice@example.com", "securepassword123")
rbac.assign_user_role(user_id, "invoke:agent-finance-agent")

print("Provisioning complete!")

```

---

## Example 2: FastAPI Integration & Route Protection

The most powerful use case is injecting the manager into a FastAPI application as a dependency to protect your routes and validate tool access at runtime.

```python
from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from rbac import KeycloakRBACManager

app = FastAPI()
security = HTTPBearer()
rbac = KeycloakRBACManager(...)

def verify_human_access(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Dependency to validate the JWT and extract human roles."""
    try:
        roles = rbac.verify_token_and_get_roles(credentials.credentials)
        return roles
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

@app.post("/api/chat")
async def chat_with_agent(prompt: str, target_agent: str, human_roles: list = Depends(verify_human_access)):
    # 1. Check if the human is authorized to talk to this specific agent
    required_role = f"invoke:{target_agent}"
    if required_role not in human_roles:
        raise HTTPException(status_code=403, detail="You lack permission to invoke this agent.")

    # 2. Fetch the tools authorized for the target agent
    agents = rbac.get_agents()
    agent_uuid = next((a['id'] for a in agents if a['clientId'] == target_agent), None)
    
    if not agent_uuid:
        raise HTTPException(status_code=404, detail="Agent not found.")

    agent_tools = rbac.get_agent_tools_directly(agent_uuid)

    # 3. Execute your LLM/LangGraph logic here, passing only the authorized `agent_tools`
    return {
        "status": "success",
        "agent": target_agent,
        "tools_granted_to_agent": agent_tools,
        "message": f"Agent executing prompt: {prompt}"
    }

```

---

## Example 3: Admin Dashboards & Auditing

The manager includes built-in methods to generate data matrices for admin dashboards, making it easy to build UI control planes.

```python
from fastapi import FastAPI
from rbac import KeycloakRBACManager

app = FastAPI()
rbac = KeycloakRBACManager(...)

@app.get("/admin/matrix/users")
async def get_user_permissions():
    """
    Returns a map of users to the agents they can invoke.
    Example Output: {"alice_finance": ["agent-finance-agent"], "bob_dev": ["agent-admin"]}
    """
    return rbac.get_user_role_matrix()

@app.get("/admin/matrix/agents")
async def get_agent_permissions():
    """
    Returns a map of agents to the tools they are authorized to use.
    Example Output: {"agent-finance-agent": ["process_refund", "view_ledger"]}
    """
    return rbac.get_agent_role_matrix()

@app.get("/admin/sessions")
async def get_active_sessions():
    """
    Returns all active human sessions currently logged into the system.
    """
    return rbac.get_active_sessions()

```

