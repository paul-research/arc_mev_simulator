#!/usr/bin/env python3
"""
Basic MEV Simulation Example

Demonstrates basic MEV simulation setup and execution.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def create_basic_config():
    """Create a basic simulation configuration"""
    return {
        "simulation": {
            "name": "basic_example",
            "duration_minutes": 2.0,
            "target_transactions": 10,
            "output_dir": "data/results"
        },
        "network": {
            "name": "development",
            "rpc_url": "http://127.0.0.1:8545",
            "chain_id": 31337,
            "gas_price_gwei": 20
        },
        "mev_bots": {
            "enabled": True,
            "count": 2,
            "bot1": {
                "strategy": "aggressive",
                "initial_balance_eth": 1.0,
                "latency_profile": "fast"
            },
            "bot2": {
                "strategy": "conservative",
                "initial_balance_eth": 1.0,
                "latency_profile": "medium"
            }
        },
        "victim_transactions": {
            "enabled": True,
            "count": 2,
            "traders": {
                "retail_victim": {
                    "type": "retail",
                    "initial_balances": {
                        "TOKEN1": 1000,
                        "TOKEN2": 2000,
                        "ETH": 5.0
                    }
                },
                "whale_victim": {
                    "type": "whale", 
                    "initial_balances": {
                        "TOKEN1": 5000,
                        "TOKEN2": 10000,
                        "ETH": 20.0
                    }
                }
            }
        },
        "pools": {
            "token_a": {
                "name": "Token1",
                "symbol": "TOKEN1",
                "decimals": 18,
                "total_supply": 1000000
            },
            "token_b": {
                "name": "Token2",
                "symbol": "TOKEN2", 
                "decimals": 18,
                "total_supply": 1000000
            },
            "uniswap_v3": {
                "fee_tier": 3000,
                "initial_price_ratio": "1:2",
                "liquidity": {
                    "amount_token_a": 1000,
                    "amount_token_b": 2000
                }
            }
        }
    }

async def run_basic_simulation():
    """Run a basic MEV simulation"""
    print("Starting Basic MEV Simulation")
    
    config = create_basic_config()
    
    # Check environment
    if os.getenv('DEPLOYER_PRIVATE_KEY'):
        print("Using Arc Testnet environment")
        config["network"] = {
            "name": "arc_testnet",
            "rpc_url": "https://arc-testnet.stg.blockchain.circle.com",
            "chain_id": 1337,
            "gas_price_gwei": 300,
            "contracts": {
                "paul_king_token": "0x6911406ae5C9fa9314B4AEc086304c001fb3b656",
                "paul_queen_token": "0x3eaE1139A9A19517B0dB5696073d957542886BF8",
                "uniswap_pool": "0x39A9Ba5F012aB6D6fc90E563C72bD85949Ca0FF6"
            }
        }
    else:
        print("Using development environment (requires Anvil)")
        print("To use Arc Testnet, set DEPLOYER_PRIVATE_KEY environment variable")
    
    try:
        from src.core.simulator import MEVSimulator
        from src.utils.helpers import setup_logging
        
        setup_logging("INFO")
        
        # Initialize simulator
        simulator = MEVSimulator(config)
        
        # Setup simulation (this would fail without actual blockchain)
        print("Note: This example shows configuration setup.")
        print("For full execution, use: python scripts/run_complete_simulation.py")
        
        print("Configuration loaded successfully:")
        print(f"- Network: {config['network']['name']}")
        print(f"- MEV Bots: {config['mev_bots']['count']}")
        print(f"- Victims: {config['victim_transactions']['count']}")
        print(f"- Duration: {config['simulation']['duration_minutes']} minutes")
        
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        return False

def main():
    """Main entry point"""
    try:
        success = asyncio.run(run_basic_simulation())
        if success:
            print("\nBasic simulation configuration test passed!")
            print("To run full simulation:")
            print("  python scripts/run_complete_simulation.py --environment development --quick-test")
            return 0
        else:
            return 1
    except Exception as e:
        print(f"Failed: {e}")
        return 1

if __name__ == "__main__":
    exit(main())