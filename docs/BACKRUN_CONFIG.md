# Backrun Bot Configuration Guide

## How Backrun On/Off Settings Work

### 1. Traditional MEV Bots (Harmful)

**Location:** `config/config.yaml` → `mev_bots` → `attack_mode`

```yaml
mev_bots:
  attack_mode:
    allow_frontrun: true      # Enable front-running
    allow_sandwich: true      # Enable full sandwich (front + back)
    frontrun_only: false      # If true, disable back-run part of sandwich
```

#### Modes:

**Standard Sandwich Attack (Default)**
```yaml
attack_mode:
  allow_frontrun: true
  allow_sandwich: true
  frontrun_only: false
```
- Victim trade detected
- Bot front-runs (buys before victim)
- Victim executes trade (price goes up)
- Bot back-runs (sells after victim) ← Profit here

**PBS Research Mode (Front-run Only)**
```yaml
attack_mode:
  allow_frontrun: true
  allow_sandwich: true
  frontrun_only: true    # Disable back-run
```
- Bot front-runs (buys before victim)
- Victim executes trade (price goes up)
- Bot DOES NOT back-run ← No sandwich completion
- Used to measure PBS effectiveness

---

### 2. Beneficial Backrun Bots (Good)

**Location:** `config/config.yaml` → `backrun_bots`

```yaml
backrun_bots:
  enabled: true     # Enable/disable beneficial bots
  count: 2
  
  bot_backrun_1:
    strategy: "backrun_arbitrage"
    strategy_params:
      only_backrun: true    # NEVER front-run, only correct prices
      monitor_price_deviation: 0.003
```

#### How It Works:

**Normal Operation (only_backrun: true)**
```
1. Victim trade happens
2. Price deviation detected (e.g., 0.3%)
3. Backrun bot executes AFTER victim
4. Price corrected back to equilibrium
5. Market efficiency improved
```

**Disable Beneficial Bots**
```yaml
backrun_bots:
  enabled: false    # Turn off all backrun bots
```

---

## PBS Research Scenarios

### Scenario 1: Traditional Mempool (Current)
```yaml
mev_bots:
  attack_mode:
    allow_frontrun: true
    frontrun_only: false    # Full sandwich enabled

backrun_bots:
  enabled: true
```

**Result:**
- MEV bots do full sandwich attacks (harmful)
- Backrun bots correct prices (beneficial)
- Users suffer from front-running

---

### Scenario 2: PBS with Front-run Elimination
```yaml
mev_bots:
  attack_mode:
    allow_frontrun: false    # PBS blocks front-running
    frontrun_only: true      # Or this

backrun_bots:
  enabled: true    # Keep beneficial MEV
```

**Result:**
- Front-running eliminated
- Price correction still works
- Users protected, market efficient

---

### Scenario 3: Compare Front-run Only vs Full Sandwich
```yaml
# Run 1: Full sandwich
mev_bots:
  attack_mode:
    frontrun_only: false

# Run 2: Front-run only (simulate PBS)
mev_bots:
  attack_mode:
    frontrun_only: true
```

**Compare:**
- MEV profit difference
- User loss difference
- Market efficiency

---

## Example Execution

### Run with Full Sandwich (Baseline)
```bash
# config.yaml: frontrun_only: false
python scripts/run_complete_simulation.py -e arc_testnet --confirm

# Results: 
# MEV Profit: 34.02 USDC (from full sandwich)
# Victim Loss: 43.01 USDC
```

### Run with Front-run Only (PBS)
```bash
# config.yaml: frontrun_only: true
python scripts/run_complete_simulation.py -e arc_testnet --confirm

# Expected Results:
# MEV Profit: ~15-20 USDC (front-run only, no back-run profit)
# Victim Loss: ~25-30 USDC (less than full sandwich)
```

### Run with Backrun Bots Only (Ideal PBS)
```bash
# config.yaml:
# mev_bots.attack_mode.allow_frontrun: false
# backrun_bots.enabled: true

python scripts/run_complete_simulation.py -e arc_testnet --confirm

# Expected Results:
# MEV Profit: 0 USDC (no sandwich attacks)
# Victim Loss: 0 USDC (no front-running)
# Backrun Profit: 5-10 USDC (beneficial arbitrage)
# Market: More efficient
```

---

## Key Differences

| Feature | MEV Bots (Harmful) | Backrun Bots (Beneficial) |
|---------|-------------------|---------------------------|
| **Strategy** | Sandwich attack | Arbitrage correction |
| **Front-run** | Yes (if enabled) | Never |
| **Back-run** | After victim (exploit) | After victim (correct) |
| **User Impact** | Negative (loss) | Neutral/Positive |
| **Market Impact** | Extract value | Improve efficiency |
| **PBS Goal** | Eliminate | Preserve |

---

## Configuration Files

### Main Config
`config/config.yaml` - Lines 31-34 and 314-349

### Implementation
Code reads these settings and:
1. MEV bots check `attack_mode.frontrun_only`
2. If true, skip back-run transaction
3. Backrun bots check `only_backrun` flag
4. Never execute front-run if true

---

## Research Questions

1. **How much does front-running contribute to total MEV?**
   - Compare `frontrun_only: false` vs `frontrun_only: true`

2. **Can beneficial MEV survive PBS?**
   - Run with `mev_bots.enabled: false` and `backrun_bots.enabled: true`

3. **What's the optimal PBS design?**
   - Block front-run, allow backrun
   - Measure user protection vs market efficiency

