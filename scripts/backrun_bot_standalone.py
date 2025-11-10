#!/usr/bin/env python3
"""
Standalone Backrun Bot - Continuously monitors and rebalances pool price to target
Run this separately from the simulator to maintain price stability
"""
import asyncio
import sys
import os
from web3 import Web3
from eth_account import Account
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.deployment.uniswap_v3_abis import ERC20_ABI, SWAP_ROUTER_ABI


class StandaloneBackrunBot:
    def __init__(self, w3, bot_key, token1_addr, token2_addr, pool_addr, swap_router_addr, target_ratio=2.0, threshold=0.005):
        self.w3 = w3
        self.bot_account = Account.from_key(bot_key)
        self.token1_addr = token1_addr
        self.token2_addr = token2_addr
        self.pool_addr = pool_addr
        self.swap_router_addr = swap_router_addr
        self.target_ratio = target_ratio  # 2.0 means TOKEN2/TOKEN1 = 2
        self.threshold = threshold  # 0.5% deviation threshold
        
        self.token1 = w3.eth.contract(address=token1_addr, abi=ERC20_ABI)
        self.token2 = w3.eth.contract(address=token2_addr, abi=ERC20_ABI)
        self.swap_router = w3.eth.contract(address=swap_router_addr, abi=SWAP_ROUTER_ABI)
        
        self.trades_executed = 0
        
    def get_pool_price(self):
        """Get current pool price ratio (TOKEN2/TOKEN1)"""
        pool_balance1 = self.token1.functions.balanceOf(self.pool_addr).call()
        pool_balance2 = self.token2.functions.balanceOf(self.pool_addr).call()
        
        if pool_balance1 == 0:
            return 0
        
        return pool_balance2 / pool_balance1
    
    async def execute_rebalance(self, sell_token1: bool, amount: float):
        """Execute a rebalance trade"""
        try:
            if sell_token1:
                # Sell TOKEN1 to buy TOKEN2 (decrease ratio)
                token_in = self.token1_addr
                token_out = self.token2_addr
                token_in_contract = self.token1
                print(f"   → Selling {amount:.2f} TOKEN1")
            else:
                # Sell TOKEN2 to buy TOKEN1 (increase ratio)
                token_in = self.token2_addr
                token_out = self.token1_addr
                token_in_contract = self.token2
                print(f"   → Selling {amount:.2f} TOKEN2")
            
            amount_wei = self.w3.to_wei(amount, 'ether')
            
            # Approve if needed
            allowance = token_in_contract.functions.allowance(
                self.bot_account.address, 
                self.swap_router_addr
            ).call()
            
            if allowance < amount_wei:
                nonce = self.w3.eth.get_transaction_count(self.bot_account.address)
                approve_tx = token_in_contract.functions.approve(
                    self.swap_router_addr, 
                    amount_wei * 100
                ).build_transaction({
                    'from': self.bot_account.address,
                    'nonce': nonce,
                    'gas': 100000,
                    'maxFeePerGas': self.w3.to_wei(400, 'gwei'),
                    'maxPriorityFeePerGas': self.w3.to_wei(80, 'gwei'),
                })
                
                signed = self.w3.eth.account.sign_transaction(approve_tx, self.bot_account.key)
                self.w3.eth.send_raw_transaction(signed.raw_transaction)
                await asyncio.sleep(2)
            
            # Execute swap
            swap_params = {
                'tokenIn': token_in,
                'tokenOut': token_out,
                'fee': 3000,
                'recipient': self.bot_account.address,
                'amountIn': amount_wei,
                'amountOutMinimum': 0,
                'sqrtPriceLimitX96': 0
            }
            
            nonce = self.w3.eth.get_transaction_count(self.bot_account.address)
            swap_tx = self.swap_router.functions.exactInputSingle(swap_params).build_transaction({
                'from': self.bot_account.address,
                'nonce': nonce,
                'gas': 800000,
                'maxFeePerGas': self.w3.to_wei(400, 'gwei'),
                'maxPriorityFeePerGas': self.w3.to_wei(80, 'gwei'),
            })
            
            signed = self.w3.eth.account.sign_transaction(swap_tx, self.bot_account.key)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
            print(f"   ✅ TX: {tx_hash.hex()[:20]}... (block {receipt['blockNumber']})")
            
            self.trades_executed += 1
            return True
            
        except Exception as e:
            print(f"   ❌ Rebalance failed: {e}")
            return False
    
    async def monitor_loop(self, check_interval=5):
        """Main monitoring loop"""
        print(f"🤖 Backrun Bot Started")
        print(f"   Bot Address: {self.bot_account.address}")
        print(f"   Target Ratio: {self.target_ratio}")
        print(f"   Threshold: {self.threshold:.2%}")
        print(f"   Check Interval: {check_interval}s")
        print(f"\n{'='*70}\n")
        
        while True:
            try:
                current_ratio = self.get_pool_price()
                deviation = abs(current_ratio - self.target_ratio) / self.target_ratio
                
                timestamp = time.strftime("%H:%M:%S")
                print(f"[{timestamp}] Pool Price: {current_ratio:.6f} | Target: {self.target_ratio} | Deviation: {deviation:.2%}")
                
                if deviation > self.threshold:
                    print(f"⚠️  DEVIATION DETECTED! Rebalancing...")
                    
                    # Calculate trade size (proportional to deviation)
                    pool_balance1 = self.token1.functions.balanceOf(self.pool_addr).call()
                    pool_size = self.w3.from_wei(pool_balance1, 'ether')
                    
                    # Trade 5-10% of pool size depending on deviation
                    trade_size = min(pool_size * 0.1, pool_size * deviation * 20)
                    trade_size = max(10, trade_size)  # Minimum 10 tokens
                    
                    if current_ratio > self.target_ratio:
                        # Ratio too high -> TOKEN2 too much -> sell TOKEN1 (makes ratio even higher, wrong!)
                        # Actually: ratio too high means TOKEN2/TOKEN1 too high -> need to decrease TOKEN2 or increase TOKEN1
                        # So we should BUY TOKEN1 (sell TOKEN2)
                        success = await self.execute_rebalance(sell_token1=False, amount=trade_size)
                    else:
                        # Ratio too low -> need to increase TOKEN2 or decrease TOKEN1
                        # So we should SELL TOKEN1 (buy TOKEN2)
                        success = await self.execute_rebalance(sell_token1=True, amount=trade_size)
                    
                    if success:
                        new_ratio = self.get_pool_price()
                        new_deviation = abs(new_ratio - self.target_ratio) / self.target_ratio
                        print(f"   New Price: {new_ratio:.6f} | New Deviation: {new_deviation:.2%}")
                        print(f"   Total Trades: {self.trades_executed}\n")
                    else:
                        print(f"   Rebalance failed, will retry next cycle\n")
                else:
                    print(f"   ✓ Price within target range\n")
                
                await asyncio.sleep(check_interval)
                
            except KeyboardInterrupt:
                print(f"\n\n🛑 Bot stopped by user")
                print(f"Total trades executed: {self.trades_executed}")
                break
            except Exception as e:
                print(f"   ❌ Error: {e}")
                await asyncio.sleep(check_interval)


