# Configuration Guide

## File Structure

```
config/
├── config.yaml          # Main simulation settings
├── environment.yaml      # Network and account configurations
```

## Main Configuration (config.yaml)

### Simulation Settings

```yaml
simulation:
  name: "mev_competition_analysis"
  duration_minutes: 10.0
  target_transactions: 100
  target_rounds: 50
  output_dir: "data/results"
```

### MEV Bot Configuration

```yaml
mev_bots:
  enabled: true
  count: 4

  bot1:
    strategy: "aggressive"
    initial_balance_eth: 1.0
    wallet_private_key: "${MEV_BOT1_PRIVATE_KEY}"
    
    strategy_params:
      bid_percentage: 80.0              # % of expected profit to bid as gas
      max_slippage: 0.02               # Maximum acceptable slippage
      min_profit_threshold: 0.001      # Minimum profit to attempt attack (ETH)
      risk_tolerance: 0.8              # Risk tolerance (0.0-1.0)
      
    latency_profile: "fast"
```

**Strategy Types:**
- `aggressive`: High-speed, high-risk, maximum profit
- `conservative`: Safe approach, consistent profits
- `adaptive`: Changes strategy based on market conditions
- `slow`: Delayed responses, lower competition
- `custom`: Use custom parameters in `strategy_params`

**Latency Profiles:**
- `fast`: 50-120ms total latency
- `medium`: 150-300ms total latency  
- `slow`: 300-600ms total latency
- `ultra_fast`: 10-50ms total latency

### Victim Trader Configuration

```yaml
victim_transactions:
  enabled: true
  count: 5

  global_settings:
    stress_response:
      enabled: true
      stress_decay_rate: 0.1
      max_stress_level: 1.0
    
    market_conditions:
      volatility_multiplier: 1.0
      gas_price_threshold: 500          # Gwei threshold
      liquidity_threshold: 1000
    
    learning:
      enabled: false
      learning_rate: 0.05
      memory_window: 10

  traders:
    retail_alice:
      type: "retail"
      wallet_private_key: "${VICTIM1_PRIVATE_KEY}"
      
      initial_balances:
        TOKEN1: 1000
        TOKEN2: 500
        ETH: 2.0
      
      custom_pattern:
        frequency_seconds: 240.0
        amount_range: [5, 50]
        slippage_tolerance: 0.02
        gas_sensitivity: 0.8
        patience_level: 0.3
        token_preference: ["TOKEN1", "TOKEN2"]
```

**Victim Types:**
- `retail`: Small traders, high slippage tolerance
- `whale`: Large traders, low slippage tolerance
- `dca_bot`: Regular consistent trades
- `arbitrage_bot`: Fast arbitrage trading
- `liquidity_provider`: Liquidity position management
- `panic_seller`: Emotional trading, high slippage

### Pool Configuration

```yaml
pools:
  token_a:
    name: "Token1"
    symbol: "TOKEN1"
    decimals: 18
    total_supply: 1000000
    
  token_b:
    name: "Token2"
    symbol: "TOKEN2"
    decimals: 18
    total_supply: 1000000

  uniswap_v3:
    fee_tier: 3000                      # 0.3% fee
    initial_price_ratio: "1:2"          # TOKEN1:TOKEN2 = 1:2
    
    liquidity:
      amount_token_a: 1000
      amount_token_b: 2000
      price_range:
        lower_tick: -887220             # Full range
        upper_tick: 887220
```

### Latency Profiles

```yaml
latency_profiles:
  fast:
    block_detection: 50                 # ms
    market_update: 100
    calculation: 80
    bundle_creation: 60
    network_submission: 120
    jitter: 0.1                        # Random variation (0.0-1.0)
  
  medium:
    block_detection: 150
    market_update: 200
    calculation: 180
    bundle_creation: 120
    network_submission: 250
    jitter: 0.2
```

## Environment Configuration (environment.yaml)

### Network Settings

