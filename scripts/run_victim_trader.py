#!/usr/bin/env python3
"""
Victim Trader - Simulates normal trading activity on the blockchain

This script continuously executes trades on Uniswap V3, simulating normal user behavior.
Can be used standalone or in conjunction with MEV bots to demonstrate MEV attacks.

Usage:
    python scripts/run_victim_trader.py --trades 100 --interval 10
    
Author: paul.kwon@circle.com
"""
import asyncio
import argparse
import sys
import os
from web3 import Web3
from eth_account import Account
import random
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.deployment.uniswap_v3_abis import ERC20_ABI, SWAP_ROUTER_ABI


class VictimTrader:
    def __init__(self, w3, private_key, token1_addr, token2_addr, swap_router_addr, pool_addr):
        self.w3 = w3
        self.account = Account.from_key(private_key)
        self.token1_addr = token1_addr
        self.token2_addr = token2_addr
        self.swap_router_addr = swap_router_addr
        self.pool_addr = pool_addr
        
        self.token1 = w3.eth.contract(address=token1_addr, abi=ERC20_ABI)
        self.token2 = w3.eth.contract(address=token2_addr, abi=ERC20_ABI)
        self.swap_router = w3.eth.contract(address=swap_router_addr, abi=SWAP_ROUTER_ABI)
        
        self.trades_executed = 0
        self.total_volume = 0
        
    def get_pool_price(self):
        """Get current pool price ratio"""
        balance1 = self.token1.functions.balanceOf(self.pool_addr).call()
        balance2 = self.token2.functions.balanceOf(self.pool_addr).call()
        return balance2 / balance1 if balance1 > 0 else 0
        
    async def execute_trade(self, amount: float, sell_token1: bool = True):
        """Execute a single trade"""
        try:
            token_in = self.token1_addr if sell_token1 else self.token2_addr
            token_out = self.token2_addr if sell_token1 else self.token1_addr
            token_in_contract = self.token1 if sell_token1 else self.token2
            
            amount_wei = self.w3.to_wei(amount, 'ether')
            
            # Approve if needed
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
                    'maxFeePerGas': self.w3.to_wei(350, 'gwei'),
                    'maxPriorityFeePerGas': self.w3.to_wei(70, 'gwei'),
                })
                
                signed = self.w3.eth.account.sign_transaction(approve_tx, self.account.key)
                self.w3.eth.send_raw_transaction(signed.raw_transaction)
                await asyncio.sleep(2)
            
            # Execute swap
            swap_params = {
                'tokenIn': token_in,
                'tokenOut': token_out,
                'fee': 3000,
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
                'maxFeePerGas': self.w3.to_wei(350, 'gwei'),
                'maxPriorityFeePerGas': self.w3.to_wei(70, 'gwei'),
            })
            
            signed = self.w3.eth.account.sign_transaction(swap_tx, self.account.key)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
            
            self.trades_executed += 1
            self.total_volume += amount
            
            return {
                'success': True,
                'tx_hash': tx_hash.hex(),
                'block': receipt['blockNumber'],
                'amount': amount,
                'direction': 'TOKEN1→TOKEN2' if sell_token1 else 'TOKEN2→TOKEN1'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def run(self, num_trades: int, interval: int, random_amount: bool = True):
        """Run victim trading loop"""
        print("="*70)
        print("Victim Trader Started")
        print("="*70)
        print(f"Address: {self.account.address}")
        print(f"Target trades: {num_trades}")
        print(f"Interval: {interval}s")
        print(f"Random amounts: {random_amount}")
        print("="*70)
        print()
        
        for i in range(num_trades):
            try:
                # Random trade parameters
                if random_amount:
                    amount = random.uniform(20, 100)
                else:
                    amount = 50
                
                sell_token1 = random.choice([True, False])
                
                # Get price before
                price_before = self.get_pool_price()
                
                timestamp = time.strftime("%H:%M:%S")
                print(f"[{timestamp}] Trade {i+1}/{num_trades}")
                print(f"  Amount: {amount:.2f} {'TOKEN1' if sell_token1 else 'TOKEN2'}")
                print(f"  Pool price before: {price_before:.6f}")
                
                # Execute trade
                result = await self.execute_trade(amount, sell_token1)
                
                if result['success']:
                    price_after = self.get_pool_price()
                    price_impact = ((price_after - price_before) / price_before) * 100
                    
                    print(f"  ✅ TX: {result['tx_hash'][:20]}...")
                    print(f"  Block: {result['block']}")
                    print(f"  Pool price after: {price_after:.6f}")
                    print(f"  Price impact: {price_impact:+.3f}%")
                else:
                    print(f"  ❌ Failed: {result['error']}")
                
                print(f"  Total trades: {self.trades_executed}, Volume: {self.total_volume:.2f}")
                print()
                
                # Wait before next trade
                if i < num_trades - 1:
                    await asyncio.sleep(interval)
                    
            except KeyboardInterrupt:
                print("\n\n⚠️  Trader stopped by user")
                break
            except Exception as e:
                print(f"  ❌ Error: {e}")
                await asyncio.sleep(interval)
        
        print("="*70)
        print("Victim Trader Summary")
        print("="*70)
        print(f"Total trades executed: {self.trades_executed}/{num_trades}")
        print(f"Total volume: {self.total_volume:.2f} tokens")
        print(f"Success rate: {self.trades_executed/num_trades*100:.1f}%")
        print("="*70)


async def main():
    parser = argparse.ArgumentParser(description='Run victim trader on blockchain')
    parser.add_argument('--trades', type=int, default=10, help='Number of trades to execute')
    parser.add_argument('--interval', type=int, default=10, help='Seconds between trades')
    parser.add_argument('--amount', type=float, help='Fixed amount per trade (default: random 20-100)')
    parser.add_argument('--rpc', default='https://arc-testnet.stg.blockchain.circle.com', help='RPC URL')
    parser.add_argument('--private-key', default='0x4d58edafc0c6889c6f211cc842a561835015eeaf273d9f8c8ec7ee960804f7ce', help='Private key')
    
    args = parser.parse_args()
    
    # Setup
    w3 = Web3(Web3.HTTPProvider(args.rpc))
    
    token1_addr = w3.to_checksum_address("0x6911406ae5C9fa9314B4AEc086304c001fb3b656")
    token2_addr = w3.to_checksum_address("0x3eaE1139A9A19517B0dB5696073d957542886BF8")
    pool_addr = w3.to_checksum_address("0x39A9Ba5F012aB6D6fc90E563C72bD85949Ca0FF6")
    swap_router_addr = w3.to_checksum_address("0xe372f58a9e03c7b56b3ea9a2a08f18767b75ca67")
    
    # Create and run trader
    trader = VictimTrader(
        w3=w3,
        private_key=args.private_key,
        token1_addr=token1_addr,
        token2_addr=token2_addr,
        swap_router_addr=swap_router_addr,
        pool_addr=pool_addr
    )
    
    await trader.run(
        num_trades=args.trades,
        interval=args.interval,
        random_amount=(args.amount is None)
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted")
        sys.exit(0)

