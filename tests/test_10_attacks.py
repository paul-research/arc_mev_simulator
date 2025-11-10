#!/usr/bin/env python3
"""
Test 10 victim trades with MEV bot attacks on Arc Testnet
"""
import asyncio
import sys
import os
from web3 import Web3
from eth_account import Account

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.deployment.uniswap_v3_abis import ERC20_ABI, SWAP_ROUTER_ABI


async def execute_victim_swap(w3, victim_key, token1_addr, token2_addr, swap_router_addr, amount_in):
    """Execute a victim swap transaction"""
    victim_account = Account.from_key(victim_key)
    
    # Approve
    token1 = w3.eth.contract(address=token1_addr, abi=ERC20_ABI)
    amount_in_wei = w3.to_wei(amount_in, 'ether')
    
    current_allowance = token1.functions.allowance(victim_account.address, swap_router_addr).call()
    
    if current_allowance < amount_in_wei:
        nonce = w3.eth.get_transaction_count(victim_account.address)
        approve_tx = token1.functions.approve(swap_router_addr, amount_in_wei).build_transaction({
            'from': victim_account.address,
            'nonce': nonce,
            'gas': 100000,
            'maxFeePerGas': w3.to_wei(400, 'gwei'),
            'maxPriorityFeePerGas': w3.to_wei(80, 'gwei'),
        })
        
        signed_approve = w3.eth.account.sign_transaction(approve_tx, victim_key)
        approve_hash = w3.eth.send_raw_transaction(signed_approve.raw_transaction)
        await asyncio.sleep(2)  # Wait for confirmation
    
    # Swap
    swap_router = w3.eth.contract(address=swap_router_addr, abi=SWAP_ROUTER_ABI)
    
    swap_params = {
        'tokenIn': token1_addr,
        'tokenOut': token2_addr,
        'fee': 3000,
        'recipient': victim_account.address,
        'amountIn': amount_in_wei,
        'amountOutMinimum': 0,
        'sqrtPriceLimitX96': 0
    }
    
    nonce = w3.eth.get_transaction_count(victim_account.address)
    swap_tx = swap_router.functions.exactInputSingle(swap_params).build_transaction({
        'from': victim_account.address,
        'nonce': nonce,
        'gas': 800000,
        'maxFeePerGas': w3.to_wei(350, 'gwei'),
        'maxPriorityFeePerGas': w3.to_wei(70, 'gwei'),
    })
    
    signed_swap = w3.eth.account.sign_transaction(swap_tx, victim_key)
    swap_hash = w3.eth.send_raw_transaction(signed_swap.raw_transaction)
    
    return swap_hash.hex()


async def execute_mev_attack(w3, mev_key, token1_addr, token2_addr, swap_router_addr, front_run_amount, back_run_amount):
    """Execute MEV sandwich attack (front-run + back-run)"""
    mev_account = Account.from_key(mev_key)
    
    # Front-run: Buy TOKEN2 (sell TOKEN1)
    print(f"   🔴 Front-run: Sell {front_run_amount} TOKEN1...")
    
    token1 = w3.eth.contract(address=token1_addr, abi=ERC20_ABI)
    amount_in_wei = w3.to_wei(front_run_amount, 'ether')
    
    # Approve if needed
    current_allowance = token1.functions.allowance(mev_account.address, swap_router_addr).call()
    if current_allowance < amount_in_wei:
        nonce = w3.eth.get_transaction_count(mev_account.address)
        approve_tx = token1.functions.approve(swap_router_addr, amount_in_wei * 100).build_transaction({
            'from': mev_account.address,
            'nonce': nonce,
            'gas': 100000,
            'maxFeePerGas': w3.to_wei(500, 'gwei'),  # Higher gas for front-run
            'maxPriorityFeePerGas': w3.to_wei(100, 'gwei'),
        })
        signed = w3.eth.account.sign_transaction(approve_tx, mev_key)
        w3.eth.send_raw_transaction(signed.raw_transaction)
        await asyncio.sleep(1)
    
    # Front-run swap
    swap_router = w3.eth.contract(address=swap_router_addr, abi=SWAP_ROUTER_ABI)
    nonce = w3.eth.get_transaction_count(mev_account.address)
    
    frontrun_params = {
        'tokenIn': token1_addr,
        'tokenOut': token2_addr,
        'fee': 3000,
        'recipient': mev_account.address,
        'amountIn': amount_in_wei,
        'amountOutMinimum': 0,
        'sqrtPriceLimitX96': 0
    }
    
    frontrun_tx = swap_router.functions.exactInputSingle(frontrun_params).build_transaction({
        'from': mev_account.address,
        'nonce': nonce,
        'gas': 800000,
        'maxFeePerGas': w3.to_wei(500, 'gwei'),
        'maxPriorityFeePerGas': w3.to_wei(100, 'gwei'),
    })
    
    signed = w3.eth.account.sign_transaction(frontrun_tx, mev_key)
    frontrun_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    
    print(f"   ✅ Front-run TX: {frontrun_hash.hex()[:20]}...")
    
    # Wait a bit for victim transaction to happen
    await asyncio.sleep(3)
    
    # Back-run: Sell TOKEN2 (buy TOKEN1 back)
    print(f"   🔵 Back-run: Buy back TOKEN1...")
    
    token2 = w3.eth.contract(address=token2_addr, abi=ERC20_ABI)
    backrun_amount_wei = w3.to_wei(back_run_amount, 'ether')
    
    # Approve TOKEN2
    current_allowance = token2.functions.allowance(mev_account.address, swap_router_addr).call()
    if current_allowance < backrun_amount_wei:
        nonce = w3.eth.get_transaction_count(mev_account.address)
        approve_tx = token2.functions.approve(swap_router_addr, backrun_amount_wei * 100).build_transaction({
            'from': mev_account.address,
            'nonce': nonce,
            'gas': 100000,
            'maxFeePerGas': w3.to_wei(400, 'gwei'),
            'maxPriorityFeePerGas': w3.to_wei(80, 'gwei'),
        })
        signed = w3.eth.account.sign_transaction(approve_tx, mev_key)
        w3.eth.send_raw_transaction(signed.raw_transaction)
        await asyncio.sleep(1)
    
    # Back-run swap
    nonce = w3.eth.get_transaction_count(mev_account.address)
    
    backrun_params = {
        'tokenIn': token2_addr,
        'tokenOut': token1_addr,
        'fee': 3000,
        'recipient': mev_account.address,
        'amountIn': backrun_amount_wei,
        'amountOutMinimum': 0,
        'sqrtPriceLimitX96': 0
    }
    
    backrun_tx = swap_router.functions.exactInputSingle(backrun_params).build_transaction({
        'from': mev_account.address,
        'nonce': nonce,
        'gas': 800000,
        'maxFeePerGas': w3.to_wei(400, 'gwei'),
        'maxPriorityFeePerGas': w3.to_wei(80, 'gwei'),
    })
    
    signed = w3.eth.account.sign_transaction(backrun_tx, mev_key)
    backrun_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    
    print(f"   ✅ Back-run TX: {backrun_hash.hex()[:20]}...")
    
    return frontrun_hash.hex(), backrun_hash.hex()


