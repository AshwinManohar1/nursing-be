import logging
import sys

class Logger:
    def __init__(self, name: str = "document_extractor"):
        self.logger = logging.getLogger(name)
        
        # Avoid adding handlers multiple times
        if not self.logger.handlers:
            self.logger.setLevel(logging.INFO)
            
            # Create console handler
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            
            # Create formatter
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            console_handler.setFormatter(formatter)
            
            # Add handler to logger
            self.logger.addHandler(console_handler)
            
            # Prevent propagation to avoid duplicate logs
            self.logger.propagate = False

    def info(self, message: str):
        """Log info message"""
        self.logger.info(message)

    def error(self, message: str, exc_info=False):
        """Log error message"""
        self.logger.error(message, exc_info=exc_info)
    
    def exception(self, message: str):
        """Log error message with exception info"""
        self.logger.exception(message)

    def debug(self, message: str):
        """Log debug message"""
        self.logger.debug(message)

    def warning(self, message: str):
        """Log warning message"""
        self.logger.warning(message)


# Create default logger instance
logger = Logger()

# Convenience function to get logger with custom name
def get_logger(name: str = "document_extractor") -> Logger:
    return Logger(name)