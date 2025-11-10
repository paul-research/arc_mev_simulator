#!/usr/bin/env python3
"""
Backrun Bot - Maintains pool price stability through arbitrage

This bot continuously monitors the pool price and executes arbitrage trades
to restore it to the target ratio, providing beneficial MEV that improves
market efficiency.

Usage:
    python scripts/run_backrun_bot.py --target-ratio 2.0 --threshold 0.005
    
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


class BackrunBot:
    def __init__(self, w3, private_key, token1_addr, token2_addr, swap_router_addr, pool_addr, 
                 target_ratio=2.0, threshold=0.005):
        self.w3 = w3
        self.account = Account.from_key(private_key)
        self.token1_addr = token1_addr
        self.token2_addr = token2_addr
        self.swap_router_addr = swap_router_addr
        self.pool_addr = pool_addr
        self.target_ratio = target_ratio
        self.threshold = threshold
        
        self.token1 = w3.eth.contract(address=token1_addr, abi=ERC20_ABI)
        self.token2 = w3.eth.contract(address=token2_addr, abi=ERC20_ABI)
        self.swap_router = w3.eth.contract(address=swap_router_addr, abi=SWAP_ROUTER_ABI)
        
        self.rebalances_executed = 0
        self.total_volume = 0
        
    def get_pool_price(self):
        """Get current pool price ratio (TOKEN2/TOKEN1)"""
        balance1 = self.token1.functions.balanceOf(self.pool_addr).call()
        balance2 = self.token2.functions.balanceOf(self.pool_addr).call()
        
        if balance1 == 0:
            return 0
        
        return balance2 / balance1
    
    def get_pool_reserves(self):
        """Get pool reserve balances"""
        balance1 = self.token1.functions.balanceOf(self.pool_addr).call()
        balance2 = self.token2.functions.balanceOf(self.pool_addr).call()
        return (
            self.w3.from_wei(balance1, 'ether'),
            self.w3.from_wei(balance2, 'ether')
        )
    
    async def execute_rebalance(self, amount: float, sell_token1: bool):
        """Execute a rebalance trade"""
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
                    'maxFeePerGas': self.w3.to_wei(400, 'gwei'),
                    'maxPriorityFeePerGas': self.w3.to_wei(80, 'gwei'),
                })
                
                signed = self.w3.eth.account.sign_transaction(approve_tx, self.account.key)
                self.w3.eth.send_raw_transaction(signed.raw_transaction)
                await asyncio.sleep(2)
            
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
            swap_tx = self.swap_router.functions.exactInputSingle(swap_params).build_transaction({
                'from': self.account.address,
                'nonce': nonce,
                'gas': 800000,
                'maxFeePerGas': self.w3.to_wei(400, 'gwei'),
                'maxPriorityFeePerGas': self.w3.to_wei(80, 'gwei'),
            })
            
            signed = self.w3.eth.account.sign_transaction(swap_tx, self.account.key)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
            
            self.rebalances_executed += 1
            self.total_volume += amount
            
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
    
    async def monitor_and_rebalance(self, check_interval: int = 10):
        """Main monitoring and rebalancing loop"""
        print("="*70)
        print("Backrun Bot (Arbitrage) Started")
        print("="*70)
        print(f"Bot Address: {self.account.address}")
        print(f"Target Ratio: {self.target_ratio} (TOKEN2/TOKEN1)")
        print(f"Deviation Threshold: {self.threshold:.2%}")
        print(f"Check Interval: {check_interval}s")
        print("="*70)
        print()
        
        while True:
            try:
                # Get current price and reserves
                current_ratio = self.get_pool_price()
                reserve1, reserve2 = self.get_pool_reserves()
                
                deviation = abs(current_ratio - self.target_ratio) / self.target_ratio
                
                timestamp = time.strftime("%H:%M:%S")
                print(f"[{timestamp}] Pool State")
                print(f"  Reserves: {reserve1:.2f} TOKEN1, {reserve2:.2f} TOKEN2")
                print(f"  Current ratio: {current_ratio:.6f}")
                print(f"  Target ratio: {self.target_ratio}")
                print(f"  Deviation: {deviation:.2%}")
                
                if deviation > self.threshold:
                    print(f"  ⚠️  REBALANCE NEEDED!")
                    
                    # Calculate trade size (proportional to deviation, 5-15% of pool)
                    trade_size = min(reserve1 * 0.15, reserve1 * deviation * 10)
                    trade_size = max(10, trade_size)
                    
                    if current_ratio < self.target_ratio:
                        # Ratio too low: TOKEN2/TOKEN1 < target
                        # Need to increase TOKEN2 or decrease TOKEN1 in pool
                        # Action: BUY TOKEN1 from pool (sell TOKEN2)
                        # This removes TOKEN1, increases ratio
                        print(f"  🔄 Buying TOKEN1 with {trade_size:.2f} TOKEN2")
                        result = await self.execute_rebalance(trade_size, sell_token1=False)
                    else:
                        # Ratio too high: TOKEN2/TOKEN1 > target  
                        # Need to decrease TOKEN2 or increase TOKEN1 in pool
                        # Action: SELL TOKEN1 to pool (buy TOKEN2)
                        # This adds TOKEN1, decreases ratio
                        print(f"  🔄 Selling {trade_size:.2f} TOKEN1")
                        result = await self.execute_rebalance(trade_size, sell_token1=True)
                    
                    if result['success']:
                        new_ratio = self.get_pool_price()
                        new_deviation = abs(new_ratio - self.target_ratio) / self.target_ratio
                        
                        print(f"     ✅ TX: {result['tx_hash'][:20]}... (block {result['block']})")
                        print(f"     New ratio: {new_ratio:.6f}")
                        print(f"     New deviation: {new_deviation:.2%}")
                        print(f"     Improvement: {(deviation - new_deviation):.2%}")
                    else:
                        print(f"     ❌ Failed: {result['error']}")
                else:
                    print(f"  ✓ Price within target range")
                
                print(f"  Stats: {self.rebalances_executed} rebalances, {self.total_volume:.2f} volume")
                print()
                
                await asyncio.sleep(check_interval)
                
            except KeyboardInterrupt:
                print("\n\n⚠️  Bot stopped by user")
                break
            except Exception as e:
                print(f"  ❌ Error: {e}")
                await asyncio.sleep(check_interval)
        
        print("="*70)
        print("Backrun Bot Summary")
        print("="*70)
        print(f"Total rebalances: {self.rebalances_executed}")
        print(f"Total volume: {self.total_volume:.2f} tokens")
        print("="*70)


async def main():
    parser = argparse.ArgumentParser(description='Run backrun arbitrage bot')
    parser.add_argument('--target-ratio', type=float, default=2.0, 
                       help='Target price ratio (TOKEN2/TOKEN1)')
    parser.add_argument('--threshold', type=float, default=0.005,
                       help='Deviation threshold to trigger rebalance (default: 0.5%%)')
    parser.add_argument('--interval', type=int, default=10,
                       help='Check interval in seconds')
    parser.add_argument('--rpc', default='https://arc-testnet.stg.blockchain.circle.com',
                       help='RPC URL')
    parser.add_argument('--private-key',
                       default='0x488e3ab7dc2033bc970e83bc6daf50ed83c4927e5d8f5bd5ca971df3d062cac2',
                       help='Bot private key')
    
    args = parser.parse_args()
    
    # Setup
    w3 = Web3(Web3.HTTPProvider(args.rpc))
    
    token1_addr = w3.to_checksum_address("0x6911406ae5C9fa9314B4AEc086304c001fb3b656")
    token2_addr = w3.to_checksum_address("0x3eaE1139A9A19517B0dB5696073d957542886BF8")
    pool_addr = w3.to_checksum_address("0x39A9Ba5F012aB6D6fc90E563C72bD85949Ca0FF6")  # ACTUAL working pool!
    swap_router_addr = w3.to_checksum_address("0xe372f58a9e03c7b56b3ea9a2a08f18767b75ca67")
    
    bot = BackrunBot(
        w3=w3,
        private_key=args.private_key,
        token1_addr=token1_addr,
        token2_addr=token2_addr,
        swap_router_addr=swap_router_addr,
        pool_addr=pool_addr,
        target_ratio=args.target_ratio,
        threshold=args.threshold
    )
    
    await bot.monitor_and_rebalance(check_interval=args.interval)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted")
        sys.exit(0)

