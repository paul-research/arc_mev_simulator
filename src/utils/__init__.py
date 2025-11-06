"""
Utility functions and helpers for MEV-Simulator

This module provides common utilities used throughout the MEV simulation system:
- Blockchain interaction helpers
- Logging configuration
- Currency formatting
- Mathematical utilities
- File I/O helpers
"""

from .helpers import (
    setup_logging,
    format_currency,
    calculate_slippage,
    generate_wallet_address,
    validate_address,
    wei_to_eth,
    eth_to_wei,
    format_timestamp,
    create_output_directory
)

from .blockchain import (
    BlockchainClient,
    connect_to_network,
    get_block_info,
    estimate_gas_price,
    wait_for_transaction
)

__all__ = [
    # Helper functions
    "setup_logging",
    "format_currency", 
    "calculate_slippage",
    "generate_wallet_address",
    "validate_address",
    "wei_to_eth",
    "eth_to_wei",
    "format_timestamp",
    "create_output_directory",
    
    # Blockchain utilities
    "BlockchainClient",
    "connect_to_network",
    "get_block_info", 
    "estimate_gas_price",
    "wait_for_transaction"
]

