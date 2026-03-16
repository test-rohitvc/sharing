
# Infisical Pydantic Tracing Manager

A robust, production-ready secret management library that seamlessly integrates **Infisical** (for secret storage), **Pydantic** (for configuration validation), and **Langfuse** (for observability and tracing).

This library allows you to strongly type your environment variables, automatically fetch them from Infisical on startup, cache them to reduce API calls, and emit detailed traces to Langfuse without cluttering your application code.

## Features

* **Pydantic Integration:** Automatically maps Infisical secrets to your Pydantic `BaseSettings` models.
* **Smart Fallbacks:** Distinguishes between `required` and `optional` fields. Fails loudly on startup if a required secret is missing, but gracefully falls back to Pydantic defaults for optional ones.
* **Built-in TTL Caching:** Uses `cachetools` to temporarily store secrets in memory, preventing rate limits and speeding up repeated secret access.
* **Langfuse Observability:** Centralized tracing for all secret operations (`get`, `create`, `update`, `delete`). Automatically categorizes missing optional variables as `WARNING`s rather than `ERROR`s in your Langfuse dashboard.
* **Secret Mutation:** Direct methods to create, update, and delete secrets in Infisical programmatically.

---

## Prerequisites

Ensure you have the following dependencies installed in your Python environment:

```bash
pip install ai-levate

```

*Note: You must have Langfuse environment variables (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`) set in your environment for tracing to work.*

---

## Quick Start

Here is a complete example of how to configure your application to use the `InfisicalSecretManager` and `InfisicalSettingsSource`.

```python
from dotenv import load_dotenv
load_dotenv()

from pydantic_settings import BaseSettings
from ai_leavte.secrets_manager import InfisicalSecretManager
from ai_leavte.secrets_manager import InfisicalSettingsSource

# 1. Initialize the Secret Manager
secret_manager = InfisicalSecretManager(
    site_url="https://app.infisical.com", # Or your self-hosted URL
    client_id="<YOUR_MACHINE_IDENTITY_CLIENT_ID>",
    client_secret="<YOUR_MACHINE_IDENTITY_CLIENT_SECRET>",
    project_id="<YOUR_INFISICAL_PROJECT_ID>",
    cache_ttl_seconds=300,
    default_env="prod"
)

# 2. Define your Application Settings
class AppConfig(BaseSettings):
    # Required keys: App will crash on boot if missing in Infisical
    DATABASE_URL: str             
    OPENAI_API_KEY: str          
    
    # Optional keys: Will default to False if not found in Infisical
    ENABLE_FEATURE_X: bool = False 

    @classmethod
    def settings_customise_sources(
        cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings
    ):
        # Override standard settings sources to use Infisical
        return (InfisicalSettingsSource(settings_cls, manager=secret_manager),)

# 3. Instantiate the config (Triggers Infisical fetch & Langfuse validation event)
config = AppConfig()

print(f"Connected to DB: {config.DATABASE_URL}")
print(f"Feature X Enabled: {config.ENABLE_FEATURE_X}")

```

---

## Core Components

### `InfisicalSecretManager`

The core engine responsible for communicating with the Infisical SDK.

* **Caching:** By default, caches secrets for 300 seconds (configurable via `cache_ttl_seconds`).
* **Client Naming:** Uses the `INFISICAL_CLIENT_NAME` environment variable for Langfuse trace attribution, or falls back to a truncated Client ID.

### `InfisicalSettingsSource`

The bridge between Pydantic and the Manager.

* When you instantiate your `BaseSettings` class, this source loops through every field.
* If a field is missing but has a default (e.g., `ENABLE_FEATURE_X: bool = False`), it suppresses the error and uses the default.
* Upon successful completion, it logs a bulk `App Startup Validation Complete` trace to Langfuse.

---

## Langfuse Tracing Behavior

This library is highly optimized for clean observability dashboards. Here is how events appear in Langfuse based on the scenario:

| Scenario | Langfuse Operation Name | Status | Level | Source |
| --- | --- | --- | --- | --- |
| Secret found in Cache | `get_value` | `SUCCESS` | `DEFAULT` | `cache` |
| Secret found in Infisical | `get_value` | `SUCCESS` | `DEFAULT` | `remote` |
| **Optional** secret missing | `get_value` | `OPTIONAL_FALLBACK` | `WARNING` | `default` |
| **Required** secret missing | `get_value` | `FAILED` | `ERROR` | N/A |
| Successful mutation | `create_secret` / `update_secret` | `SUCCESS` | `DEFAULT` | N/A |
| All secrets loaded | `App Startup Validation Complete` | `SUCCESS` | `DEFAULT` | `remote` |

---

## Secret Mutations

You can mutate secrets dynamically during application runtime. These operations bypass the Pydantic configuration and talk directly to the cache and Infisical.

```python
# Create a new secret
secret_manager.create_secret(key="NEW_API_KEY", value="sk-12345", env="prod")

# Update an existing secret
secret_manager.update_secret(key="OPENAI_API_KEY", new_value="sk-new-key", env="prod")

# Delete a secret
secret_manager.delete_secret(key="OLD_API_KEY", env="prod")

```

*Note: Mutations automatically update the local `TTLCache` to ensure subsequent `get_value` calls return the freshest data without needing an API round-trip.*

---

## Exceptions

If you are interacting with the `InfisicalSecretManager` directly (outside of Pydantic), you can catch the following custom exceptions from `exceptions.py`:

* `SecretNotFoundError`: Raised when a required secret is completely missing.
* `SecretAccessError`: Raised for authentication, network, or permission (403) errors.
* `SecretMutationError`: Raised when creating, updating, or deleting a secret fails.
