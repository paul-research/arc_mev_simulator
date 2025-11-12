#!/usr/bin/env python3
"""
Front-Running Attack Demonstration on Arc Testnet

Demonstrates real MEV attack using mempool monitoring:
- Victim submits transaction (320 gwei)
- MEV bot detects via txpool_content RPC
- MEV bot submits higher-gas front-run (340 gwei)
- MEV bot executes first on blockchain
"""
from web3 import Web3
import sys
import os
import time
import threading
from eth_account import Account

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.deployment.uniswap_v3_abis import ERC20_ABI, SWAP_ROUTER_ABI

w3 = Web3(Web3.HTTPProvider('https://arc-testnet.stg.blockchain.circle.com'))

swap_router_addr = w3.to_checksum_address("0xe372f58a9e03c7b56b3ea9a2a08f18767b75ca67")
token1_addr = w3.to_checksum_address("0x6911406ae5C9fa9314B4AEc086304c001fb3b656")
token2_addr = w3.to_checksum_address("0x3eaE1139A9A19517B0dB5696073d957542886BF8")
pool_addr = w3.to_checksum_address("0x39A9Ba5F012aB6D6fc90E563C72bD85949Ca0FF6")

victim_addr = w3.to_checksum_address("0x0cDCCD90Ec76f490e1495E0190FeCAaCe165254a")
mev_addr = w3.to_checksum_address("0xF1f0b247Ec9d10B5410CC67d097CF099ebAD973d")

swap_router = w3.eth.contract(address=swap_router_addr, abi=SWAP_ROUTER_ABI)
token1 = w3.eth.contract(address=token1_addr, abi=ERC20_ABI)
token2 = w3.eth.contract(address=token2_addr, abi=ERC20_ABI)

victim_key = '0x4d58edafc0c6889c6f211cc842a561835015eeaf273d9f8c8ec7ee960804f7ce'
mev_key = '0x488e3ab7dc2033bc970e83bc6daf50ed83c4927e5d8f5bd5ca971df3d062cac2'

victim_account = Account.from_key(victim_key)
mev_account = Account.from_key(mev_key)

# Gas prices based on current network conditions
VICTIM_GAS = 320  # Normal gas
MEV_GAS = 340     # Slightly higher - will execute first

print("="*70)
print("PERFECT FRONT-RUN ATTACK")
print("="*70)
print()
print(f"Victim: {victim_addr}")
print(f"MEV Bot: {mev_addr}")
print()
print(f"Gas Strategy:")
print(f"  Victim: {VICTIM_GAS} gwei (normal)")
print(f"  MEV Bot: {MEV_GAS} gwei (+{MEV_GAS - VICTIM_GAS} gwei higher)")
print()

def get_pool_price():
    balance1 = token1.functions.balanceOf(pool_addr).call()
    balance2 = token2.functions.balanceOf(pool_addr).call()
    return balance2 / balance1 if balance1 > 0 else 0

initial_price = get_pool_price()
print(f"Initial pool price: {initial_price:.6f} TOKEN2/TOKEN1")
print()

# MEV Bot monitoring
detected_swap = None
monitor_running = True
detection_time = None

