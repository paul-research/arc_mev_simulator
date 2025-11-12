#!/usr/bin/env python3
"""
MEV Bot with Block Monitoring (Real-time)

Since Arc Testnet has fast block times (~2s) and transactions don't stay
in mempool long, we monitor new blocks and attack in the NEXT block.

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


class BlockMonitoringMEVBot:
    def __init__(self, w3, private_key, token1_addr, token2_addr, swap_router_addr, pool_addr, mode='aggressive'):
        self.w3 = w3
        self.account = Account.from_key(private_key)
        self.token1_addr = w3.to_checksum_address(token1_addr)
        self.token2_addr = w3.to_checksum_address(token2_addr)
        self.swap_router_addr = w3.to_checksum_address(swap_router_addr)
        self.pool_addr = w3.to_checksum_address(pool_addr)
        self.mode = mode
        
        self.token1 = w3.eth.contract(address=self.token1_addr, abi=ERC20_ABI)
        self.token2 = w3.eth.contract(address=self.token2_addr, abi=ERC20_ABI)
        self.swap_router = w3.eth.contract(address=self.swap_router_addr, abi=SWAP_ROUTER_ABI)
        
        self.attacks_executed = 0
        self.total_profit = 0
        self.last_block = 0
        
        # Mode parameters
        self.params = self._get_mode_params(mode)
        
        print(f"🤖 MEV Bot initialized (Block Monitoring)")
        print(f"   Address: {self.account.address}")
        print(f"   Mode: {mode}")
        print(f"   Strategy: Monitor blocks, attack next block")
        
    def _get_mode_params(self, mode):
        """Get attack parameters based on mode"""
        params = {
            'aggressive': {'frontrun_ratio': 0.6, 'gas_multiplier': 1.5, 'min_profit': 0.01},
            'conservative': {'frontrun_ratio': 0.3, 'gas_multiplier': 1.2, 'min_profit': 0.05},
            'adaptive': {'frontrun_ratio': 0.5, 'gas_multiplier': 1.3, 'min_profit': 0.02},
        }
        return params.get(mode, params['aggressive'])
    
    def get_pool_price(self):
        """Get current pool price"""
        try:
            balance1 = self.token1.functions.balanceOf(self.pool_addr).call()
            balance2 = self.token2.functions.balanceOf(self.pool_addr).call()
            return float(balance2) / float(balance1) if balance1 > 0 else 0
        except Exception as e:
            return 0
    
    def decode_swap_transaction(self, tx):
        """Decode transaction to check if it's a swap on our pool"""
        try:
            if not tx['to'] or tx['to'].lower() != self.swap_router_addr.lower():
                return None
            
            if not tx['input'] or len(tx['input']) < 10:
                return None
            
            func_sig = tx['input'][:10]
            if func_sig != '0x414bf389':  # exactInputSingle
                return None
            
            try:
                decoded = self.swap_router.decode_function_input(tx['input'])
                params = decoded[1]
                
                token_in = self.w3.to_checksum_address(params['tokenIn'])
                token_out = self.w3.to_checksum_address(params['tokenOut'])
                
                if not ((token_in == self.token1_addr and token_out == self.token2_addr) or
                        (token_in == self.token2_addr and token_out == self.token1_addr)):
                    return None
                
                amount_in = float(self.w3.from_wei(params['amountIn'], 'ether'))
                
                return {
                    'from': tx['from'],
                    'token_in': token_in,
                    'token_out': token_out,
                    'amount_in': amount_in,
                    'is_token1_to_token2': token_in == self.token1_addr,
                    'tx_hash': tx['hash'].hex() if isinstance(tx['hash'], bytes) else tx['hash']
                }
            except Exception:
                return None
                
        except Exception:
            return None
    
    def is_profitable(self, victim_swap):
        """Determine if attacking this swap would be profitable"""
        amount = victim_swap['amount_in']
        
        if amount < 20:  # Skip small trades
            return False
        
        # Calculate potential profit
        pool_balance = self.token1.functions.balanceOf(self.pool_addr).call()
        pool_size = float(self.w3.from_wei(pool_balance, 'ether'))
        
        price_impact = (amount / pool_size) * 100
        estimated_profit_pct = price_impact * 0.5
        estimated_profit = amount * (estimated_profit_pct / 100)
        
        return estimated_profit > self.params['min_profit']
    
    async def execute_swap(self, amount: float, sell_token1: bool, high_priority: bool = False):
        """Execute a single swap"""
        try:
            token_in = self.token1_addr if sell_token1 else self.token2_addr
            token_out = self.token2_addr if sell_token1 else self.token1_addr
            token_in_contract = self.token1 if sell_token1 else self.token2
            
            amount_wei = self.w3.to_wei(amount, 'ether')
            
            # Check/approve
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
                    'maxFeePerGas': self.w3.to_wei(500, 'gwei'),
                    'maxPriorityFeePerGas': self.w3.to_wei(100, 'gwei'),
                    'chainId': 5042002
                })
                
                signed = self.w3.eth.account.sign_transaction(approve_tx, self.account.key)
                self.w3.eth.send_raw_transaction(signed.raw_transaction)
                await asyncio.sleep(2)
            
            # Swap
            swap_params = {
                'tokenIn': token_in,
                'tokenOut': token_out,
                'fee': 100,
                'recipient': self.account.address,
                'amountIn': amount_wei,
                'amountOutMinimum': 0,
                'sqrtPriceLimitX96': 0
            }
            
            nonce = self.w3.eth.get_transaction_count(self.account.address)
            gas_price = int(600 * self.params['gas_multiplier']) if high_priority else 400
            priority_fee = int(120 * self.params['gas_multiplier']) if high_priority else 80
            
            swap_tx = self.swap_router.functions.exactInputSingle(swap_params).build_transaction({
                'from': self.account.address,
                'nonce': nonce,
                'gas': 800000,
                'maxFeePerGas': self.w3.to_wei(gas_price, 'gwei'),
                'maxPriorityFeePerGas': self.w3.to_wei(priority_fee, 'gwei'),
                'chainId': 5042002
            })
            
            signed = self.w3.eth.account.sign_transaction(swap_tx, self.account.key)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
            
            return {
                'success': receipt['status'] == 1,
                'tx_hash': tx_hash.hex(),
                'block': receipt['blockNumber'],
                'gas_used': receipt['gasUsed']
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def execute_sandwich_attack(self, victim_swap):
        """Execute sandwich attack"""
        timestamp = time.strftime("%H:%M:%S")
        print(f"\n[{timestamp}] 🎯 EXECUTING SANDWICH ATTACK")
        print(f"  Victim TX: {victim_swap['tx_hash'][:20]}...")
        print(f"  Amount: {victim_swap['amount_in']:.2f} {'TOKEN1' if victim_swap['is_token1_to_token2'] else 'TOKEN2'}")
        
        price_before = self.get_pool_price()
        print(f"  Pool price: {price_before:.6f}")
        
        # Calculate attack size
        frontrun_amount = victim_swap['amount_in'] * self.params['frontrun_ratio']
        victim_direction = victim_swap['is_token1_to_token2']
        
        # Front-run (same direction as victim)
        print(f"  🔴 Front-run: {frontrun_amount:.2f} {'TOKEN1' if victim_direction else 'TOKEN2'}")
        frontrun_result = await self.execute_swap(frontrun_amount, victim_direction, high_priority=True)
        
        if not frontrun_result['success']:
            print(f"  ❌ Front-run failed: {frontrun_result.get('error', 'Unknown')}")
            return False
        
        print(f"     ✅ TX: {frontrun_result['tx_hash'][:20]}... (block {frontrun_result['block']})")
        
        # Wait a bit
        await asyncio.sleep(3)
        
        # Back-run (opposite direction)
        backrun_amount = frontrun_amount * 1.01
        print(f"  🔵 Back-run: {backrun_amount:.2f} {'TOKEN2' if victim_direction else 'TOKEN1'}")
        backrun_result = await self.execute_swap(backrun_amount, not victim_direction, high_priority=False)
        
        if not backrun_result['success']:
            print(f"  ❌ Back-run failed: {backrun_result.get('error', 'Unknown')}")
            return False
        
        print(f"     ✅ TX: {backrun_result['tx_hash'][:20]}... (block {backrun_result['block']})")
        
        price_after = self.get_pool_price()
        profit = (price_after - price_before) * frontrun_amount * 0.1
        self.total_profit += profit
        self.attacks_executed += 1
        
        print(f"  💰 Estimated profit: {profit:.4f} tokens")
        print(f"  📊 Total: {self.attacks_executed} attacks, {self.total_profit:.4f} profit")
        
        return True
    
    async def monitor_blocks(self, poll_interval: float = 1.0):
        """Monitor new blocks for victim transactions"""
        print("="*70)
        print("MEV Bot - Block Monitoring Started")
        print("="*70)
        print(f"Strategy: Monitor new blocks, attack immediately")
        print(f"Poll Interval: {poll_interval}s")
        print(f"Min Profit: {self.params['min_profit']} tokens")
        print("="*70)
        print()
        
        self.last_block = self.w3.eth.block_number
        print(f"🔍 Monitoring from block {self.last_block}...")
        print()
        
        while True:
            try:
                current_block = self.w3.eth.block_number
                
                # Check for new blocks
                if current_block > self.last_block:
                    # Process all new blocks
                    for block_num in range(self.last_block + 1, current_block + 1):
                        timestamp = time.strftime("%H:%M:%S")
                        print(f"[{timestamp}] 📦 New block: {block_num}")
                        
                        try:
                            block = self.w3.eth.get_block(block_num, full_transactions=True)
                            
                            for tx in block['transactions']:
                                victim_swap = self.decode_swap_transaction(tx)
                                
                                if victim_swap and self.is_profitable(victim_swap):
                                    print(f"   💡 Profitable swap detected!")
                                    print(f"   Amount: {victim_swap['amount_in']:.2f} tokens")
                                    
                                    # Execute attack immediately
                                    await self.execute_sandwich_attack(victim_swap)
                        
                        except Exception as e:
                            print(f"   ❌ Error processing block {block_num}: {e}")
                    
                    self.last_block = current_block
                
                await asyncio.sleep(poll_interval)
                
            except KeyboardInterrupt:
                print("\n\n⚠️  Bot stopped by user")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                await asyncio.sleep(poll_interval)


async def main():
    parser = argparse.ArgumentParser(description='Run MEV bot with block monitoring')
    parser.add_argument('--mode', choices=['aggressive', 'conservative', 'adaptive'], 
                       default='aggressive')
    parser.add_argument('--poll-interval', type=float, default=1.0)
    parser.add_argument('--rpc', default='https://arc-testnet.stg.blockchain.circle.com')
    parser.add_argument('--private-key', 
                       default='0x488e3ab7dc2033bc970e83bc6daf50ed83c4927e5d8f5bd5ca971df3d062cac2')
    
    args = parser.parse_args()
    
    w3 = Web3(Web3.HTTPProvider(args.rpc))
    
    if not w3.is_connected():
        print("❌ Failed to connect to RPC")
        return
    
    print(f"✅ Connected to Arc Testnet")
    print(f"   Block: {w3.eth.block_number}")
    print()
    
    bot = BlockMonitoringMEVBot(
        w3=w3,
        private_key=args.private_key,
        token1_addr="0x6911406ae5C9fa9314B4AEc086304c001fb3b656",
        token2_addr="0x3eaE1139A9A19517B0dB5696073d957542886BF8",
        swap_router_addr="0xe372f58a9e03c7b56b3ea9a2a08f18767b75ca67",
        pool_addr="0x39A9Ba5F012aB6D6fc90E563C72bD85949Ca0FF6",
        mode=args.mode
    )
    
    await bot.monitor_blocks(poll_interval=args.poll_interval)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted")
        sys.exit(0)

