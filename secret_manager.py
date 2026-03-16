import os
import logging
from typing import Optional
from cachetools import TTLCache

from infisical_sdk import InfisicalSDKClient
from langfuse import get_client

from exceptions import SecretNotFoundError, SecretMutationError, SecretAccessError

logger = logging.getLogger("infisical_manager")

class InfisicalSecretManager:
    def __init__(
        self, 
        project_id: str,
        client_id: str,
        client_secret: str,
        site_url: str = "https://app.infisical.com",
        cache_ttl_seconds: int = 300, 
        cache_max_size: int = 1000,
        default_env: str = "dev"
    ):
        self.project_id = project_id
        self.client_id = client_id
        self.site_url = site_url.rstrip("/")
        self.default_env = default_env
        self._cache = TTLCache(maxsize=cache_max_size, ttl=cache_ttl_seconds)
        
        self.client_name = os.getenv("INFISICAL_CLIENT_NAME", f"Machine-Identity-{self.client_id[:8]}")
        
        self.client = InfisicalSDKClient(host=self.site_url, cache_ttl=None)
        self.client.auth.universal_auth.login(
            client_id=self.client_id,
            client_secret=client_secret
        )

    def _emit_event(
        self, 
        operation_name: str, 
        key: str, 
        status: str, 
        target_env: Optional[str] = None, 
        source: Optional[str] = None, 
        error_msg: Optional[str] = None,
        level: str = "DEFAULT"
    ) -> None:
        """Centralized helper to emit tracing events to Langfuse."""
        target_env = target_env or self.default_env
        try:
            client = get_client()
            
            output_data = {"variable": key, "status": status}
            if source:
                output_data["source"] = source
                
            metadata = {
                "client_id": self.client_id,
                "client_name": self.client_name,
                "target_env": target_env,
            }
            if error_msg:
                metadata["error_message"] = error_msg

            with client.start_as_current_observation(name=operation_name) as obs:
                obs.update(
                    input={"accessor": self.client_name, "environment": target_env},
                    output=output_data,
                    metadata=metadata,
                    level=level
                )

            client.flush()
        except Exception as e:
            logger.error(f"Failed to emit Langfuse event for {operation_name}: {e}")

    def get_value(self, key: str, env: Optional[str] = None, required: bool = True) -> Optional[str]:
        target_env = env or self.default_env
        cache_key = f"{target_env}:{key}"

        if cache_key in self._cache:
            self._emit_event(
                operation_name="get_value", 
                key=key, 
                status="SUCCESS", 
                target_env=target_env, 
                source="cache"
            )
            return self._cache[cache_key]

        try:
            secret = self.client.secrets.get_secret_by_name(
                secret_name=key, 
                environment_slug=target_env, 
                project_id=self.project_id,
                secret_path="/"
            )
            
            val = getattr(secret, "secret_value", getattr(secret, "secretValue", None))
            self._cache[cache_key] = val
            self._emit_event(
                operation_name="get_value", 
                key=key, 
                status="SUCCESS", 
                target_env=target_env, 
                source="remote"
            )
            return val
            
        except Exception as e:
            error_msg = str(e)
            is_not_found = "not found" in error_msg.lower() or "404" in error_msg
            
            if is_not_found and not required:
                self._emit_event(
                    operation_name="get_value", 
                    key=key, 
                    status="OPTIONAL_FALLBACK", 
                    target_env=target_env,
                    source="default",
                    level="WARNING"
                )
                return None

            self._emit_event(
                operation_name="get_value", 
                key=key, 
                status="FAILED", 
                target_env=target_env, 
                error_msg=error_msg,
                level="ERROR"
            )
            
            if is_not_found:
                raise SecretNotFoundError(f"Secret '{key}' not found in '{target_env}'.") from e
            raise SecretAccessError(f"Error accessing '{key}': {error_msg}") from e

    def create_secret(self, key: str, value: str, env: Optional[str] = None) -> None:
        target_env = env or self.default_env
        try:
            self.client.secrets.create_secret_by_name(
                secret_name=key,
                secret_value=value,
                environment_slug=target_env,
                project_id=self.project_id,
                secret_path="/"
            )
            self._cache[f"{target_env}:{key}"] = value
            self._emit_event("create_secret", key, "SUCCESS", target_env)
            
        except Exception as e:
            self._emit_event("create_secret", key, "FAILED", target_env, error_msg=str(e), level="ERROR")
            raise SecretMutationError(f"Failed to create '{key}': {e}") from e

    def update_secret(self, key: str, new_value: str, env: Optional[str] = None) -> None:
        target_env = env or self.default_env
        try:
            self.client.secrets.update_secret_by_name(
                current_secret_name=key,
                secret_value=new_value,
                environment_slug=target_env,
                project_id=self.project_id,
                secret_path="/"
            )
            self._cache[f"{target_env}:{key}"] = new_value
            self._emit_event("update_secret", key, "SUCCESS", target_env)
            
        except Exception as e:
            self._emit_event("update_secret", key, "FAILED", target_env, error_msg=str(e), level="ERROR")
            raise SecretMutationError(f"Failed to update '{key}': {e}") from e

    def delete_secret(self, key: str, env: Optional[str] = None) -> None:
        target_env = env or self.default_env
        try:
            self.client.secrets.delete_secret_by_name(
                secret_name=key,
                environment_slug=target_env,
                project_id=self.project_id,
                secret_path="/"
            )
            self._cache.pop(f"{target_env}:{key}", None)
            self._emit_event("delete_secret", key, "SUCCESS", target_env)
            
        except Exception as e:
            self._emit_event("delete_secret", key, "FAILED", target_env, error_msg=str(e), level="ERROR")
            raise SecretMutationError(f"Failed to delete '{key}': {e}") from e
