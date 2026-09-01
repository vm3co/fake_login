import os
import sys
import time
import logging
from functools import wraps


class Logger:
    """Singleton logger class for outputting logs to the console and a file.

    This class ensures that only one logger instance is created (singleton pattern)
    and provides methods to retrieve the configured logger.

    Attributes:
        logger (logging.Logger): The logger instance.
    """
    _instance = None  # For singleton pattern

    def __new__(cls, enable_console=True, enable_file=True, *args, **kwargs):
        """Create a new Logger instance if one does not already exist.

        Args:
            enable_console (bool): Flag to enable logging to the console.
            enable_file (bool): Flag to enable logging to a file.
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments.

        Returns:
            Logger: The singleton instance of the Logger class.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._enable_console_flag = enable_console
            cls._instance._enable_file_flag = enable_file
        return cls._instance

    def __init__(self, enable_console=True, enable_file=True):
        """Initialize the Logger instance.

        This method sets up the logger, configuring handlers for both console and file outputs.
        If the instance is already initialized, the method returns without doing anything.

        Args:
            enable_console (bool, optional): Enable console output. Defaults to True.
            enable_file (bool, optional): Enable file output. Defaults to True.
        """
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._initialized = True

        # Create a logger instance.
        self.logger = logging.getLogger(__name__)

        if not self.logger.handlers:
            formatter = logging.Formatter("%(asctime)s-%(levelname)s: %(message)s")
            self.logger.setLevel(logging.DEBUG)

            # Handler settings for the command line output.
            if self._enable_console_flag:
                console_handler = logging.StreamHandler(sys.stdout)
                console_handler.setFormatter(formatter)
                console_handler.setLevel(logging.DEBUG)  # Set the level of the commandline handler
                self.logger.addHandler(console_handler)

            # Handler settings for file output.
            if self._enable_file_flag:
                curr_date = time.strftime("%Y%m%d")
                log_path = './Logger'
                log_name = f'{curr_date}.log'
                log_file = os.path.join(log_path, log_name)
                os.makedirs(log_path, exist_ok=True)
                file_handler = logging.FileHandler(log_file)
                file_handler.setLevel(logging.DEBUG)  # Set the level of the file handler
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)

    def get_logger(self) -> logging.Logger:
        """Get the configured logger instance."""
        return self.logger


def timelog(func):
    """Decorator that logs the execution time of a function.
    Args:
        func (Callable): The function to wrap.
    Returns:
        Callable: The wrapped function with execution time logging. 
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger = Logger().get_logger()
        logger.info(f'[Phase: {func.__name__}] ------------- START')
        start_time = time.time()
        try:
            return func(*args, **kwargs)
        finally:
            execution_time = time.time() - start_time
            logger.info(f"[Phase: {func.__name__}] ------------- END in {execution_time:.3f}(s)")
    return wrapper


if __name__ == "__main__":

    @timelog
    def example(test_str):
        print("processinng...")
        time.sleep(2)
        print(test_str)
        print("done")

    logger = Logger(enable_console=True, enable_file=True).get_logger()
    logger.debug("Start")
    example("Hello World!!")
    logger.debug("End")
