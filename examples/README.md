# Examples

## Basic Simulation

Demonstrates MEV simulation configuration and setup.

```bash
python examples/basic_simulation.py
```

**What it does:**
- Creates basic MEV simulation configuration
- Shows how to configure bots and victims
- Tests core imports and setup

## Running Full Simulations

For complete simulations, use the main script:

```bash
# Development environment (requires Anvil)
python scripts/run_complete_simulation.py --environment development --quick-test

# Arc Testnet (requires DEPLOYER_PRIVATE_KEY)
export DEPLOYER_PRIVATE_KEY="your_key_here"
python scripts/run_complete_simulation.py --environment arc_testnet --quick-test --confirm
```

## Configuration Examples

### Minimal Config

```python
config = {
    "simulation": {
        "duration_minutes": 5.0,
        "target_transactions": 20
    },
    "mev_bots": {
        "enabled": True,
        "count": 2,
        "bot1": {"strategy": "aggressive"},
        "bot2": {"strategy": "conservative"}
    },
    "victim_transactions": {
        "enabled": True,
        "count": 1,
        "traders": {
            "victim1": {"type": "retail"}
        }
    }
}
```

### Research Config

```python
config = {
    "simulation": {
        "duration_minutes": 15.0,
        "target_transactions": 100
    },
    "mev_bots": {
        "count": 4,
        # Multiple strategies for competition analysis
    },
    "victim_transactions": {
        "count": 5,
        # Diverse victim profiles
    }
}
```

## Analysis

Simulation results are automatically saved to `data/results/` with:
- `mev_analysis.csv` - Detailed attack data  
- `summary_report.json` - Summary statistics

Load and analyze with pandas:

```python
import pandas as pd
df = pd.read_csv('data/results/simulation_*/mev_analysis.csv')
print(f"Total MEV Profit: {df['mev_profit'].sum():.6f} USDC")
```