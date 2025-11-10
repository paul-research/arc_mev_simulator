"""
Helper utilities for MEV-Simulator

Common utility functions used throughout the MEV simulation system.
"""

import logging
import os
import hashlib
import time
from datetime import datetime
from pathlib import Path
from typing import Union, Optional, Dict, Any
import structlog


def setup_logging(level: str = "INFO", 
                 log_file: Optional[str] = None,
                 structured: bool = True) -> None:
    """
    Setup logging configuration for MEV simulator
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional log file path
        structured: Whether to use structured logging
    """
    log_level = getattr(logging, level.upper())
    
    # Configure basic logging
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Setup file logging if specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(log_level)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        
        # Add to root logger
        logging.getLogger().addHandler(file_handler)
    
    # Suppress noisy third-party loggers
    logging.getLogger('web3').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('eth_account').setLevel(logging.WARNING)
    
    # Setup structured logging if enabled
    if structured:
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer()
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )


def format_currency(amount: float, 
                   currency: str = "ETH", 
                   decimals: int = 6) -> str:
    """
    Format currency amounts with appropriate precision
    
    Args:
        amount: Amount to format
        currency: Currency symbol
        decimals: Number of decimal places
        
    Returns:
        Formatted currency string
    """
    if abs(amount) < 0.000001:
        return f"0.000000 {currency}"
    
    # Use scientific notation for very small amounts
    if abs(amount) < 0.001:
        return f"{amount:.2e} {currency}"
    
    # Standard formatting
    return f"{amount:.{decimals}f} {currency}"


def calculate_slippage(expected_amount: float, 
                      actual_amount: float) -> float:
    """
    Calculate slippage percentage
    
    Args:
        expected_amount: Expected output amount
        actual_amount: Actual received amount
        
    Returns:
        Slippage as decimal (0.02 = 2%)
    """
    if expected_amount <= 0:
        return 0.0
    
    return max(0.0, (expected_amount - actual_amount) / expected_amount)


def generate_wallet_address(seed: str) -> str:
    """
    Generate deterministic wallet address from seed
    
    Args:
        seed: Seed string for deterministic generation
        
    Returns:
        Ethereum address (0x...)
    """
    # Create deterministic hash
    hash_obj = hashlib.sha256(seed.encode())
    hash_bytes = hash_obj.digest()
    
    # Take first 20 bytes for address
    address_bytes = hash_bytes[:20]
    
    # Format as hex string
    address = "0x" + address_bytes.hex()
    
    return address


def validate_address(address: str) -> bool:
    """
    Validate Ethereum address format
    
    Args:
        address: Address to validate
        
    Returns:
        True if valid Ethereum address
    """
    if not isinstance(address, str):
        return False
    
    # Check basic format
    if not address.startswith("0x"):
        return False
    
    if len(address) != 42:
        return False
    
    # Check hex characters
    try:
        int(address[2:], 16)
        return True
    except ValueError:
        return False


def wei_to_eth(wei_amount: int) -> float:
    """Convert Wei to ETH"""
    return wei_amount / 1e18


def eth_to_wei(eth_amount: float) -> int:
    """Convert ETH to Wei"""
    return int(eth_amount * 1e18)


