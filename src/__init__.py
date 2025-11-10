"""
MEV-Simulator
PBS research platform
paul.kwon@circle.com
"""

__version__ = "0.1.0"
__author__ = "Circle Research"
__email__ = "paul.kwon@circle.com"

# Core imports
from .core.simulator import MEVSimulator
from .core.mev_bot import MEVBot
from .core.pool_manager import PoolManager
from .core.latency_simulator import LatencySimulator

# Deployment
from .deployment.deployer import ContractDeployer

# Analysis
from .analysis.analyzer import MEVAnalyzer
from .analysis.visualizer import MEVVisualizer

# Utils
from .utils.blockchain import BlockchainClient
from .utils.helpers import setup_logging, format_currency, calculate_slippage

__all__ = [
    "__version__",
    "__author__", 
    "__email__",
    "MEVSimulator",
    "MEVBot", 
    "PoolManager",
    "LatencySimulator",
    "ContractDeployer",
    "MEVAnalyzer",
    "MEVVisualizer",
    "BlockchainClient",
    "setup_logging",
    "format_currency", 
    "calculate_slippage"
]

# Setup default logging
import logging

def _setup_default_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    logging.getLogger('web3').setLevel(logging.WARNING)
    logging.getLogger('eth_account').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)

_setup_default_logging()

PACKAGE_INFO = {
    "name": "MEV-Simulator",
    "version": __version__,
    "description": "PBS research platform",
    "author": __author__,
    "email": __email__,
    "license": "MIT",
    "url": "https://github.com/paul-research/arc_mev_simulator",
    "keywords": ["MEV", "PBS", "Circle", "research"]
}



