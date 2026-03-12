import jwt
from keycloak import KeycloakAdmin, KeycloakOpenID
from keycloak.exceptions import KeycloakError
from typing import List, Dict, Optional

class KeycloakRBACManager:
    def __init__(self, server_url: str, realm: str, admin_user: str, admin_pass: str, backend_client_id: str, backend_client_secret: str):
        self.realm = realm
        
        # OpenID: Used for authenticating users and verifying tokens
        self.openid = KeycloakOpenID(
            server_url=server_url,
            realm_name=realm,
            client_id=backend_client_id,
            client_secret_key=backend_client_secret
        )
        
        # Admin: Used for CRUD operations on users, agents, and roles
        self.admin = KeycloakAdmin(
            server_url=server_url,
            username=admin_user,
            password=admin_pass,
            realm_name=realm,
            user_realm_name="master",
            client_id="admin-cli",
            verify=True
        )
        
        # Cache the public key to avoid network calls during token validation
        self.public_key = f"-----BEGIN PUBLIC KEY-----\n{self.admin.realm_public_key()}\n-----END PUBLIC KEY-----"

    # ==========================================
    # 1. Human User Management
    # ==========================================
    def create_user(self, username: str, email: str, password: str) -> str:
        payload = {"username": username, "email": email, "enabled": True}
        user_id = self.admin.create_user(payload)
        self.admin.set_user_password(user_id, password, temporary=False)
        return user_id

    def get_users(self) -> List[Dict]:
        users = self.admin.get_users()
        # Filter out service accounts
        return [u for u in users if not u.get('username').startswith('service-account-')]

    def delete_user(self, user_id: str):
        self.admin.delete_user(user_id)

    def login_user(self, username: str, password: str) -> dict:
        """Returns the JWT token for a human user."""
        return self.openid.token(username, password)

    def assign_user_role(self, user_id: str, role_name: str):
        """Used to grant a human permission to invoke an agent (e.g., 'invoke:agent-admin')."""
        role = self.admin.get_realm_role(role_name)
        self.admin.assign_realm_roles(user_id=user_id, roles=[role])

    def remove_user_role(self, user_id: str, role_name: str):
        role = self.admin.get_realm_role(role_name)
        self.admin.delete_realm_roles_of_user(user_id=user_id, roles=[role])

    # ==========================================
    # 2. AI Agent (Client) Management
    # ==========================================
    def create_agent(self, agent_name: str) -> str:
        """Creates the Agent Client AND auto-creates its matching 'invoke' role."""
        client_id = f"agent-{agent_name}" if not agent_name.startswith("agent-") else agent_name
        payload = {"clientId": client_id, "serviceAccountsEnabled": True, "publicClient": False}
        client_uuid = self.admin.create_client(payload)
        
        # Create the role that humans need to invoke this agent
        try:
            self.admin.create_realm_role(payload={"name": f"invoke:{client_id}"})
        except KeycloakError:
            pass # Role might already exist
            
        return client_uuid

    def get_agents(self) -> List[Dict]:
        clients = self.admin.get_clients()
        return [c for c in clients if c['clientId'].startswith('agent-')]

    def delete_agent(self, client_uuid: str, client_id: str):
        self.admin.delete_client(client_uuid)
        # Clean up the invoke role
        try:
            self.admin.delete_realm_role(f"invoke:{client_id}")
        except KeycloakError:
            pass

    def login_agent(self, client_id: str, client_secret: str) -> dict:
        """Returns the JWT token for machine-to-machine agent auth."""
        # Create a temporary OpenID client for this specific agent
        temp_openid = KeycloakOpenID(
            server_url=self.openid.server_url, realm_name=self.realm,
            client_id=client_id, client_secret_key=client_secret
        )
        return temp_openid.token(grant_type="client_credentials")

    def assign_agent_tool(self, client_uuid: str, tool_name: str):
        """Grants a tool (role) to an agent's service account."""
        formatted_tool = f"tool:{tool_name}" if not tool_name.startswith("tool:") else tool_name
        # Ensure the tool role exists in Keycloak
        try:
            self.admin.create_realm_role(payload={"name": formatted_tool})
        except KeycloakError:
            pass 
            
        sa_user = self.admin.get_client_service_account_user(client_uuid)
        role = self.admin.get_realm_role(formatted_tool)
        self.admin.assign_realm_roles(user_id=sa_user['id'], roles=[role])

    def remove_agent_tool(self, client_uuid: str, tool_name: str):
        formatted_tool = f"tool:{tool_name}" if not tool_name.startswith("tool:") else tool_name
        sa_user = self.admin.get_client_service_account_user(client_uuid)
        role = self.admin.get_realm_role(formatted_tool)
        self.admin.delete_realm_roles_of_user(user_id=sa_user['id'], roles=[role])

    # ==========================================
    # 3. Runtime Validation & Introspection
    # ==========================================
    def verify_token_and_get_roles(self, token: str) -> List[str]:
        """Air-gapped JWT validation. Extremely fast, zero network calls."""
        decoded = jwt.decode(token, self.public_key, algorithms=["RS256"], options={"verify_aud": False})
        return decoded.get("realm_access", {}).get("roles", [])
        
    def get_agent_tools_directly(self, client_uuid: str) -> List[str]:
        """If you need to check an agent's tools WITHOUT them logging in."""
        sa_user = self.admin.get_client_service_account_user(client_uuid)
        roles = self.admin.get_realm_roles_of_user(sa_user['id'])
        return [r['name'].split(':')[1] for r in roles if r['name'].startswith('tool:')]

    # ==========================================
    # 4. Configuration Settings
    # ==========================================
    def update_jwt_expiry(self, lifespan_seconds: int):
        """Dynamically changes how long JWTs remain valid (Keycloak Realm Setting)."""
        realm_settings = self.admin.get_realm()
        realm_settings['accessTokenLifespan'] = lifespan_seconds
        self.admin.update_realm(payload=realm_settings)

    # ==========================================
    # 5. Auditing & Matrices
    # ==========================================
    def get_user_role_matrix(self) -> Dict[str, List[str]]:
        """
        Returns a dictionary mapping human usernames to their assigned roles.
        Specifically filters for 'invoke:' roles to see which agents they can use.
        """
        users = self.get_users()
        matrix = {}
        for user in users:
            try:
                roles = self.admin.get_realm_roles_of_user(user['id'])
                # Filter to only show the agent invocation roles
                invoke_roles = [r['name'].replace('invoke:', '') for r in roles if r['name'].startswith('invoke:')]
                matrix[user['username']] = invoke_roles
            except KeycloakError:
                matrix[user['username']] = []
        return matrix

    def get_agent_role_matrix(self) -> Dict[str, List[str]]:
        """
        Returns a dictionary mapping Agent Client IDs to their authorized tools.
        """
        agents = self.get_agents()
        matrix = {}
        for agent in agents:
            try:
                # Reuses your existing function to fetch tools
                tools = self.get_agent_tools_directly(agent['id'])
                matrix[agent['clientId']] = tools
            except KeycloakError:
                # Failsafe in case a service account wasn't generated properly
                matrix[agent['clientId']] = []
        return matrix

    def get_active_sessions(self, target_client_id: Optional[str] = None) -> List[Dict]:
        """
        Returns all active human user sessions for a specific client.
        If no client_id is passed, it defaults to your backend_client_id.
        """
        # Default to the client used to initialize the class
        client_to_check = target_client_id or self.openid.client_id
        
        # Keycloak requires the internal UUID to fetch sessions, not the string name
        clients = self.admin.get_clients({"clientId": client_to_check})
        if not clients:
            return []
            
        client_uuid = clients[0]['id']
        
        try:
            # Fetch active user sessions for this client
            sessions = self.admin.get_client_user_sessions(client_uuid)
            
            # Clean up the output to return only the most relevant data
            cleaned_sessions = []
            for session in sessions:
                cleaned_sessions.append({
                    "username": session.get("username"),
                    "ip_address": session.get("ipAddress"),
                    "start_time": session.get("start"),
                    "last_access": session.get("lastAccess"),
                    "session_id": session.get("id")
                })
            return cleaned_sessions
        except KeycloakError:
            return []
