# MEV Simulator

Front-running attack simulator for blockchain MEV research.

**Author:** paul.kwon@circle.com  
**Repository:** https://github.com/paul-research/arc_mev_simulator

## Overview

This simulator demonstrates MEV (Maximal Extractable Value) attacks on Uniswap V3 pools running on Arc Testnet. It includes three independent components that work together:

- **Victim Trader**: Normal users making trades
- **MEV Bot**: Executes sandwich attacks (front-run + back-run)
- **Backrun Bot**: Arbitrage bot that restores pool price to target ratio

All transactions are executed on the actual blockchain, making this a realistic MEV research platform.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run victim trader (simulates normal trading)
python scripts/run_victim_trader.py --trades 10 --interval 5

# Run MEV bot (executes sandwich attacks)  
python scripts/run_mev_bot.py --mode aggressive --demo

# Run backrun bot (maintains price stability)
python scripts/run_backrun_bot.py --target-ratio 2.0 --threshold 0.005
```

## Components

### 1. Victim Trader (`run_victim_trader.py`)

Simulates normal user trading activity.

**Usage:**
```bash
# 20 trades with 10 second intervals
python scripts/run_victim_trader.py --trades 20 --interval 10

# Fixed amount of 100 tokens per trade
python scripts/run_victim_trader.py --trades 10 --amount 100

# Custom RPC and private key
python scripts/run_victim_trader.py --rpc https://custom-rpc.com --private-key 0x...
```

**Arguments:**
- `--trades N`: Number of trades to execute (default: 10)
- `--interval S`: Seconds between trades (default: 10)
- `--amount A`: Fixed amount per trade (default: random 20-100)
- `--rpc URL`: RPC endpoint (default: Arc Testnet)
- `--private-key KEY`: Trader private key

**Output:**
```
[21:33:24] Trade 1/3
  Amount: 50.00 TOKEN2
  Pool price before: 0.904889
  ✅ TX: d19b9a38442b59c9c13e...
  Block: 10378159
  Pool price after: 0.976430
  Price impact: +7.906%
```

### 2. MEV Bot (`run_mev_bot.py`)

Executes sandwich attacks on victim transactions.

**Usage:**
```bash
# Run in demo mode (2 example attacks)
python scripts/run_mev_bot.py --demo

# Monitor mempool (would need flashbots/private mempool in production)
python scripts/run_mev_bot.py --mode aggressive --interval 5

# Conservative attack strategy
python scripts/run_mev_bot.py --mode conservative
```

**Arguments:**
- `--mode MODE`: Attack strategy (aggressive/conservative/adaptive)
- `--demo`: Run demo attacks instead of monitoring
- `--interval S`: Mempool check interval (default: 5)
- `--rpc URL`: RPC endpoint
- `--private-key KEY`: Bot private key

**Attack Modes:**
- `aggressive`: 80% of victim size, 1.5x gas multiplier
- `conservative`: 30% of victim size, 1.2x gas multiplier  
- `adaptive`: 50% of victim size, 1.3x gas multiplier

**Output:**
```
[21:35:10] 🎯 Sandwich Attack Opportunity Detected
  Victim will trade: 50.00 TOKEN1
  Pool price: 0.976430
  🔴 Front-run: 25.00 TOKEN1
     ✅ TX: a1b2c3... (block 10378200)
  🔵 Back-run: 26.25 TOKEN1
     ✅ TX: d4e5f6... (block 10378202)
  💰 Estimated profit: 0.0125 ETH
```

### 3. Backrun Bot (`run_backrun_bot.py`)

Monitors pool price and executes arbitrage to restore target ratio.

**Usage:**
```bash
# Maintain 2:1 ratio with 0.5% threshold
python scripts/run_backrun_bot.py --target-ratio 2.0 --threshold 0.005

# More aggressive rebalancing (0.1% threshold)
python scripts/run_backrun_bot.py --target-ratio 2.0 --threshold 0.001 --interval 5
```

**Arguments:**
- `--target-ratio R`: Target price ratio TOKEN2/TOKEN1 (default: 2.0)
- `--threshold T`: Deviation threshold to trigger (default: 0.005 = 0.5%)
- `--interval S`: Check interval in seconds (default: 10)
- `--rpc URL`: RPC endpoint
- `--private-key KEY`: Bot private key

**Output:**
```
[21:36:15] Pool State
  Reserves: 1450.23 TOKEN1, 1200.45 TOKEN2
  Current ratio: 0.827534
  Target ratio: 2.0
  Deviation: 58.62%
  ⚠️  REBALANCE NEEDED!
  🔄 Buying TOKEN1 with 300.00 TOKEN2
     ✅ TX: g7h8i9... (block 10378250)
     New ratio: 1.652341
     Improvement: 41.17%
