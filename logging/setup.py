import logging
import json
import contextvars
from datetime import datetime
from logging.handlers import RotatingFileHandler

# 1. Create a Context Variable to hold our Langfuse Trace ID
current_trace_id = contextvars.ContextVar("current_trace_id", default="no_trace")
current_user_id = contextvars.ContextVar("current_user_id", default="system")

# 2. Create a Custom JSON Formatter
class AuditableJSONFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": current_trace_id.get(),
            "user_id": current_user_id.get(),
        }
        
        # Capture exceptions if they occur
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
            
        # Capture any extra kwargs passed to the logger
        if hasattr(record, "extra_data"):
            log_record.update(record.extra_data)

        return json.dumps(log_record)

# 3. Setup the Logger and File Offloading
def setup_logger():
    logger = logging.getLogger("langgraph_app")
    logger.setLevel(logging.DEBUG) # Set to INFO in production

    # Offload to a file, rotating at 10MB, keeping 5 backups
    file_handler = RotatingFileHandler("app_audit.log", maxBytes=10*1024*1024, backupCount=5)
    file_handler.setFormatter(AuditableJSONFormatter())
    
    # Also print to console for local dev
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(AuditableJSONFormatter())

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger

logger = setup_logger()
