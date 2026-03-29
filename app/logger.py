import os
import logging
from logging.handlers import RotatingFileHandler

def setup_logging():
    """Setup logging with file rotation (1MB max, 5 copies)"""
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Setup logger
    logger = logging.getLogger('inverter_monitor')
    logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create rotating file handler (1MB max, 5 backup files)
    handler = RotatingFileHandler(
        'logs/inverter_monitor.log',
        maxBytes=1024*1024,  # 1MB
        backupCount=5,
        encoding='utf-8'
    )
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(handler)
    
    return logger

# Initialize logger
logger = setup_logging()

def log_info(message):
    """Log info message"""
    logger.info(message)

def log_error(message):
    """Log error message"""
    logger.error(message)

def log_warning(message):
    """Log warning message"""
    logger.warning(message)


