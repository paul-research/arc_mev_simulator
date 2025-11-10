# MEV-Simulator

PBS research platform - Circle Research (paul.kwon@circle.com)

## Objective

Evaluate PBS effectiveness: eliminate front-running while preserving beneficial arbitrage.

## Quick Start

```bash
git clone https://github.com/paul-research/arc_mev_simulator.git
cd MEV-simulator
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

export DEPLOYER_PRIVATE_KEY="your_key"
python scripts/run_complete_simulation.py -e arc_testnet -q --confirm
```

## Configuration

### Attack Mode (MEV Bots)
```yaml
# config/config.yaml
mev_bots:
  attack_mode:
    frontrun_only: false  # true = disable backrun (PBS mode)
```

### Backrun Bots (Beneficial)
```yaml
backrun_bots:
  enabled: true  # Price restoration bots
  bot_backrun_1:
    strategy_params:
      monitor_price_deviation: 0.003  # 0.3% trigger
```

## Research Scenarios

### 1. Full Sandwich (Baseline)
```yaml
mev_bots.attack_mode.frontrun_only: false
backrun_bots.enabled: true
```

### 2. PBS Simulation
```yaml
mev_bots.attack_mode.frontrun_only: true
backrun_bots.enabled: true
```

### 3. Ideal PBS
```yaml
mev_bots.enabled: false
backrun_bots.enabled: true
```

## Network Config

```yaml
# config/environment.yaml
arc_testnet:
  rpc_url: "https://arc-testnet.stg.blockchain.circle.com"
  contracts:
    token1_address: "0x6911406ae5C9fa9314B4AEc086304c001fb3b656"
    token2_address: "0x3eaE1139A9A19517B0dB5696073d957542886BF8"
    uniswap_pool: "0x39A9Ba5F012aB6D6fc90E563C72bD85949Ca0FF6"
```

## Results

```python
import pandas as pd
df = pd.read_csv('data/results/simulation_*/mev_analysis.csv')
print(f"MEV Profit: {df['mev_profit'].sum():.2f} USDC")
print(f"Victim Loss: {df['victim_loss'].sum():.2f} USDC")
```

## Documentation

- `docs/BACKRUN_CONFIG.md` - Backrun bot details

## License

MIT