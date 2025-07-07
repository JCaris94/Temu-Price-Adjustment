import logging
import os
from datetime import datetime
from colorama import Fore, Style, init
from config import Config

init(autoreset=True)

LOG_COLORS = {
    'INFO': Fore.CYAN,
    'WARNING': Fore.YELLOW,
    'ERROR': Fore.RED,
    'CRITICAL': Fore.RED + Style.BRIGHT,
    'DEBUG': Fore.GREEN,
    'SUCCESS': Fore.GREEN + Style.BRIGHT,
    'VERBOSE': Fore.MAGENTA
}

class ColoredFormatter(logging.Formatter):
    def format(self, record):
        timestamp = datetime.now().strftime('%d.%m.%Y - %H:%M:%S')
        levelname = record.levelname
        message = super().format(record)
        
        if levelname in LOG_COLORS:
            color = LOG_COLORS[levelname]
            levelname = f"{color}{levelname}{Style.RESET_ALL}"
        
        return f"{Fore.LIGHTBLACK_EX}{timestamp}{Style.RESET_ALL} - {levelname} - {message}"

def setup_logger(verbose=False):
    logger = logging.getLogger("temu_bot")
    logger.handlers = []
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    
    # Console handler
    ch = logging.StreamHandler()
    ch_formatter = ColoredFormatter('%(message)s')
    ch.setFormatter(ch_formatter)
    logger.addHandler(ch)
    
    # File handler (overwrite each run)
    config = Config()
    fh = logging.FileHandler(config.LOG_FILE, mode='w')
    fh_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%d.%m.%Y - %H:%M:%S'
    )
    fh.setFormatter(fh_formatter)
    logger.addHandler(fh)
    
    # Custom success log level
    logging.addLevelName(25, "SUCCESS")
    if not hasattr(logger, 'success'):
        setattr(logger, 'success', lambda message, *args: logger._log(25, message, args))
    
    # Custom verbose log level
    logging.addLevelName(5, "VERBOSE")
    if not hasattr(logger, 'verbose'):
        setattr(logger, 'verbose', lambda message, *args: logger._log(5, message, args))
    
    return logger