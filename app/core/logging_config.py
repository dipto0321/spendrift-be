import json
import logging

from app.core.config import settings


def setup_logging():
    """Setup structured logging configuration."""
    
    class JSONFormatter(logging.Formatter):
        """Format logs as JSON."""
        
        def format(self, record: logging.LogRecord) -> str:
            log_data = {
                "timestamp": self.formatTime(record),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            if record.exc_info:
                log_data["exception"] = self.formatException(record.exc_info)
            return json.dumps(log_data)
    
    class TextFormatter(logging.Formatter):
        """Format logs as plain text."""
        
        def format(self, record: logging.LogRecord) -> str:
            return (
                f"[{self.formatTime(record)}] {record.levelname} - "
                f"{record.name} - {record.getMessage()}"
            )
    
    # Remove existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler
    console_handler = logging.StreamHandler()
    
    # Set formatter based on config
    if settings.log_format.lower() == "json":
        formatter = JSONFormatter()
    else:
        formatter = TextFormatter()
    
    console_handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger.setLevel(settings.log_level.upper())
    root_logger.addHandler(console_handler)
    
    # Set FastAPI and SQLAlchemy loggers
    logging.getLogger("fastapi").setLevel(settings.log_level.upper())
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