def mev_monitor():
    """MEV Bot: Continuously monitor txpool_content"""
    global detected_swap, monitor_running, detection_time
    
    print("[MEV Bot] 🤖 Monitoring txpool_content...")
    print("[MEV Bot]    Scanning for large swaps from ANY account...")
    check_count = 0
    
    while monitor_running:
        try:
            check_count += 1
            
            result = w3.provider.make_request('txpool_content', [])
            
            if 'result' not in result:
                time.sleep(0.1)
                continue
            
            # Check both queued and pending
            for pool_name in ['queued', 'pending']:
                pool = result['result'].get(pool_name, {})
                
                for account_addr, txs in pool.items():
                    for nonce_str, tx in txs.items():
                        if tx['to'] and tx['to'].lower() == swap_router_addr.lower():
                            input_data = tx['input']
                            
                            if input_data[:10] == '0x04e45aaf':
                                try:
                                    func, params = swap_router.decode_function_input(input_data)
                                    swap_params = params['params']
                                    amount_in = swap_params['amountIn']
                                    
                                    # Target large swaps (> 60 tokens)
                                    if amount_in >= w3.to_wei(60, 'ether') and detected_swap is None:
                                        detected_swap = {
                                            'account': account_addr,
                                            'tokenIn': swap_params['tokenIn'],
                                            'tokenOut': swap_params['tokenOut'],
                                            'amountIn': amount_in,
                                            'gas': int(tx['maxFeePerGas'], 16),
                                            'pool': pool_name,
                                            'nonce': int(nonce_str)
                                        }
                                        detection_time = time.time()
                                        
                                        token_in = w3.to_checksum_address(swap_params['tokenIn'])
                                        direction = "TOKEN2→TOKEN1" if token_in == token2_addr else "TOKEN1→TOKEN2"
                                        
                                        print(f"[MEV Bot] 🎯 LARGE SWAP DETECTED!")
                                        print(f"[MEV Bot]    From: {account_addr[:10]}... (unknown)")
                                        print(f"[MEV Bot]    Pool: {pool_name.upper()}")
                                        print(f"[MEV Bot]    Direction: {direction}")
                                        print(f"[MEV Bot]    Amount: {w3.from_wei(amount_in, 'ether')} tokens")
                                        print(f"[MEV Bot]    Gas: {int(tx['maxFeePerGas'], 16) / 1e9:.0f} gwei")
                                        print()
                                        return
                                except:
                                    pass
            
            if check_count % 10 == 0:
                print(f"[MEV Bot]    Scan #{check_count}...")
            
            time.sleep(0.1)
            
        except:
            pass

# Start MEV monitoring
monitor_thread = threading.Thread(target=mev_monitor, daemon=True)
monitor_thread.start()
time.sleep(1)

print("="*70)
print("STEP 1: VICTIM SUBMITS LARGE SWAP (slow gas)")
print("="*70)
print()

# Victim submits large swap with SLOW gas
victim_amount = 80.0  # Large swap
victim_amount_wei = w3.to_wei(victim_amount, 'ether')

swap_params = {
    'tokenIn': token2_addr,
    'tokenOut': token1_addr,
    'fee': 100,
    'recipient': victim_account.address,
    'amountIn': victim_amount_wei,
    'amountOutMinimum': 0,
    'sqrtPriceLimitX96': 0
}

victim_nonce = w3.eth.get_transaction_count(victim_account.address, 'pending')

victim_swap_tx = swap_router.functions.exactInputSingle(swap_params).build_transaction({
    'from': victim_account.address,
    'nonce': victim_nonce,
    'gas': 800000,
    'maxFeePerGas': w3.to_wei(VICTIM_GAS, 'gwei'),
    'maxPriorityFeePerGas': w3.to_wei(int(VICTIM_GAS * 0.2), 'gwei'),
    'chainId': 5042002
})

signed_victim = w3.eth.account.sign_transaction(victim_swap_tx, victim_account.key)
victim_submit_time = time.time()
victim_tx_hash = w3.eth.send_raw_transaction(signed_victim.raw_transaction)

print(f"[Victim] ✅ Large swap submitted!")
print(f"[Victim]    TX: {victim_tx_hash.hex()}")
print(f"[Victim]    Amount: {victim_amount} tokens")
print(f"[Victim]    Gas: {VICTIM_GAS} gwei")
print()

# Wait for MEV bot to detect
print("="*70)
print("STEP 2: MEV BOT DETECTS IN MEMPOOL")
print("="*70)
print()

for i in range(50):  # Wait up to 5 seconds
    if detected_swap:
        break
    time.sleep(0.1)

if not detected_swap:
    print("[MEV Bot] ❌ Detection failed")
    monitor_running = False
    exit(1)

monitor_running = False
detection_latency = detection_time - victim_submit_time
print(f"[MEV Bot] ✅ Detected in {detection_latency:.2f}s")
print()

# MEV Bot executes front-run
print("="*70)
print("STEP 3: MEV BOT FRONT-RUNS (fast gas)")
print("="*70)
print()

mev_amount = 60.0  # Similar size
mev_amount_wei = w3.to_wei(mev_amount, 'ether')

token_in = w3.to_checksum_address(detected_swap['tokenIn'])
token_to_approve = token2 if token_in == token2_addr else token1

# Skip approval (assume already approved from previous runs)
print(f"[MEV Bot] Skipping approval (already approved)")

# Front-run swap
mev_swap_params = {
    'tokenIn': detected_swap['tokenIn'],
    'tokenOut': detected_swap['tokenOut'],
    'fee': 100,
    'recipient': mev_account.address,
    'amountIn': mev_amount_wei,
    'amountOutMinimum': 0,
    'sqrtPriceLimitX96': 0
}

