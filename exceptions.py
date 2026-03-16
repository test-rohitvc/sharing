class SecretManagerError(Exception):
    """Base exception for secret management errors."""
    pass

class SecretNotFoundError(SecretManagerError):
    """Raised when a secret cannot be found in Infisical or Cache."""
    pass

class SecretAccessError(SecretManagerError):
    """Raised when there is an authentication or network error accessing Infisical."""
    pass

class SecretMutationError(SecretManagerError):
    """Raised when creating, updating, or deleting a secret fails."""
    pass