```

## Configuration

### Network Settings (`config/environment.yaml`)

```yaml
arc_testnet:
  network:
    rpc_url: "https://arc-testnet.stg.blockchain.circle.com"
    chain_id: 5042002
    
  contracts:
    token1_address: "0x6911406ae5C9fa9314B4AEc086304c001fb3b656"
    token2_address: "0x3eaE1139A9A19517B0dB5696073d957542886BF8"
    uniswap_pool: "0x39A9Ba5F012aB6D6fc90E563C72bD85949Ca0FF6"
    swap_router: "0xe372f58a9e03c7b56b3ea9a2a08f18767b75ca67"
    pool_fee: 100  # 0.01%
```

### Private Keys

Set environment variables or pass via CLI:
```bash
export DEPLOYER_PRIVATE_KEY="0x..."
export VICTIM1_PRIVATE_KEY="0x..."  
export MEV_BOT_PRIVATE_KEY="0x..."

# Or pass directly
python scripts/run_victim_trader.py --private-key 0x...
```

## Example: Complete Simulation

Run all three components simultaneously in different terminals:

**Terminal 1: Victim Trader**
```bash
python scripts/run_victim_trader.py --trades 100 --interval 15
```

**Terminal 2: MEV Bot**
```bash
python scripts/run_mev_bot.py --mode aggressive --demo
```

**Terminal 3: Backrun Bot**
```bash
python scripts/run_backrun_bot.py --target-ratio 2.0 --threshold 0.005 --interval 10
```

### Expected Behavior:

1. **Victim** trades 50 TOKEN2 → pool price moves from 0.90 to 0.98 (+7.9%)
2. **MEV Bot** detects opportunity, front-runs with 25 TOKEN2
3. Victim's trade executes at worse price (slippage increases)
4. **MEV Bot** back-runs, closes position for profit
5. **Backrun Bot** detects price deviation, arbitrages back toward 2.0 target
6. Pool price stabilizes, ready for next cycle

## Architecture

```
┌─────────────────┐
│ Victim Trader   │  Normal trading (price impact 5-8%)
│ (Terminal 1)    │
└────────┬────────┘
         │
         ▼
   ┌─────────────┐      ┌──────────────────┐
   │ Uniswap V3  │◀─────│ MEV Bot          │  Sandwich attack
   │ Pool        │      │ (Terminal 2)     │  (front-run + back-run)
   │ 0x39A9...   │      └──────────────────┘
   └─────────────┘
         ▲
         │
┌────────┴────────┐
│ Backrun Bot     │  Price rebalancing
│ (Terminal 3)    │  (restore to target)
└─────────────────┘
```

## Research Use Cases

### 1. MEV Impact Measurement
Run victim trader alone vs. with MEV bot to measure:
- Slippage amplification
- Price impact difference
- Victim loss percentage

### 2. Backrun Bot Effectiveness
Compare pool stability with/without backrun bot:
- Price deviation duration
- Recovery time to target ratio
- Liquidity efficiency

### 3. Attack Strategy Comparison
Test different MEV bot modes:
- Aggressive: High profit, high gas cost
- Conservative: Lower profit, lower risk
- Adaptive: Learning-based optimization

## Extending to PBS Research

This simulator can be extended for Proposer-Builder Separation (PBS) research:

1. **Private Mempool**: Replace mempool monitoring with private transaction submission
2. **Builder Competition**: Multiple MEV bots bidding for block inclusion
3. **Order Flow Auction**: Implement auction mechanism for transaction ordering

See `docs/BACKRUN_CONFIG.md` for backrun bot implementation details.

## Tests

Run test suite to verify functionality:

```bash
# Single swap verification
python tests/test_victim_swap.py

# 10 consecutive MEV attacks
python tests/test_10_attacks.py

# Backrun bot price restoration
python tests/test_backrun_rebalance.py
```

## Troubleshooting

### Transactions not appearing on blockchain
- Verify correct chain ID (5042002 for Arc Testnet)
- Check private key has sufficient ETH balance
- Confirm RPC endpoint is accessible

### Pool price not changing
- Verify using correct pool address (0x39A9...)
- Check pool has liquidity
- Confirm fee tier matches (100 = 0.01%)

### "Invalid chain ID" error
- All transactions must include `chainId: 5042002`
- Update `config/environment.yaml` if using different network

## License

MIT

## Citation

```bibtex
@software{mev_simulator,
  author = {Paul Kwon},
  title = {MEV Front-Running Attack Simulator},
  year = {2025},
  url = {https://github.com/paul-research/arc_mev_simulator}
}
```