```yaml
default_environment: "arc_testnet"

arc_testnet:
  network:
    name: "arc_testnet"
    rpc_url: "https://arc-testnet.stg.blockchain.circle.com"
    chain_id: 1337
    block_time_ms: 500
    gas_price_gwei: 300
    max_priority_fee_gwei: 50
    
    contracts:
      # Pre-deployed tokens
      paul_king_token: "0x6911406ae5C9fa9314B4AEc086304c001fb3b656"
      paul_queen_token: "0x3eaE1139A9A19517B0dB5696073d957542886BF8"
      wusdc_native: "0x3600000000000000000000000000000000000000"
      
      # Uniswap V3 contracts
      uniswap_v3_factory: "0x1F98431c8aD98523631AE4a59f267346ea31F984"
      uniswap_v3_router: "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"
      position_manager: "0xC36442b4c4e76c8f7a04B0eE0d2C2d4C6e5e4F2D"
      quoter_v2: "0x61fFE014bA17989E743c5F6cB21bF9697530B21e"
      
      # Simulation contracts
      swap_router: "0xe372f58a9e03c7b56b3ea9a2a08f18767b75ca67"
      uniswap_pool: "0x39A9Ba5F012aB6D6fc90E563C72bD85949Ca0FF6"

  accounts:
    deployer:
      private_key: "${DEPLOYER_PRIVATE_KEY}"
      address: "0xF1f0b247Ec9d10B5410CC67d097CF099ebAD973d"
    
    mev_bots:
      bot1:
        private_key: "${MEV_BOT1_PRIVATE_KEY}"
        address: "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
```

### Development Environment

```yaml
development:
  network:
    name: "anvil_mainnet_fork"
    rpc_url: "http://127.0.0.1:8545"
    chain_id: 31337
    block_time_ms: 1000
    
    contracts:
      uniswap_v3_factory: "0x1F98431c8aD98523631AE4a59f267346ea31F984"
      uniswap_v3_router: "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"
      position_manager: "0xC36442b4c4e76c8f7a04B0eE0d2C2d4C6e5e4F2D"
      quoter_v2: "0x61fFE014bA17989E743c5F6cB21bF9697530B21e"
      weth9: "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
  
  accounts:
    deployer:
      private_key: "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
      address: "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
```

## Environment Variables

```bash
# Required for Arc Testnet
export DEPLOYER_PRIVATE_KEY="0x..."
export MEV_BOT1_PRIVATE_KEY="0x..."
export VICTIM1_PRIVATE_KEY="0x..."

# Optional
export MEV_SIM_ENV="arc_testnet"
export MEV_SIM_LOG_LEVEL="INFO"
```

## Advanced Settings

### Performance Configuration

```yaml
performance:
  max_concurrent_bots: 10
  batch_size: 50
  enable_parallel_processing: true
  worker_processes: 4
  max_memory_usage_gb: 8.0
```

### Monitoring

```yaml
monitoring:
  log_level: "INFO"
  log_to_file: true
  log_file_path: "logs/simulation.log"
  enable_metrics: true
  metrics_interval_seconds: 5
```

### Security

```yaml
security:
  use_env_variables: true
  encrypt_private_keys: false
  enable_ssl_verification: true
  request_timeout_seconds: 30
  max_retries: 3
  max_transaction_value_eth: 10.0
```

## Configuration Templates

### Research Configuration

```yaml
simulation:
  name: "mev_research_study"
  duration_minutes: 60
  target_transactions: 500

mev_bots:
  count: 6  # More bots for competition analysis
```

### Performance Testing

```yaml
simulation:
  target_transactions: 1000

performance:
  enable_parallel_processing: true
  worker_processes: 8
  batch_size: 100
```

### Development Testing

```yaml
simulation:
  duration_minutes: 2
  target_transactions: 20

monitoring:
  log_level: "DEBUG"

security:
  enable_dry_run_mode: true
```

## Validation

The simulator validates configurations before execution:

- Network connectivity
- Account balances
- Contract addresses
- Parameter ranges
- Strategy consistency

## Common Issues

### Invalid Parameters

```yaml
# ❌ Invalid
slippage_tolerance: 1.5  # Must be 0.0-1.0
frequency_seconds: -10   # Must be positive

# ✅ Valid
slippage_tolerance: 0.02
frequency_seconds: 240.0
```

### Missing Environment Variables

```bash
❌ Error: DEPLOYER_PRIVATE_KEY not set
```

Solution: Set required environment variables or configure in YAML.

### Network Configuration

```bash
❌ Error: Connection refused
```

Solution: Verify RPC URL and network connectivity.