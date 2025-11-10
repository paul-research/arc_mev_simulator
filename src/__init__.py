"""
MEV-Simulator: A Research Platform for Maximal Extractable Value Analysis

This package provides comprehensive tools for:
- MEV bot simulation and competition analysis
- Blockchain pool deployment and management  
- Latency modeling and network effects
- Revenue sharing and user protection research
- Statistical analysis and visualization

Core Components:
- core: Simulation engine and MEV bot logic
- deployment: Smart contract deployment tools
- analysis: Data analysis and visualization  
- utils: Helper utilities and blockchain interaction
"""

__version__ = "0.1.0"
__author__ = "Arc Research Team"
__email__ = "research@arc.network"

# Core imports for easy access
from .core.simulator import MEVSimulator
from .core.mev_bot import MEVBot
from .core.pool_manager import PoolManager
from .core.latency_simulator import LatencySimulator

# Deployment tools
from .deployment.deployer import ContractDeployer

# Analysis tools  
from .analysis.analyzer import MEVAnalyzer
from .analysis.visualizer import MEVVisualizer

# Utilities
from .utils.blockchain import BlockchainClient
from .utils.helpers import setup_logging, format_currency, calculate_slippage

__all__ = [
    # Version info
    "__version__",
    "__author__", 
    "__email__",
    
    # Core components
    "MEVSimulator",
    "MEVBot", 
    "PoolManager",
    "LatencySimulator",
    
    # Deployment
    "ContractDeployer",
    
    # Analysis
    "MEVAnalyzer",
    "MEVVisualizer",
    
    # Utils
    "BlockchainClient",
    "setup_logging",
    "format_currency", 
    "calculate_slippage"
]

# Package-level configuration
import logging

# Setup default logging
def _setup_default_logging():
    """Setup default logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Set third-party loggers to WARNING to reduce noise
    logging.getLogger('web3').setLevel(logging.WARNING)
    logging.getLogger('eth_account').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)

# Initialize logging
_setup_default_logging()

# Package info
PACKAGE_INFO = {
    "name": "MEV-Simulator",
    "version": __version__,
    "description": "A Research Platform for Maximal Extractable Value Analysis",
    "author": __author__,
    "email": __email__,
    "license": "MIT",
    "url": "https://github.com/arc-research/mev-simulator",
    "keywords": ["MEV", "blockchain", "ethereum", "defi", "research", "simulation"]
}


