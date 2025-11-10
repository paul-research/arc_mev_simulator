# MEV Simulator

Front-running attack simulator for blockchain MEV research.

**Author:** paul.kwon@circle.com  
**Repository:** https://github.com/paul-research/arc_mev_simulator

## Quick Start

```bash
# Install
pip install -r requirements.txt

# Run victim trader (normal trading)
python scripts/run_victim_trader.py --trades 10 --interval 10

# Run MEV bot (sandwich attacks)
python scripts/run_mev_bot.py --mode aggressive --demo

# Run backrun bot (price rebalancing)
python scripts/run_backrun_bot.py --target-ratio 2.0 --threshold 0.005
```

## Scripts

### Production Scripts (`scripts/`)

| Script | Purpose | Usage |
|--------|---------|-------|
| `run_victim_trader.py` | Normal trading activity | `--trades N --interval S` |
| `run_mev_bot.py` | MEV sandwich attacks | `--mode aggressive\|conservative\|adaptive` |
| `run_backrun_bot.py` | Price arbitrage/rebalancing | `--target-ratio R --threshold T` |

### Test Scripts (`tests/`)

| Script | Purpose |
|--------|---------|
| `test_victim_swap.py` | Single swap verification |
| `test_10_attacks.py` | 10 consecutive MEV attacks |
| `test_backrun_rebalance.py` | Backrun bot verification |

## Configuration

All contracts and keys are configured in:
- `config/environment.yaml` - Network and contract addresses
- `config/config.yaml` - Simulation parameters

### Arc Testnet Addresses

```yaml
RPC: https://arc-testnet.stg.blockchain.circle.com
TOKEN1: 0x6911406ae5C9fa9314B4AEc086304c001fb3b656
TOKEN2: 0x3eaE1139A9A19517B0dB5696073d957542886BF8
Pool: 0x39A9Ba5F012aB6D6fc90E563C72bD85949Ca0FF6
SwapRouter: 0xe372f58a9e03c7b56b3ea9a2a08f18767b75ca67
```

## Examples

### Run 100 victim trades
```bash
python scripts/run_victim_trader.py --trades 100 --interval 5
```

### Run aggressive MEV bot
```bash
python scripts/run_mev_bot.py --mode aggressive --interval 3
```

### Maintain pool price at 2:1 ratio
```bash
python scripts/run_backrun_bot.py --target-ratio 2.0 --threshold 0.005 --interval 10
```

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌────────────────┐
│ Victim Trader   │────▶│ Uniswap V3   │◀────│ MEV Bot        │
│ (Normal trades) │     │ Pool         │     │ (Front-run)    │
└─────────────────┘     └──────────────┘     └────────────────┘
                               ▲
                               │
                        ┌──────┴──────┐
                        │ Backrun Bot │
                        │ (Arbitrage) │
                        └─────────────┘
```

## Research

This simulator demonstrates:
- **Harmful MEV**: Front-running and sandwich attacks
- **Beneficial MEV**: Price rebalancing and arbitrage
- **Real blockchain execution**: All transactions on Arc Testnet

For extending to PBS research, see `docs/BACKRUN_CONFIG.md`.

## License

MIT
