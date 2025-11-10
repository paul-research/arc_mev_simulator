#!/usr/bin/env python3
"""
Simple test to verify victim can execute a swap transaction on Arc Testnet
"""
import asyncio
import sys
import os
from web3 import Web3
from eth_account import Account

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.deployment.deployer import ContractDeployer
from src.deployment.uniswap_v3_abis import ERC20_ABI, SWAP_ROUTER_ABI


async def test_victim_swap():
    print("=" * 60)
    print("Testing Victim Swap Transaction")
    print("=" * 60)
    
    # Configuration
    rpc_url = "https://arc-testnet.stg.blockchain.circle.com"
    victim_key = "0x4d58edafc0c6889c6f211cc842a561835015eeaf273d9f8c8ec7ee960804f7ce"
    
    # Setup Web3 first to use to_checksum_address
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    token1_address = w3.to_checksum_address("0x6911406ae5C9fa9314B4AEc086304c001fb3b656")
    token2_address = w3.to_checksum_address("0x3eaE1139A9A19517B0dB5696073d957542886BF8")
    swap_router_address = w3.to_checksum_address("0xe372f58a9e03c7b56b3ea9a2a08f18767b75ca67")
    pool_address = w3.to_checksum_address("0x39A9Ba5F012aB6D6fc90E563C72bD85949Ca0FF6")
    
    victim_account = Account.from_key(victim_key)
    
    print(f"\n📍 Victim Address: {victim_account.address}")
    print(f"💰 Balance: {w3.from_wei(w3.eth.get_balance(victim_account.address), 'ether')} ETH")
    print(f"📦 Tx Count: {w3.eth.get_transaction_count(victim_account.address)}")
    
    # Check token balances
    token1 = w3.eth.contract(address=token1_address, abi=ERC20_ABI)
    token2 = w3.eth.contract(address=token2_address, abi=ERC20_ABI)
    
    token1_balance = token1.functions.balanceOf(victim_account.address).call()
    token2_balance = token2.functions.balanceOf(victim_account.address).call()
    
    print(f"\n💎 TOKEN1 Balance: {w3.from_wei(token1_balance, 'ether')}")
    print(f"💎 TOKEN2 Balance: {w3.from_wei(token2_balance, 'ether')}")
    
    # Prepare swap: 50 TOKEN1 -> TOKEN2
    amount_in = w3.to_wei(50, 'ether')
    
    print(f"\n🔄 Executing swap: 50 TOKEN1 -> TOKEN2")
    
    # Step 1: Approve
    print("Step 1: Approving...")
    current_allowance = token1.functions.allowance(victim_account.address, swap_router_address).call()
    
    if current_allowance < amount_in:
        nonce = w3.eth.get_transaction_count(victim_account.address)
        approve_tx = token1.functions.approve(
            swap_router_address,
            amount_in
        ).build_transaction({
            'from': victim_account.address,
            'nonce': nonce,
            'gas': 100000,
            'maxFeePerGas': w3.to_wei(400, 'gwei'),
            'maxPriorityFeePerGas': w3.to_wei(80, 'gwei'),
        })
        
        signed_approve = w3.eth.account.sign_transaction(approve_tx, victim_key)
        approve_hash = w3.eth.send_raw_transaction(signed_approve.raw_transaction)
        print(f"Approve TX: {approve_hash.hex()}")
        
        approve_receipt = w3.eth.wait_for_transaction_receipt(approve_hash, timeout=120)
        print(f"✅ Approved at block {approve_receipt['blockNumber']}")
    else:
        print(f"✅ Already approved (allowance: {w3.from_wei(current_allowance, 'ether')})")
    
    # Step 2: Swap
    print("\nStep 2: Executing swap...")
    swap_router = w3.eth.contract(address=swap_router_address, abi=SWAP_ROUTER_ABI)
    
    swap_params = {
        'tokenIn': token1_address,
        'tokenOut': token2_address,
        'fee': 3000,  # 0.3%
        'recipient': victim_account.address,
        'amountIn': amount_in,
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
    print(f"Swap TX: {swap_hash.hex()}")
    
    swap_receipt = w3.eth.wait_for_transaction_receipt(swap_hash, timeout=120)
    
    if swap_receipt['status'] == 1:
        print(f"✅ Swap successful at block {swap_receipt['blockNumber']}")
        print(f"Gas used: {swap_receipt['gasUsed']}")
        
        # Check new balances
        new_token1_balance = token1.functions.balanceOf(victim_account.address).call()
        new_token2_balance = token2.functions.balanceOf(victim_account.address).call()
        
        token1_diff = w3.from_wei(new_token1_balance - token1_balance, 'ether')
        token2_diff = w3.from_wei(new_token2_balance - token2_balance, 'ether')
        
        print(f"\n📊 Balance Changes:")
        print(f"   TOKEN1: {token1_diff:+.2f}")
        print(f"   TOKEN2: {token2_diff:+.2f}")
        
        print(f"\n🎉 SUCCESS! Transaction is on-chain and verifiable.")
        print(f"   Block: {swap_receipt['blockNumber']}")
        print(f"   TX: {swap_hash.hex()}")
        
    else:
        print(f"❌ Swap failed!")
        return False
    
    return True


if __name__ == "__main__":
    result = asyncio.run(test_victim_swap())
    sys.exit(0 if result else 1)

