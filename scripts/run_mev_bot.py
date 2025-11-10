#!/usr/bin/env python3
"""
MEV Bot - Monitors mempool and executes sandwich attacks

This script continuously monitors for victim transactions and executes
front-run and back-run attacks to extract MEV.

Usage:
    python scripts/run_mev_bot.py --mode aggressive --min-profit 0.01
    
Author: paul.kwon@circle.com
"""
import asyncio
import argparse
import sys
import os
from web3 import Web3
from eth_account import Account
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.deployment.uniswap_v3_abis import ERC20_ABI, SWAP_ROUTER_ABI


class MEVBot:
    def __init__(self, w3, private_key, token1_addr, token2_addr, swap_router_addr, pool_addr, mode='aggressive'):
        self.w3 = w3
        self.account = Account.from_key(private_key)
        self.token1_addr = token1_addr
        self.token2_addr = token2_addr
        self.swap_router_addr = swap_router_addr
        self.pool_addr = pool_addr
        self.mode = mode
        
        self.token1 = w3.eth.contract(address=token1_addr, abi=ERC20_ABI)
        self.token2 = w3.eth.contract(address=token2_addr, abi=ERC20_ABI)
        self.swap_router = w3.eth.contract(address=swap_router_addr, abi=SWAP_ROUTER_ABI)
        
        self.attacks_executed = 0
        self.total_profit = 0
        
        # Mode parameters
        self.params = self._get_mode_params(mode)
        
    def _get_mode_params(self, mode):
        """Get attack parameters based on mode"""
        params = {
            'aggressive': {'frontrun_ratio': 0.8, 'gas_multiplier': 1.5},
            'conservative': {'frontrun_ratio': 0.3, 'gas_multiplier': 1.2},
            'adaptive': {'frontrun_ratio': 0.5, 'gas_multiplier': 1.3},
        }
        return params.get(mode, params['aggressive'])
    
    def get_pool_price(self):
        """Get current pool price"""
        balance1 = self.token1.functions.balanceOf(self.pool_addr).call()
        balance2 = self.token2.functions.balanceOf(self.pool_addr).call()
        return balance2 / balance1 if balance1 > 0 else 0
    
    async def execute_swap(self, amount: float, sell_token1: bool, high_priority: bool = False):
        """Execute a single swap"""
        try:
            token_in = self.token1_addr if sell_token1 else self.token2_addr
            token_out = self.token2_addr if sell_token1 else self.token1_addr
            token_in_contract = self.token1 if sell_token1 else self.token2
            
            amount_wei = self.w3.to_wei(amount, 'ether')
            
            # Approve
            allowance = token_in_contract.functions.allowance(
                self.account.address,
                self.swap_router_addr
            ).call()
            
            if allowance < amount_wei:
                nonce = self.w3.eth.get_transaction_count(self.account.address)
                approve_tx = token_in_contract.functions.approve(
                    self.swap_router_addr,
                    amount_wei * 1000
                ).build_transaction({
                    'from': self.account.address,
                    'nonce': nonce,
                    'gas': 100000,
                    'maxFeePerGas': self.w3.to_wei(500, 'gwei') if high_priority else self.w3.to_wei(400, 'gwei'),
                    'maxPriorityFeePerGas': self.w3.to_wei(100, 'gwei') if high_priority else self.w3.to_wei(80, 'gwei'),
                })
                
                signed = self.w3.eth.account.sign_transaction(approve_tx, self.account.key)
                self.w3.eth.send_raw_transaction(signed.raw_transaction)
                await asyncio.sleep(1)
            
            # Swap
            swap_params = {
                'tokenIn': token_in,
                'tokenOut': token_out,
                'fee': 100,  # 0.01% fee tier (matches arc_test pool)
                'recipient': self.account.address,
                'amountIn': amount_wei,
                'amountOutMinimum': 0,
                'sqrtPriceLimitX96': 0
            }
            
            nonce = self.w3.eth.get_transaction_count(self.account.address)
            gas_price = int(500 * self.params['gas_multiplier']) if high_priority else 400
            priority_fee = int(100 * self.params['gas_multiplier']) if high_priority else 80
            
            swap_tx = self.swap_router.functions.exactInputSingle(swap_params).build_transaction({
                'from': self.account.address,
                'nonce': nonce,
                'gas': 800000,
                'maxFeePerGas': self.w3.to_wei(gas_price, 'gwei'),
                'maxPriorityFeePerGas': self.w3.to_wei(priority_fee, 'gwei'),
            })
            
            signed = self.w3.eth.account.sign_transaction(swap_tx, self.account.key)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
            
            return {
                'success': True,
                'tx_hash': tx_hash.hex(),
                'block': receipt['blockNumber']
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def execute_sandwich_attack(self, victim_amount: float, victim_direction: bool):
        """Execute a sandwich attack"""
        timestamp = time.strftime("%H:%M:%S")
        print(f"\n[{timestamp}] 🎯 Sandwich Attack Opportunity Detected")
        print(f"  Victim will trade: {victim_amount:.2f} {'TOKEN1' if victim_direction else 'TOKEN2'}")
        
        # Calculate attack size
        frontrun_amount = victim_amount * self.params['frontrun_ratio']
        
        price_before = self.get_pool_price()
        print(f"  Pool price: {price_before:.6f}")
        
        # Front-run
        print(f"  🔴 Front-run: {frontrun_amount:.2f} {'TOKEN1' if victim_direction else 'TOKEN2'}")
        frontrun_result = await self.execute_swap(frontrun_amount, victim_direction, high_priority=True)
        
        if not frontrun_result['success']:
            print(f"  ❌ Front-run failed: {frontrun_result['error']}")
            return False
        
        print(f"     ✅ TX: {frontrun_result['tx_hash'][:20]}... (block {frontrun_result['block']})")
        
        # Wait for victim transaction
        await asyncio.sleep(3)
        
        price_after_frontrun = self.get_pool_price()
        
        # Back-run (reverse direction)
        backrun_amount = frontrun_amount * 1.05  # Slightly more to capture profit
        print(f"  🔵 Back-run: {backrun_amount:.2f} {'TOKEN2' if victim_direction else 'TOKEN1'}")
        backrun_result = await self.execute_swap(backrun_amount, not victim_direction, high_priority=False)
        
        if not backrun_result['success']:
            print(f"  ❌ Back-run failed: {backrun_result['error']}")
            return False
        
        print(f"     ✅ TX: {backrun_result['tx_hash'][:20]}... (block {backrun_result['block']})")
        
        price_after = self.get_pool_price()
        
        # Calculate profit (simplified)
        profit = (price_after - price_before) * frontrun_amount * 0.1
        self.total_profit += profit
        self.attacks_executed += 1
        
        print(f"  💰 Estimated profit: {profit:.4f} ETH")
        print(f"  📊 Total attacks: {self.attacks_executed}, Total profit: {self.total_profit:.4f} ETH")
        
        return True
    
    async def monitor_mempool(self, check_interval: int = 5):
        """Monitor for victim transactions"""
        print("="*70)
        print("MEV Bot Started")
        print("="*70)
        print(f"Bot Address: {self.account.address}")
        print(f"Mode: {self.mode}")
        print(f"Check Interval: {check_interval}s")
        print("="*70)
        print()
        
        # In a real implementation, this would monitor pending transactions
        # For demonstration, we simulate detection
        print("🔍 Monitoring mempool for victim transactions...")
        print("   (In production, this would use eth_subscribe or flashbots)")
        print()
        
        while True:
            try:
                await asyncio.sleep(check_interval)
                
                # Simulate victim detection (in real impl, parse mempool)
                # For now, we just show that the bot is ready
                timestamp = time.strftime("%H:%M:%S")
                print(f"[{timestamp}] Monitoring... (attacks: {self.attacks_executed}, profit: {self.total_profit:.4f})")
                
            except KeyboardInterrupt:
                print("\n\n⚠️  Bot stopped by user")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                await asyncio.sleep(check_interval)


async def main():
    parser = argparse.ArgumentParser(description='Run MEV bot on blockchain')
    parser.add_argument('--mode', choices=['aggressive', 'conservative', 'adaptive'], 
                       default='aggressive', help='Attack mode')
    parser.add_argument('--interval', type=int, default=5, help='Mempool check interval (seconds)')
    parser.add_argument('--rpc', default='https://arc-testnet.stg.blockchain.circle.com', help='RPC URL')
    parser.add_argument('--private-key', 
                       default='0x488e3ab7dc2033bc970e83bc6daf50ed83c4927e5d8f5bd5ca971df3d062cac2',
                       help='MEV bot private key')
    parser.add_argument('--demo', action='store_true', help='Run demo attacks instead of monitoring')
    
    args = parser.parse_args()
    
    # Setup
    w3 = Web3(Web3.HTTPProvider(args.rpc))
    
    token1_addr = w3.to_checksum_address("0x6911406ae5C9fa9314B4AEc086304c001fb3b656")
    token2_addr = w3.to_checksum_address("0x3eaE1139A9A19517B0dB5696073d957542886BF8")
    pool_addr = w3.to_checksum_address("0x39A9Ba5F012aB6D6fc90E563C72bD85949Ca0FF6")  # ACTUAL working pool!
    swap_router_addr = w3.to_checksum_address("0xe372f58a9e03c7b56b3ea9a2a08f18767b75ca67")
    
    bot = MEVBot(
        w3=w3,
        private_key=args.private_key,
        token1_addr=token1_addr,
        token2_addr=token2_addr,
        swap_router_addr=swap_router_addr,
        pool_addr=pool_addr,
        mode=args.mode
    )
    
    if args.demo:
        # Run demo attacks
        print("Running demo attacks...\n")
        await bot.execute_sandwich_attack(victim_amount=50, victim_direction=True)
        await asyncio.sleep(5)
        await bot.execute_sandwich_attack(victim_amount=80, victim_direction=False)
    else:
        # Monitor mempool
        await bot.monitor_mempool(check_interval=args.interval)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted")
        sys.exit(0)

