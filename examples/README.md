# Examples

## Basic Simulation

```bash
python examples/basic_simulation.py
```

Shows configuration setup without blockchain connection.

## Full Simulation

```bash
# Arc Testnet
export DEPLOYER_PRIVATE_KEY="your_key"
python scripts/run_complete_simulation.py -e arc_testnet -q --confirm

# Local Development
anvil --fork-url https://eth-mainnet.g.alchemy.com/v2/demo --chain-id 31337
python scripts/run_complete_simulation.py -e development -q
```

## Analysis

```python
import pandas as pd
df = pd.read_csv('data/results/simulation_*/mev_analysis.csv')
print(f"Total MEV: {df['mev_profit'].sum():.2f} USDC")
```