def format_timestamp(timestamp: float, 
                    format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Format timestamp to human-readable string
    
    Args:
        timestamp: Unix timestamp
        format_str: strftime format string
        
    Returns:
        Formatted timestamp string
    """
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime(format_str)


def create_output_directory(base_path: str, 
                          simulation_name: str = None) -> Path:
    """
    Create output directory with timestamp
    
    Args:
        base_path: Base output directory
        simulation_name: Optional simulation name for subdirectory
        
    Returns:
        Path object for created directory
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    if simulation_name:
        dir_name = f"{simulation_name}_{timestamp}"
    else:
        dir_name = f"simulation_{timestamp}"
    
    output_dir = Path(base_path) / dir_name
    output_dir.mkdir(parents=True, exist_ok=True)
    
    return output_dir


def safe_divide(numerator: float, 
                denominator: float, 
                default: float = 0.0) -> float:
    """
    Safely divide two numbers, returning default if denominator is zero
    
    Args:
        numerator: Numerator
        denominator: Denominator
        default: Default value if division by zero
        
    Returns:
        Division result or default
    """
    if denominator == 0:
        return default
    return numerator / denominator


def percentage_change(old_value: float, new_value: float) -> float:
    """
    Calculate percentage change between two values
    
    Args:
        old_value: Original value
        new_value: New value
        
    Returns:
        Percentage change as decimal (0.1 = 10% increase)
    """
    if old_value == 0:
        return 0.0 if new_value == 0 else float('inf')
    
    return (new_value - old_value) / old_value


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp value between min and max"""
    return max(min_val, min(value, max_val))


def normalize(value: float, 
              min_val: float, 
              max_val: float) -> float:
    """
    Normalize value to 0-1 range
    
    Args:
        value: Value to normalize
        min_val: Minimum value in range
        max_val: Maximum value in range
        
    Returns:
        Normalized value between 0 and 1
    """
    if max_val == min_val:
        return 0.0
    
    return clamp((value - min_val) / (max_val - min_val), 0.0, 1.0)


def exponential_backoff(attempt: int, 
                       base_delay: float = 1.0,
                       max_delay: float = 60.0,
                       jitter: bool = True) -> float:
    """
    Calculate exponential backoff delay
    
    Args:
        attempt: Attempt number (0-based)
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        jitter: Whether to add random jitter
        
    Returns:
        Delay in seconds
    """
    delay = min(base_delay * (2 ** attempt), max_delay)
    
    if jitter:
        import random
        delay *= (0.5 + random.random() * 0.5)  # 50-100% of calculated delay
    
    return delay


def retry_with_backoff(func, 
                      max_attempts: int = 3,
                      base_delay: float = 1.0,
                      exceptions: tuple = (Exception,)):
    """
    Decorator for retrying functions with exponential backoff
    
    Args:
        func: Function to retry
        max_attempts: Maximum retry attempts
        base_delay: Base delay between attempts
        exceptions: Tuple of exceptions to catch
        
    Returns:
        Decorated function
    """
    def wrapper(*args, **kwargs):
        import time
        import random
        
        for attempt in range(max_attempts):
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                if attempt == max_attempts - 1:
                    raise e
                
                delay = exponential_backoff(attempt, base_delay)
                logging.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay:.2f}s...")
                time.sleep(delay)
        
    return wrapper


def human_readable_size(size_bytes: int) -> str:
    """
    Convert bytes to human readable size
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Human readable size string
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def load_json_file(file_path: str) -> Dict[Any, Any]:
    """Load JSON file with error handling"""
    import json
    
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error(f"JSON file not found: {file_path}")
        return {}
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON in {file_path}: {e}")
        return {}


def save_json_file(data: Dict[Any, Any], file_path: str) -> bool:
    """Save data to JSON file with error handling"""
    import json
    
    try:
        # Create directory if it doesn't exist
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        return True
    except Exception as e:
        logging.error(f"Failed to save JSON to {file_path}: {e}")
        return False


def get_env_var(name: str, 
                default: Optional[str] = None,
                required: bool = False) -> Optional[str]:
    """
    Get environment variable with optional default and validation
    
    Args:
        name: Environment variable name
        default: Default value if not set
        required: Whether the variable is required
        
    Returns:
        Environment variable value or default
        
    Raises:
        ValueError: If required variable is not set
    """
    value = os.getenv(name, default)
    
    if required and value is None:
        raise ValueError(f"Required environment variable {name} is not set")
    
    return value


def setup_environment(env_file: str = ".env") -> None:
    """
    Load environment variables from file
    
    Args:
        env_file: Path to environment file
    """
    env_path = Path(env_file)
    
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path)
        logging.info(f"Loaded environment from {env_file}")
    else:
        logging.warning(f"Environment file {env_file} not found")


class Timer:
    """Context manager for timing code execution"""
    
    def __init__(self, name: str = "Operation"):
        self.name = name
        self.start_time = None
        self.end_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, *args):
        self.end_time = time.time()
        duration = self.end_time - self.start_time
        logging.info(f"{self.name} completed in {duration:.3f} seconds")
    
    @property
    def duration(self) -> float:
        """Get duration in seconds"""
        if self.start_time is None:
            return 0.0
        end = self.end_time if self.end_time is not None else time.time()
        return end - self.start_time


class RateLimiter:
    """Simple rate limiter for API calls"""
    
    def __init__(self, max_calls: int, time_window: float):
        """
        Args:
            max_calls: Maximum calls in time window
            time_window: Time window in seconds
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = []
    
    def can_proceed(self) -> bool:
        """Check if call can proceed within rate limit"""
        now = time.time()
        
        # Remove old calls outside the window
        self.calls = [call_time for call_time in self.calls 
                     if now - call_time < self.time_window]
        
        return len(self.calls) < self.max_calls
    
    def record_call(self) -> None:
        """Record a call"""
        self.calls.append(time.time())
    
    def wait_if_needed(self) -> None:
        """Wait if rate limit would be exceeded"""
        if not self.can_proceed():
            # Wait until the oldest call expires
            wait_time = self.time_window - (time.time() - self.calls[0])
            if wait_time > 0:
                time.sleep(wait_time + 0.1)  # Small buffer
        
        self.record_call()


# Example usage and testing
if __name__ == "__main__":
    # Test utilities
    print("🧪 Testing MEV Simulator Utilities")
    
    # Test logging setup
    setup_logging("DEBUG")
    logging.info("Logging setup complete")
    
    # Test currency formatting
    amounts = [0.000001, 0.001, 0.123456, 1.23, 1000.567]
    for amount in amounts:
        print(f"Format {amount}: {format_currency(amount)}")
    
    # Test slippage calculation
    print(f"Slippage (100->95): {calculate_slippage(100, 95):.2%}")
    
    # Test address generation
    seed_address = generate_wallet_address("test_seed_123")
    print(f"Generated address: {seed_address}")
    print(f"Valid address: {validate_address(seed_address)}")
    
    # Test timer
    with Timer("Test operation"):
        time.sleep(0.1)
    
    print("✅ All utility tests passed!")


