# MEV-Simulator

MEV research platform for PBS evaluation.

**Circle Research**  
paul.kwon@circle.com

## Objective

Evaluate PBS effectiveness: eliminate front-running while preserving beneficial arbitrage.

## Features

- Real Uniswap V3 on Arc Testnet
- MEV bot strategies: Aggressive, Conservative, Slow, Adaptive
- Backrun bots: Beneficial arbitrage
- Front-run only mode for PBS research
- Victim profiles: Retail, Whale, DCA, Arbitrage, Panic
- Latency modeling
- CSV/JSON analysis

## MEV Types

### Harmful (Eliminate)
- Front-running
- Sandwich attacks

### Beneficial (Preserve)
- Backrun/Arbitrage
- Liquidations
- Rebalancing

## Latest Results

```
MEV Profit: 34.02 USDC
Victim Loss: 43.01 USDC  
Success Rate: 81.6%
```

## Installation

```bash
git clone https://github.com/paul-research/arc_mev_simulator.git
cd MEV-simulator
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

### Arc Testnet

```bash
export DEPLOYER_PRIVATE_KEY="your_key"
python scripts/run_complete_simulation.py -e arc_testnet -q --confirm
```

### Development (Local Anvil)

```bash
anvil --fork-url https://eth-mainnet.g.alchemy.com/v2/demo --chain-id 31337
python scripts/run_complete_simulation.py -e development -q
```

### PBS Research Mode

```yaml
# config/config.yaml
mev_bots:
  attack_mode:
    frontrun_only: true  # Disable back-run for comparison
```

## Configuration

### Network

```yaml
# config/environment.yaml
arc_testnet:
  rpc_url: "https://arc-testnet.stg.blockchain.circle.com"
  chain_id: 1337
  contracts:
    token1_address: "0x6911406ae5C9fa9314B4AEc086304c001fb3b656"
    token2_address: "0x3eaE1139A9A19517B0dB5696073d957542886BF8"
    uniswap_pool: "0x39A9Ba5F012aB6D6fc90E563C72bD85949Ca0FF6"
```

### Attack Mode

```yaml
# config/config.yaml
mev_bots:
  attack_mode:
    allow_frontrun: true
    allow_sandwich: true
    frontrun_only: false
```

## Architecture

```
MEV-Simulator/
├── config/          # Settings
├── src/
│   ├── core/        # Simulation engine
│   ├── deployment/  # Contract deployment
│   └── analysis/    # Result analysis
└── scripts/         # Execution scripts
```

## Analysis

```python
import pandas as pd
df = pd.read_csv('data/results/simulation_*/mev_analysis.csv')
print(f"MEV Profit: {df['mev_profit'].sum():.2f} USDC")
print(f"Victim Loss: {df['victim_loss'].sum():.2f} USDC")
```

## Research Applications

- PBS front-run elimination measurement
- User protection quantification
- Harmful vs beneficial MEV separation
- Builder system design

## Documentation

- `docs/CONFIG_GUIDE.md` - Configuration
- `docs/ARCHITECTURE.md` - Technical details

## Contact

paul.kwon@circle.com

**Circle Research**

## License

MIT