async def main():
    # Configuration
    rpc_url = "https://arc-testnet.stg.blockchain.circle.com"
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    bot_key = "0x488e3ab7dc2033bc970e83bc6daf50ed83c4927e5d8f5bd5ca971df3d062cac2"
    
    token1_addr = w3.to_checksum_address("0x6911406ae5C9fa9314B4AEc086304c001fb3b656")
    token2_addr = w3.to_checksum_address("0x3eaE1139A9A19517B0dB5696073d957542886BF8")
    pool_addr = w3.to_checksum_address("0x39A9Ba5F012aB6D6fc90E563C72bD85949Ca0FF6")
    swap_router_addr = w3.to_checksum_address("0xe372f58a9e03c7b56b3ea9a2a08f18767b75ca67")
    
    # Create and start bot
    bot = StandaloneBackrunBot(
        w3=w3,
        bot_key=bot_key,
        token1_addr=token1_addr,
        token2_addr=token2_addr,
        pool_addr=pool_addr,
        swap_router_addr=swap_router_addr,
        target_ratio=2.0,  # TARGET: TOKEN2/TOKEN1 = 2.0
        threshold=0.005    # 0.5% deviation threshold
    )
    
    await bot.monitor_loop(check_interval=10)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Bot interrupted")
        sys.exit(0)

