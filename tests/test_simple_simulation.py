#!/usr/bin/env python3
"""
Simple MEV simulation test - victim only (no MEV bots attacking yet)
Tests that victim can execute swaps on actual blockchain
"""
import asyncio
import sys
import os
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.core.simulator import MEVSimulator
from src.utils.helpers import setup_logging


async def test_simple_victim_trades():
    print("=" * 70)
    print("Simple Victim Trading Test (Blockchain)")
    print("=" * 70)
    
    # Load config
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yaml')
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Modify config for quick test
    config['simulation']['duration_minutes'] = 5
    config['simulation']['target_transactions'] = 10
    
    # Disable MEV bots for now (test victim only)
    config['mev_bots']['count'] = 0
    config['backrun_bots']['enabled'] = False
    
    # Keep only 1 victim
    config['victim_transactions']['count'] = 1
    victim_traders = list(config['victim_transactions']['traders'].keys())
    for trader_id in victim_traders[1:]:
        del config['victim_transactions']['traders'][trader_id]
    
    # Set faster trading frequency
    first_trader = list(config['victim_transactions']['traders'].values())[0]
    first_trader['custom_pattern']['frequency_seconds'] = 30.0  # Trade every 30 seconds
    first_trader['custom_pattern']['amount_range'] = [10, 50]  # Smaller trades
    
    # Setup logging
    setup_logging('INFO')
    
    # Override network config to use Arc Testnet
    env_config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'environment.yaml')
    with open(env_config_path, 'r') as f:
        env_config = yaml.safe_load(f)
    
    config['network'] = env_config['arc_testnet']['network']
    
    print(f"\n🌐 Network: {config['network']['name']}")
    print(f"📡 RPC: {config['network']['rpc_url']}")
    
    # Create simulator
    simulator = MEVSimulator(config)
    
    print("\n🚀 Setting up simulation...")
    await simulator.setup()
    
    print("\n✅ Setup complete! Running simulation...")
    print("   Duration: 5 minutes")
    print("   Target: 10 victim transactions")
    print("   (No MEV bots - testing victim only)\n")
    
    # Run simulation
    results = await simulator.run_simulation()
    
    print("\n" + "=" * 70)
    print("📊 Simulation Results")
    print("=" * 70)
    print(f"Total Rounds: {len(results)}")
    
    total_victim_trades = sum(len(r.victim_trades) for r in results)
    successful_trades = sum(len([t for t in r.victim_trades if t.executed]) for r in results)
    
    print(f"Victim Trades Attempted: {total_victim_trades}")
    print(f"Successful: {successful_trades}")
    
    if successful_trades > 0:
        print("\n✅ SUCCESS! Victim trades were executed on blockchain!")
        print("\nSample transactions:")
        count = 0
        for r in results:
            for trade in r.victim_trades:
                if trade.executed and trade.tx_hash:
                    print(f"  - TX: {trade.tx_hash}")
                    count += 1
                    if count >= 3:
                        break
            if count >= 3:
                break
    else:
        print("\n❌ No trades were executed")
    
    return successful_trades > 0


if __name__ == "__main__":
    try:
        result = asyncio.run(test_simple_victim_trades())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Simulation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

