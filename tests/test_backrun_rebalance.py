#!/usr/bin/env python3
"""
Test that backrun bot restores pool price after MEV attack
"""
import asyncio
import sys
import os
from web3 import Web3
from eth_account import Account

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.deployment.uniswap_v3_abis import ERC20_ABI, SWAP_ROUTER_ABI, UNISWAP_V3_POOL_ABI


def get_pool_price(w3, pool_addr, token1_addr, token2_addr):
    """Get pool price by checking pool's token reserves"""
    token1 = w3.eth.contract(address=token1_addr, abi=ERC20_ABI)
    token2 = w3.eth.contract(address=token2_addr, abi=ERC20_ABI)
    
    # Get pool's reserves (how much tokens the pool holds)
    pool_balance1 = token1.functions.balanceOf(pool_addr).call()
    pool_balance2 = token2.functions.balanceOf(pool_addr).call()
    
    if pool_balance1 == 0:
        return 0
    
    # Price = reserve2 / reserve1
    price = pool_balance2 / pool_balance1
    return price


async def execute_swap(w3, private_key, token_in_addr, token_out_addr, swap_router_addr, amount_in, label=""):
    """Execute a swap and return tx hash"""
    account = Account.from_key(private_key)
    
    # Approve
    token_in = w3.eth.contract(address=token_in_addr, abi=ERC20_ABI)
    amount_in_wei = w3.to_wei(amount_in, 'ether')
    
    current_allowance = token_in.functions.allowance(account.address, swap_router_addr).call()
    
    if current_allowance < amount_in_wei:
        nonce = w3.eth.get_transaction_count(account.address)
        approve_tx = token_in.functions.approve(swap_router_addr, amount_in_wei * 10).build_transaction({
            'from': account.address,
            'nonce': nonce,
            'gas': 100000,
            'maxFeePerGas': w3.to_wei(400, 'gwei'),
            'maxPriorityFeePerGas': w3.to_wei(80, 'gwei'),
        })
        
        signed = w3.eth.account.sign_transaction(approve_tx, private_key)
        w3.eth.send_raw_transaction(signed.raw_transaction)
        await asyncio.sleep(3)
    
    # Swap
    swap_router = w3.eth.contract(address=swap_router_addr, abi=SWAP_ROUTER_ABI)
    
    swap_params = {
        'tokenIn': token_in_addr,
        'tokenOut': token_out_addr,
        'fee': 3000,
        'recipient': account.address,
        'amountIn': amount_in_wei,
        'amountOutMinimum': 0,
        'sqrtPriceLimitX96': 0
    }
    
    nonce = w3.eth.get_transaction_count(account.address)
    swap_tx = swap_router.functions.exactInputSingle(swap_params).build_transaction({
        'from': account.address,
        'nonce': nonce,
        'gas': 800000,
        'maxFeePerGas': w3.to_wei(400, 'gwei'),
        'maxPriorityFeePerGas': w3.to_wei(80, 'gwei'),
    })
    
    signed = w3.eth.account.sign_transaction(swap_tx, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    
    # Wait for transaction to be mined
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
    print(f"   Confirmed at block: {receipt['blockNumber']}")
    
    return tx_hash.hex()


async def test_backrun_rebalance():
    print("=" * 70)
    print("Testing Backrun Bot Price Rebalancing")
    print("=" * 70)
    
    # Setup
    rpc_url = "https://arc-testnet.stg.blockchain.circle.com"
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    victim_key = "0x4d58edafc0c6889c6f211cc842a561835015eeaf273d9f8c8ec7ee960804f7ce"
    mev_key = "0x488e3ab7dc2033bc970e83bc6daf50ed83c4927e5d8f5bd5ca971df3d062cac2"
    backrun_key = mev_key  # Use same key for simplicity
    
    token1_addr = w3.to_checksum_address("0x6911406ae5C9fa9314B4AEc086304c001fb3b656")
    token2_addr = w3.to_checksum_address("0x3eaE1139A9A19517B0dB5696073d957542886BF8")
    pool_addr = w3.to_checksum_address("0x39A9Ba5F012aB6D6fc90E563C72bD85949Ca0FF6")  # Correct pool address
    swap_router_addr = w3.to_checksum_address("0xe372f58a9e03c7b56b3ea9a2a08f18767b75ca67")
    
    print(f"\n📊 Initial pool state:")
    initial_price = get_pool_price(w3, pool_addr, token1_addr, token2_addr)
    print(f"   Price: {initial_price:.6f}")
    
    target_price = initial_price  # We'll try to restore to this
    
    print(f"\n{'='*70}")
    print("Step 1: MEV Bot Front-runs (distorts price)")
    print(f"{'='*70}")
    
    # Large MEV front-run to distort price
    frontrun_amount = 500  # Much larger to create visible impact
    print(f"🔴 MEV Bot selling {frontrun_amount} TOKEN1...")
    frontrun_tx = await execute_swap(w3, mev_key, token1_addr, token2_addr, swap_router_addr, frontrun_amount, "MEV Front-run")
    print(f"   TX: {frontrun_tx[:20]}...")
    
    # No additional sleep needed - wait_for_transaction_receipt already waits
    
    price_after_frontrun = get_pool_price(w3, pool_addr, token1_addr, token2_addr)
    print(f"   Price after front-run: {price_after_frontrun:.6f}")
    print(f"   Price change: {((price_after_frontrun - initial_price) / initial_price * 100):+.2f}%")
    
    print(f"\n{'='*70}")
    print("Step 2: Victim trades (suffers from bad price)")
    print(f"{'='*70}")
    
    victim_amount = 200  # Also increase victim trade
    print(f"👤 Victim selling {victim_amount} TOKEN1...")
    victim_tx = await execute_swap(w3, victim_key, token1_addr, token2_addr, swap_router_addr, victim_amount, "Victim")
    print(f"   TX: {victim_tx[:20]}...")
    
    price_after_victim = get_pool_price(w3, pool_addr, token1_addr, token2_addr)
    print(f"   Price after victim: {price_after_victim:.6f}")
    print(f"   Price change: {((price_after_victim - initial_price) / initial_price * 100):+.2f}%")
    
    print(f"\n{'='*70}")
    print("Step 3: Backrun Bot Rebalances (restores price)")
    print(f"{'='*70}")
    
    # Calculate how much to trade to restore price
    # If price dropped, we need to sell TOKEN2 to buy TOKEN1
    price_deviation = abs(price_after_victim - target_price) / target_price
    
    print(f"🔵 Price deviation: {price_deviation:.2%}")
    
    if price_deviation > 0.001:  # 0.1% threshold (lower)
        if price_after_victim < target_price:
            # TOKEN1 is cheap, buy TOKEN1 (sell TOKEN2)
            rebalance_amount = 300  # Larger rebalance
            print(f"🔄 Backrun bot buying TOKEN1 (selling {rebalance_amount} TOKEN2)...")
            rebalance_tx = await execute_swap(w3, backrun_key, token2_addr, token1_addr, swap_router_addr, rebalance_amount, "Backrun")
        else:
            # TOKEN1 is expensive, sell TOKEN1 (buy TOKEN2)
            rebalance_amount = 300  # Larger rebalance
            print(f"🔄 Backrun bot selling {rebalance_amount} TOKEN1...")
            rebalance_tx = await execute_swap(w3, backrun_key, token1_addr, token2_addr, swap_router_addr, rebalance_amount, "Backrun")
        
        print(f"   TX: {rebalance_tx[:20]}...")
        
        price_after_backrun = get_pool_price(w3, pool_addr, token1_addr, token2_addr)
        print(f"   Price after backrun: {price_after_backrun:.6f}")
        print(f"   Price restored to: {((price_after_backrun - initial_price) / initial_price * 100):+.2f}% of original")
    else:
        print(f"   ℹ️  Deviation below threshold, no rebalance needed")
        price_after_backrun = price_after_victim
    
    print(f"\n{'='*70}")
    print("📊 SUMMARY")
    print(f"{'='*70}")
    print(f"Initial price:       {initial_price:.6f}")
    print(f"After front-run:     {price_after_frontrun:.6f} ({((price_after_frontrun - initial_price) / initial_price * 100):+.2f}%)")
    print(f"After victim:        {price_after_victim:.6f} ({((price_after_victim - initial_price) / initial_price * 100):+.2f}%)")
    print(f"After backrun:       {price_after_backrun:.6f} ({((price_after_backrun - initial_price) / initial_price * 100):+.2f}%)")
    
    # Check if backrun successfully reduced deviation
    deviation_before = abs(price_after_victim - initial_price) / initial_price
    deviation_after = abs(price_after_backrun - initial_price) / initial_price
    
    print(f"\nDeviation before backrun: {deviation_before:.2%}")
    print(f"Deviation after backrun:  {deviation_after:.2%}")
    
    if deviation_after < deviation_before:
        print(f"\n✅ Backrun bot successfully reduced price deviation!")
        improvement = (deviation_before - deviation_after) / deviation_before * 100
        print(f"   Improvement: {improvement:.1f}%")
        return True
    else:
        print(f"\n⚠️  Backrun did not improve price")
        return False


if __name__ == "__main__":
    try:
        result = asyncio.run(test_backrun_rebalance())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

