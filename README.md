# MEV Front-Running Attack Simulator

Front-running attack simulator on Arc Testnet using public mempool monitoring.

**Author:** paul.kwon@circle.com  
**Organization:** Circle Research

---

## Overview

This simulator demonstrates MEV front-running attacks on Arc Testnet by monitoring public mempool transactions via `txpool_content` RPC and executing higher-gas transactions to achieve priority ordering.

All transactions are executed on Arc Testnet blockchain.

### Attack Cases

**Case 1:**
- MEV Bot: Block 10835872 (executed first)
- Victim: Block 10835917 (45 blocks later)
- Method: +20 gwei gas priority

**Case 2:**
- MEV Bot: Block 10833967 (executed first)  
- Victim: Block 10834330 (363 blocks later)
- Method: +20 gwei gas priority

---

## Quick Start

```bash
pip install -r requirements.txt
python scripts/frontrun_attack_demo.py
```

---

## How It Works

### 1. Mempool Monitoring

Poll `txpool_content` RPC every 100ms to detect pending transactions:

```python
result = w3.provider.make_request('txpool_content', [])
queued = result['result'].get('queued', {})

for account, txs in queued.items():
    for nonce, tx in txs.items():
        if is_profitable_swap(tx):
            execute_frontrun(tx)
```

### 2. Transaction Decoding

Extract swap parameters from transaction input data:

```python
func, params = swap_router.decode_function_input(tx['input'])
token_in = params['tokenIn']
token_out = params['tokenOut']
amount = params['amountIn']
```

### 3. Gas Priority Execution

Submit transaction with higher gas to execute first:

```python
# Victim: 320 gwei
# MEV Bot: 340 gwei (+20 gwei)
# Result: MEV bot executes first due to gas priority
```

---

## Scripts

### `frontrun_attack_demo.py`

Complete front-running attack demonstration.

```bash
python scripts/frontrun_attack_demo.py
```

Execution flow:
1. Start mempool monitoring
2. Victim submits swap (320 gwei)
3. MEV bot detects transaction
4. MEV bot submits front-run (340 gwei)
5. MEV bot executes first

### `victim_trader.py`

Simulates victim trading activity.

```bash
python scripts/victim_trader.py
```

### `mev_bot_realtime.py`

Block monitoring MEV bot for fast chains.

```bash
python scripts/mev_bot_realtime.py
```

Monitors new blocks and executes sandwich attacks.

### `backrun_bot.py`

Arbitrage bot for pool price rebalancing.

```bash
python scripts/backrun_bot.py --target-ratio 2.0
```

---

## Configuration

### Network (`config/environment.yaml`)

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
    pool_fee: 100
```

### Private Keys

```bash
export VICTIM_KEY="0x4d58..."
export MEV_BOT_KEY="0x488e..."
```

---

## Attack Methods

### Method 1: Mempool Monitoring (txpool_content)

Poll `txpool_content` RPC to detect queued transactions before execution.

**Advantages:**
- Detect transactions before block inclusion
- Full transaction details available
- True front-running capability

**Limitations:**
- Requires fast polling (100-200ms)
- Only sees transactions accepted by node

### Method 2: Block Monitoring

Monitor new blocks and execute attacks in subsequent blocks.

**Advantages:**
- Reliable on fast chains
- Lower RPC overhead

**Limitations:**
- Not true front-running (reacts after execution)
- Suitable for sandwich attacks only

---

## Technical Details

### Gas Priority Mechanism

Transactions with higher `maxFeePerGas` are prioritized by validators:

| Party | Gas Price | Execution Order |
|-------|-----------|-----------------|
| Victim | 320 gwei | Second |
| MEV Bot | 340 gwei | First |

### Mempool States

Arc Testnet RPC exposes two transaction pools:

- **pending**: High-gas transactions ready for next block
- **queued**: Lower-gas transactions waiting for inclusion

Front-running targets transactions in the `queued` state.

### Transaction Decoding

Uniswap V3 `exactInputSingle` function signature:

```
Function: exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))
Selector: 0x04e45aaf
```

Decode to extract:
- `tokenIn`: Input token address
- `tokenOut`: Output token address
- `amountIn`: Swap amount
- `amountOutMinimum`: Slippage tolerance

---

## Tests

```bash
# Single swap test
python tests/test_victim_swap.py

# Multiple attacks
python tests/test_10_attacks.py

# Backrun rebalancing
python tests/test_backrun_rebalance.py
```

---

## Troubleshooting

### Transactions stuck in queue

Check pending transaction count:

```python
confirmed = w3.eth.get_transaction_count(address, 'latest')
pending = w3.eth.get_transaction_count(address, 'pending')
queued_count = pending - confirmed
```

Clear with high-gas replacement transactions.

### Invalid chain ID error

Arc Testnet chain ID is `5042002`. Ensure all transactions include:

```python
'chainId': 5042002
```

### Pool price not changing

Verify pool address: `0x39A9Ba5F012aB6D6fc90E563C72bD85949Ca0FF6`

---

## Project Structure

```
MEV-simulator/
├── scripts/
│   ├── frontrun_attack_demo.py
│   ├── victim_trader.py
│   ├── mev_bot.py
│   ├── mev_bot_realtime.py
│   └── backrun_bot.py
├── tests/
│   ├── test_victim_swap.py
│   ├── test_10_attacks.py
│   └── test_backrun_rebalance.py
├── src/
│   ├── core/
│   ├── deployment/
│   └── utils/
└── config/
    ├── config.yaml
    └── environment.yaml
```

---

## Attack Cases on Arc Testnet

**Transaction 1 (MEV Bot):**
```
Hash:  0x23664bc04a2c90a5375c3c23a47df220f53e3d725e7acb1821651d5c1cae2107
Block: 10835872
Index: 0
```

**Transaction 2 (Victim):**
```
Hash:  0xc8c5754eb9beb41a3d152f0e6f2dfa40d115ee814b6a49029c56a252b3293644
Block: 10835917
Index: 3
```

Explorer: `https://arc-testnet-explorer.circle.com`

---

## License

MIT

---

## Disclaimer

For research and educational purposes only.

---

## Citation

```bibtex
@software{mev_simulator,
  author = {Paul Kwon},
  title = {MEV Front-Running Attack Simulator},
  year = {2025},
  organization = {Circle Research},
  url = {https://github.com/paul-research/arc_mev_simulator}
}
```