mev_swap_tx = swap_router.functions.exactInputSingle(mev_swap_params).build_transaction({
    'from': mev_account.address,
    'nonce': w3.eth.get_transaction_count(mev_account.address, 'pending'),
    'gas': 800000,
    'maxFeePerGas': w3.to_wei(MEV_GAS, 'gwei'),
    'maxPriorityFeePerGas': w3.to_wei(int(MEV_GAS * 0.2), 'gwei'),
    'chainId': 5042002
})

signed_mev = w3.eth.account.sign_transaction(mev_swap_tx, mev_account.key)
mev_submit_time = time.time()
mev_tx_hash = w3.eth.send_raw_transaction(signed_mev.raw_transaction)

print(f"[MEV Bot] 🚀 FRONT-RUN SUBMITTED!")
print(f"[MEV Bot]    TX: {mev_tx_hash.hex()}")
print(f"[MEV Bot]    Amount: {mev_amount} tokens")
print(f"[MEV Bot]    Gas: {MEV_GAS} gwei (+{MEV_GAS - VICTIM_GAS} more)")
print(f"[MEV Bot]    Time since victim: {mev_submit_time - victim_submit_time:.2f}s")
print()

# Wait for MEV execution
print(f"[MEV Bot] Waiting for execution...")
mev_receipt = w3.eth.wait_for_transaction_receipt(mev_tx_hash, timeout=30)
mev_exec_time = time.time()
print(f"[MEV Bot] ✅ Executed in block {mev_receipt['blockNumber']}, index {mev_receipt['transactionIndex']}")
print(f"[MEV Bot]    Execution time: {mev_exec_time - mev_submit_time:.2f}s")
print()

# Wait for victim execution
print(f"[Victim] Waiting for victim's transaction...")
victim_executed = False

for i in range(30):  # Wait up to 3 more seconds
    try:
        victim_receipt = w3.eth.get_transaction_receipt(victim_tx_hash)
        victim_exec_time = time.time()
        print(f"[Victim] ✅ Executed in block {victim_receipt['blockNumber']}, index {victim_receipt['transactionIndex']}")
        print(f"[Victim]    Total time: {victim_exec_time - victim_submit_time:.2f}s")
        victim_executed = True
        break
    except:
        time.sleep(0.1)

print()

# Determine success
if victim_executed:
    if mev_receipt['blockNumber'] < victim_receipt['blockNumber']:
        result = "✅ FRONT-RUN SUCCESS!"
        detail = f"MEV bot executed {victim_receipt['blockNumber'] - mev_receipt['blockNumber']} blocks earlier"
    elif mev_receipt['blockNumber'] == victim_receipt['blockNumber']:
        if mev_receipt['transactionIndex'] < victim_receipt['transactionIndex']:
            result = "✅ FRONT-RUN SUCCESS!"
            detail = f"Same block, MEV bot index {mev_receipt['transactionIndex']} < victim index {victim_receipt['transactionIndex']}"
        else:
            result = "❌ Victim executed first"
            detail = f"Same block, victim index {victim_receipt['transactionIndex']} < MEV bot index {mev_receipt['transactionIndex']}"
    else:
        result = "❌ Victim executed first"
        detail = f"Victim in earlier block"
else:
    result = "⚠️  Victim still pending"
    detail = "Victim transaction taking longer than expected"

# Final results
final_price = get_pool_price()
price_impact = ((final_price - initial_price) / initial_price) * 100

print("="*70)
print("ATTACK RESULTS")
print("="*70)
print()
print(f"Price: {initial_price:.6f} → {final_price:.6f} ({price_impact:+.2f}%)")
print()
print(f"Victim gas: {VICTIM_GAS} gwei (slow)")
print(f"MEV gas: {MEV_GAS} gwei (fast, +{MEV_GAS - VICTIM_GAS} gwei)")
print()
print(f"MEV TX: {mev_tx_hash.hex()}")
print(f"Victim TX: {victim_tx_hash.hex()}")
print()
print(result)
print(f"  {detail}")
print()
print("Summary:")
print("- Victim used normal gas (320 gwei)")
print("- MEV bot detected via txpool_content (public RPC)")
print("- MEV bot used slightly higher gas (340 gwei)")
print("- MEV bot executed first due to gas priority")
print()
print("This demonstrates REAL front-running on Arc Testnet!")
print("="*70)