async def test_10_simulations():
    print("=" * 70)
    print("Testing 10 Victim Trades + MEV Attacks on Arc Testnet")
    print("=" * 70)
    
    # Setup
    rpc_url = "https://arc-testnet.stg.blockchain.circle.com"
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    victim_key = "0x4d58edafc0c6889c6f211cc842a561835015eeaf273d9f8c8ec7ee960804f7ce"
    mev_key = "0x488e3ab7dc2033bc970e83bc6daf50ed83c4927e5d8f5bd5ca971df3d062cac2"
    
    token1_addr = w3.to_checksum_address("0x6911406ae5C9fa9314B4AEc086304c001fb3b656")
    token2_addr = w3.to_checksum_address("0x3eaE1139A9A19517B0dB5696073d957542886BF8")
    swap_router_addr = w3.to_checksum_address("0xe372f58a9e03c7b56b3ea9a2a08f18767b75ca67")
    
    victim_account = Account.from_key(victim_key)
    mev_account = Account.from_key(mev_key)
    
    print(f"\n👤 Victim: {victim_account.address}")
    print(f"🤖 MEV Bot: {mev_account.address}")
    print(f"\n{'='*70}")
    
    results = []
    
    for i in range(10):
        print(f"\n🔄 Round {i+1}/10")
        print("-" * 70)
        
        try:
            # 1. MEV Bot front-runs
            print("1️⃣  MEV Bot front-running...")
            victim_amount = 30  # Victim will trade 30 TOKEN1
            frontrun_amount = victim_amount * 0.5  # Bot front-runs with 50% of victim size
            backrun_amount = frontrun_amount * 2  # Bot back-runs to close position
            
            frontrun_hash, _ = await execute_mev_attack(
                w3, mev_key, token1_addr, token2_addr, swap_router_addr,
                frontrun_amount, backrun_amount
            )
            
            # 2. Victim trades (in the middle)
            print(f"\n2️⃣  Victim trading {victim_amount} TOKEN1...")
            victim_hash = await execute_victim_swap(
                w3, victim_key, token1_addr, token2_addr, swap_router_addr, victim_amount
            )
            print(f"   ✅ Victim TX: {victim_hash[:20]}...")
            
            # Back-run already happened in execute_mev_attack
            
            results.append({
                'round': i+1,
                'victim_tx': victim_hash,
                'frontrun_tx': frontrun_hash,
                'success': True
            })
            
            print(f"   ✅ Round {i+1} complete!")
            
            # Wait between rounds
            await asyncio.sleep(3)
            
        except Exception as e:
            print(f"   ❌ Round {i+1} failed: {e}")
            results.append({
                'round': i+1,
                'success': False,
                'error': str(e)
            })
    
    # Summary
    print(f"\n{'='*70}")
    print("📊 SUMMARY")
    print(f"{'='*70}")
    
    successful = [r for r in results if r.get('success')]
    print(f"✅ Successful rounds: {len(successful)}/10")
    print(f"❌ Failed rounds: {10 - len(successful)}/10")
    
    if successful:
        print(f"\n📝 Sample transactions:")
        for r in successful[:3]:
            print(f"   Round {r['round']}: {r['victim_tx'][:20]}...")
    
    return len(successful) >= 8  # Consider success if 8+ rounds worked


if __name__ == "__main__":
    try:
        result = asyncio.run(test_10_simulations())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

