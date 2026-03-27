from keycloak import KeycloakAdmin
from keycloak.exceptions import KeycloakError
from datetime import datetime, timezone

class KeycloakService:
    def __init__(self, server_url: str, realm_name: str, client_id: str, client_secret: str):
        """
        Initializes the Keycloak Admin Client. 
        Requires a Service Account client with realm-management roles.
        """
        self.admin = KeycloakAdmin(
            server_url=server_url,
            realm_name=realm_name,
            client_id=client_id,
            client_secret_key=client_secret,
            verify=True
        )

    def get_enriched_users(self) -> list[dict]:
        """
        Fetches all users and enriches them with roles and session data.
        """
        enriched_users = []
        
        try:
            # Fetch all users (Note: You may want to paginate this for large realms)
            users = self.admin.get_users()
            
            for user in users:
                user_id = user.get("id")
                
                # 1. Fetch Realm Roles
                roles_payload = self.admin.get_realm_roles_of_user(user_id)
                roles = [role.get("name") for role in roles_payload]
                
                # 2. Fetch Sessions for IP and Last Access
                sessions = self.admin.get_user_sessions(user_id)
                ip_address = None
                last_access = None
                
                # If the user has active sessions, take the most recent one
                if sessions:
                    latest_session = sessions[0] # Keycloak usually orders newest first
                    ip_address = latest_session.get("ipAddress")
                    
                    # Keycloak returns lastAccess as a Unix timestamp in milliseconds
                    last_access_ms = latest_session.get("lastAccess")
                    if last_access_ms:
                        last_access = datetime.fromtimestamp(last_access_ms / 1000.0, tz=timezone.utc)

                # Assemble the user details
                enriched_users.append({
                    "id": user_id,
                    "username": user.get("username"),
                    "roles": roles,
                    "ipaddress": ip_address,
                    "lastaccess": last_access
                })
                
            return enriched_users
            
        except KeycloakError as e:
            print(f"Failed to communicate with Keycloak: {e}")
            raise
