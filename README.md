# MEV-Simulator

Professional MEV research platform for PBS (Proposer-Builder Separation) evaluation.

**Circle Research Team**  
Contact: paul.kwon@circle.com

## Research Objective

This simulator is designed to evaluate PBS systems and their effectiveness in eliminating harmful MEV (front-running) while preserving beneficial MEV (arbitrage/backrun). The goal is to understand how builder-based systems can protect users while maintaining market efficiency.

## Features

- **Real Blockchain Environment**: Simulation on actual Uniswap V3 pools on Arc Testnet
- **MEV Bot Strategies**: Aggressive, Conservative, Slow, Adaptive sandwich attacks
- **Backrun Bots**: Beneficial arbitrage bots that correct price imbalances
- **Front-Run Only Mode**: Configurable attack modes for PBS research
- **Victim Profiles**: Retail, Whale, DCA Bot, Arbitrage Bot, Panic Seller
- **Latency Modeling**: Network delays and inter-bot competition
- **Data Analysis**: Automated analysis with CSV/JSON export

## MEV Types Analyzed

### Harmful MEV (Target for Elimination)
- **Front-Running**: Bots detect pending transactions and execute ahead
- **Sandwich Attacks**: Front-run + victim trade + back-run

### Beneficial MEV (Should be Preserved)
- **Backrun/Arbitrage**: Corrects price deviations, improves market efficiency
- **Liquidations**: Maintains protocol solvency
- **Rebalancing**: Optimizes liquidity pool health

## Latest Results (Arc Testnet)

```
MEV Profit: 34.02 USDC
Victim Loss: 43.01 USDC  
Success Rate: 81.6%
Victim Trades: 8 executed, 1 failed
MEV Attacks: 76 attempts, 62 successful
```

## Installation

```bash
git clone https://github.com/paul-research/arc_mev_simulator.git
cd MEV-simulator

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

## Environment Setup

Set your Arc Testnet private key:

```bash
export DEPLOYER_PRIVATE_KEY="your_private_key_here"
```

## Usage

### Quick Test (Arc Testnet)

```bash
python scripts/run_complete_simulation.py \
  --environment arc_testnet \
  --quick-test \
  --confirm
```

### Development Environment (Local Anvil)

```bash
# Terminal 1: Start Anvil
anvil --fork-url https://eth-mainnet.g.alchemy.com/v2/demo --chain-id 31337

# Terminal 2: Run simulation
python scripts/run_complete_simulation.py \
  --environment development \
  --quick-test
```

### PBS Research Mode

```bash
# Compare front-run only vs full sandwich attacks
# Edit config/config.yaml:
#   attack_mode:
#     frontrun_only: true  # Disable back-run

python scripts/run_complete_simulation.py \
  --environment arc_testnet \
  --confirm
```

## Configuration

### Network Settings

```yaml
# config/environment.yaml
arc_testnet:
  network:
    rpc_url: "https://arc-testnet.stg.blockchain.circle.com"
    chain_id: 1337
  contracts:
    token1_address: "0x6911406ae5C9fa9314B4AEc086304c001fb3b656"
    token2_address: "0x3eaE1139A9A19517B0dB5696073d957542886BF8"
    uniswap_pool: "0x39A9Ba5F012aB6D6fc90E563C72bD85949Ca0FF6"
```

### Attack Mode Configuration

```yaml
# config/config.yaml
mev_bots:
  attack_mode:
    allow_frontrun: true      # Front-running attacks
    allow_sandwich: true      # Full sandwich attacks
    frontrun_only: false      # Set true to disable back-run
```

### Backrun Bots (Beneficial MEV)

```yaml
backrun_bots:
  enabled: true
  bot_backrun_1:
    strategy: "backrun_arbitrage"
    strategy_params:
      only_backrun: true      # Never front-run
      monitor_price_deviation: 0.003
```

## Architecture

```
MEV-Simulator/
├── config/
│   ├── config.yaml          # Simulation settings
│   └── environment.yaml      # Network & contract addresses
├── src/
│   ├── core/                # Simulation engine
│   │   ├── simulator.py     # Main orchestrator
│   │   ├── mev_bot.py       # MEV attack strategies
│   │   ├── victim_trader.py # Victim behavior patterns
│   │   └── pool_manager.py  # Uniswap V3 interactions
│   ├── deployment/          # Contract deployment
│   └── analysis/            # Result analysis
└── scripts/
    └── run_complete_simulation.py  # Main execution script
```

## Results Analysis

Results are automatically saved to `data/results/simulation_*/`:

```python
import pandas as pd

# Load results
df = pd.read_csv('data/results/simulation_*/mev_analysis.csv')

# Analyze MEV profitability
print(f"Total MEV Profit: {df['mev_profit'].sum():.6f} USDC")
print(f"Victim Loss: {df['victim_loss'].sum():.6f} USDC")
print(f"Success Rate: {df['success'].mean():.1%}")

# Compare front-run vs backrun
frontrun_profit = df[df['attack_type']=='frontrun']['mev_profit'].sum()
backrun_profit = df[df['attack_type']=='backrun']['mev_profit'].sum()
```

## Research Applications

### PBS Evaluation
- Measure front-run elimination effectiveness
- Quantify user protection improvements
- Analyze impact on beneficial MEV

### MEV Categorization
- Separate harmful vs beneficial MEV
- Economic impact analysis
- Value distribution studies

### Builder System Design
- Optimal ordering strategies
- MEV redistribution mechanisms
- User protection schemes

## Documentation

- [`docs/CONFIG_GUIDE.md`](docs/CONFIG_GUIDE.md) - Configuration reference
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) - Technical architecture
- [`examples/README.md`](examples/README.md) - Usage examples

## Contributing

This is a research project by Circle Research Team. For questions or collaboration:

**Contact:** paul.kwon@circle.com

## License

MIT License

---

**Circle Research Team**  
Advancing blockchain research for better user protection and market efficiency.