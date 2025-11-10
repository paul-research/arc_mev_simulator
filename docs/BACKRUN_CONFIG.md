# Backrun Bot Configuration

## How It Works

Backrun bots restore pool price to target ratio after victim trades.

### Mechanism
```
1. Target: TOKEN1:TOKEN2 = 1:2 (price 2.0)
2. Victim buys 100 TOKEN1 → price rises to 2.08
3. Backrun bot detects 4% deviation > 0.3% threshold
4. Bot sells TOKEN1 → price restores to ~2.01
5. Bot profits from arbitrage: ~0.5-1 USDC
```

### Configuration

```yaml
# config/config.yaml
pools:
  uniswap_v3:
    initial_price_ratio: "1:2"  # Target price

backrun_bots:
  enabled: true
  bot_backrun_1:
    strategy_params:
      monitor_price_deviation: 0.003  # 0.3% threshold
      target_price_ratio: 2.0
      only_backrun: true
```

### On/Off

```yaml
# Enable
backrun_bots:
  enabled: true

# Disable
backrun_bots:
  enabled: false
```

## Code Location

- Implementation: `src/core/mev_bot.py` (BackrunBot class)
- Integration: `src/core/simulator.py` (_setup_backrun_bots method)
- Config: `config/config.yaml` (backrun_bots section)
