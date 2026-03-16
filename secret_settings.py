import logging
from typing import Any, Tuple
from pydantic_settings import PydanticBaseSettingsSource
from pydantic.fields import FieldInfo

from exceptions import SecretNotFoundError
from manager import InfisicalSecretManager

logger = logging.getLogger("infisical_settings")
logging.basicConfig(level=logging.INFO)


class InfisicalSettingsSource(PydanticBaseSettingsSource):
    def __init__(self, settings_cls, manager: InfisicalSecretManager):
        super().__init__(settings_cls)
        self.manager = manager
        self.validated_keys = []

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> Tuple[Any, str, bool]:
        logger.info(f"🔍 Checking Infisical for setting: '{field_name}'...")
        is_required = field.is_required()

        try:
            val = self.manager.get_value(key=field_name, required=is_required)

            if val is None and not is_required:
                logger.warning(
                    f"Secret '{field_name}' not found, but it is optional. Using default."
                )
                return None, field_name, False

            self.validated_keys.append(field_name)
            logger.info(f"Successfully retrieved '{field_name}' from Infisical.")
            return val, field_name, False

        except SecretNotFoundError as e:
            logger.error(f"Required secret '{field_name}' is missing from Infisical!")
            raise ValueError(
                f"\n\nApplication startup failed: Required secret '{field_name}' not found "
                f"in Infisical environment '{self.manager.default_env}'.\n"
                f"Original error: {e}"
            ) from e

    def __call__(self) -> dict[str, Any]:
        d: dict[str, Any] = {}

        for field_name, field in self.settings_cls.model_fields.items():
            field_value, field_key, value_is_complex = self.get_field_value(
                field, field_name
            )
            if field_value is not None:
                d[field_key] = field_value

        # Emit the bulk validation event required at startup
        if self.validated_keys:
            self.manager._emit_event(
                operation_name="App Startup Validation Complete",
                key=str(self.validated_keys),
                status="SUCCESS",
                source="remote",
            )

        return d
