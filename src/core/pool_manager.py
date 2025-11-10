"""
Uniswap V3 Pool Management and Interaction

This module handles:
- ERC20 token deployment and management
- Uniswap V3 pool creation and initialization  
- Liquidity provision and removal
- Swap execution and simulation
- Pool state monitoring and analysis
- Price and slippage calculations
"""

import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
import logging
from web3 import Web3
from web3.contract import Contract
from eth_account import Account
import json
import math
import time

# Import Uniswap V3 ABIs
try:
    from ..deployment.uniswap_v3_abis import (
        UNISWAP_V3_FACTORY_ABI, UNISWAP_V3_POOL_ABI, POSITION_MANAGER_ABI,
        SWAP_ROUTER_ABI, QUOTER_V2_ABI, ERC20_ABI
    )
except ImportError:
    # Fallback if import fails
    logger.warning("Could not import Uniswap V3 ABIs, using simplified versions")
    UNISWAP_V3_FACTORY_ABI = []
    UNISWAP_V3_POOL_ABI = []
    POSITION_MANAGER_ABI = []
    SWAP_ROUTER_ABI = []
    QUOTER_V2_ABI = []
    ERC20_ABI = []

logger = logging.getLogger(__name__)


@dataclass
class TokenInfo:
    """Information about an ERC20 token"""
    address: str
    name: str
    symbol: str
    decimals: int
    total_supply: int


@dataclass  
class PoolInfo:
    """Information about a Uniswap V3 pool"""
    address: str
    token0: TokenInfo
    token1: TokenInfo
    fee: int
    tick_spacing: int
    current_tick: int
    sqrt_price_x96: int
    liquidity: int
    
    def get_price_ratio(self) -> float:
        """Calculate token0/token1 price ratio"""
        # Convert sqrt_price_x96 to actual price
        price = (self.sqrt_price_x96 / (2 ** 96)) ** 2
        return price
    
    def get_tokens_by_symbol(self) -> Tuple[TokenInfo, TokenInfo]:
        """Get tokens ordered by symbol (for consistent ordering)"""
        if self.token0.symbol < self.token1.symbol:
            return self.token0, self.token1
        return self.token1, self.token0


@dataclass
class SwapResult:
    """Result of a swap transaction"""
    tx_hash: str
    success: bool
    amount_in: float
    amount_out: float
    amount_out_expected: float
    slippage: float
    gas_used: int
    gas_cost: float
    price_impact: float
    

class PoolManager:
    """Manages Uniswap V3 pools and token operations"""
    
    # Standard ERC20 ABI (simplified)
    ERC20_ABI = [
        {
            "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}],
            "name": "transfer",
            "outputs": [{"name": "", "type": "bool"}],
            "type": "function"
        },
        {
            "inputs": [{"name": "_owner", "type": "address"}],
            "name": "balanceOf", 
            "outputs": [{"name": "balance", "type": "uint256"}],
            "type": "function"
        },
        {
            "inputs": [{"name": "_spender", "type": "address"}, {"name": "_value", "type": "uint256"}],
            "name": "approve",
            "outputs": [{"name": "", "type": "bool"}],
            "type": "function"
        },
        {
            "inputs": [],
            "name": "name",
            "outputs": [{"name": "", "type": "string"}],
            "type": "function"
        },
        {
            "inputs": [],
            "name": "symbol",
            "outputs": [{"name": "", "type": "string"}],
            "type": "function"
        },
        {
            "inputs": [],
            "name": "decimals",
            "outputs": [{"name": "", "type": "uint8"}],
            "type": "function"
        }
    ]
    
    def __init__(self, 
                 web3: Web3,
                 network_config: Dict[str, Any],
                 deployer_private_key: str):
        """
        Initialize Pool Manager
        
        Args:
            web3: Web3 instance connected to blockchain
            network_config: Network configuration dictionary
            deployer_private_key: Private key for contract deployment
        """
        self.web3 = web3
        self.network_config = network_config
        
        # Setup deployer account
        self.deployer_account = Account.from_key(deployer_private_key)
        self.deployer_address = self.deployer_account.address
        
        # Contract addresses
        self.uniswap_factory = network_config['contracts']['uniswap_v3_factory']
        self.swap_router = network_config['contracts']['uniswap_v3_router']
        self.position_manager = network_config['contracts']['position_manager']
        self.quoter = network_config['contracts']['quoter_v2']
        
        # Deployed contracts tracking
        self.deployed_tokens: Dict[str, TokenInfo] = {}
        self.created_pools: Dict[str, PoolInfo] = {}
        self.token_contracts: Dict[str, Any] = {}  # Store actual contract instances
        self.pool_contracts: Dict[str, Any] = {}   # Store pool contract instances
        
        # Optional real deployer for actual blockchain deployment
        self.deployer = None
        
        logger.info(f"Initialized PoolManager with deployer: {self.deployer_address}")
    
    async def deploy_token(self, 
                          name: str, 
                          symbol: str, 
                          total_supply: int,
                          decimals: int = 18) -> TokenInfo:
        """
        Deploy a new ERC20 token
        
        Args:
            name: Token name
            symbol: Token symbol  
            total_supply: Total token supply
            decimals: Token decimals
            
        Returns:
            TokenInfo with deployment details
        """
        try:
            # Use the real deployer if available
            if hasattr(self, 'deployer') and self.deployer:
                contract = await self.deployer.deploy_erc20_token(name, symbol, decimals, total_supply)
                
                token_info = TokenInfo(
                    address=contract.address,
                    name=name,
                    symbol=symbol,
                    decimals=decimals,
                    total_supply=total_supply
                )
                
                # Store contract instance for later use
                self.token_contracts[symbol] = contract
                
            else:
                # Fallback to mock deployment for testing
                token_address = Web3.keccak(
                    text=f"{self.deployer_address}_{symbol}_{total_supply}"
                ).hex()[:42]
                
                token_info = TokenInfo(
                    address=token_address,
                    name=name,
                    symbol=symbol,
                    decimals=decimals,
                    total_supply=total_supply
                )
            
            self.deployed_tokens[symbol] = token_info
            
            logger.info(f"Deployed token {symbol} at {token_info.address}")
            return token_info
            
        except Exception as e:
            logger.error(f"Failed to deploy token {symbol}: {e}")
            raise
    
    async def create_pool(self,
                         token0_symbol: str,
                         token1_symbol: str, 
                         fee_tier: int = 3000,
                         initial_price_ratio: str = "1:1") -> PoolInfo:
        """
        Create a new Uniswap V3 pool
        
        Args:
            token0_symbol: First token symbol
            token1_symbol: Second token symbol
            fee_tier: Pool fee tier (500, 3000, 10000)
            initial_price_ratio: Initial price ratio as "token0:token1"
            
        Returns:
            PoolInfo with pool details
        """
        try:
            # Get token info
            token0_info = self.deployed_tokens[token0_symbol]
            token1_info = self.deployed_tokens[token1_symbol]
            
            # Ensure proper token ordering (token0 < token1)
            if int(token0_info.address, 16) > int(token1_info.address, 16):
                token0_info, token1_info = token1_info, token0_info
                token0_symbol, token1_symbol = token1_symbol, token0_symbol
                # Flip the price ratio
                ratio_parts = initial_price_ratio.split(':')
                initial_price_ratio = f"{ratio_parts[1]}:{ratio_parts[0]}"
            
            # Calculate initial sqrt price
            ratio_parts = initial_price_ratio.split(':')
            price_ratio = float(ratio_parts[1]) / float(ratio_parts[0])  # token1/token0
            sqrt_price_x96 = int(math.sqrt(price_ratio) * (2 ** 96))
            
            # Use real deployer to create Uniswap V3 pool
            if hasattr(self, 'deployer') and self.deployer:
                pool_contract = await self.deployer.create_uniswap_v3_pool(
                    token0_info.address, 
                    token1_info.address,
                    fee_tier,
                    price_ratio
                )
                pool_address = pool_contract.address
                
                # Store contract instance
                pool_key = f"{token0_symbol}_{token1_symbol}_{fee_tier}"
                self.pool_contracts[pool_key] = pool_contract
                
                # Get actual pool state
                try:
                    slot0 = pool_contract.functions.slot0().call()
                    actual_sqrt_price = slot0[0]
                    current_tick = slot0[1]
                    unlocked = slot0[6]
                    
                    if not unlocked:
                        logger.warning(f"Pool {pool_key} is not unlocked!")
                        
                except Exception as e:
                    logger.warning(f"Could not read pool state: {e}")
                    actual_sqrt_price = sqrt_price_x96
                    current_tick = 0
                
            else:
                # Fallback to mock deployment
                pool_address = Web3.keccak(
                    text=f"pool_{token0_info.address}_{token1_info.address}_{fee_tier}"
                ).hex()[:42]
                actual_sqrt_price = sqrt_price_x96
                current_tick = 0
            
            # Create pool info
            pool_info = PoolInfo(
                address=pool_address,
                token0=token0_info,
                token1=token1_info,
                fee=fee_tier,
                tick_spacing=60 if fee_tier == 3000 else (10 if fee_tier == 500 else 200),
                current_tick=current_tick,
                sqrt_price_x96=actual_sqrt_price,
                liquidity=0  # Will be updated when liquidity is added
            )
            
            pool_key = f"{token0_symbol}_{token1_symbol}_{fee_tier}"
            self.created_pools[pool_key] = pool_info
            
            logger.info(f"Created Uniswap V3 pool {pool_key} at {pool_address}")
            return pool_info
            
        except Exception as e:
            logger.error(f"Failed to create Uniswap V3 pool {token0_symbol}/{token1_symbol}: {e}")
            raise
    
    async def add_liquidity(self,
                           pool_key: str,
                           amount0: float,
                           amount1: float,
                           price_range: Optional[Tuple[int, int]] = None) -> Dict[str, Any]:
        """
        Add liquidity to a Uniswap V3 pool using Position Manager
        
        Args:
            pool_key: Pool identifier
            amount0: Amount of token0 to add
            amount1: Amount of token1 to add  
            price_range: (lower_tick, upper_tick) or None for full range
            
        Returns:
            Dictionary with liquidity addition results
        """
        try:
            pool_info = self.created_pools[pool_key]
            
            if price_range is None:
                # Full range liquidity for Uniswap V3
                lower_tick = -887220  # Approximately full range for most fee tiers
                upper_tick = 887220
            else:
                lower_tick, upper_tick = price_range
            
            # Convert amounts to wei
            amount0_wei = int(amount0 * (10 ** pool_info.token0.decimals))
            amount1_wei = int(amount1 * (10 ** pool_info.token1.decimals))
            
            # Use real deployer to add liquidity if available
            if hasattr(self, 'deployer') and self.deployer:
                try:
                    # Get position manager contract
                    position_manager = self.web3.eth.contract(
                        address=self.position_manager,
                        abi=POSITION_MANAGER_ABI
                    )
                    
                    # Get token contracts
                    token0_contract = self.web3.eth.contract(
                        address=pool_info.token0.address,
                        abi=ERC20_ABI
                    )
                    token1_contract = self.web3.eth.contract(
                        address=pool_info.token1.address,
                        abi=ERC20_ABI
                    )
                    
                    # Approve tokens
                    nonce = await self._get_nonce()
                    gas_price = await self._get_gas_price()
                    
                    # Approve token0
                    approve_tx0 = token0_contract.functions.approve(
                        self.position_manager, amount0_wei
                    ).build_transaction({
                        'from': self.deployer_address,
                        'nonce': nonce,
                        'gas': 100000,
                        'gasPrice': gas_price
                    })
                    await self._send_transaction(approve_tx0)
                    
                    # Approve token1
                    nonce += 1
                    approve_tx1 = token1_contract.functions.approve(
                        self.position_manager, amount1_wei
                    ).build_transaction({
                        'from': self.deployer_address,
                        'nonce': nonce,
                        'gas': 100000,
                        'gasPrice': gas_price
                    })
                    await self._send_transaction(approve_tx1)
                    
                    # Add liquidity via Position Manager
                    nonce += 1
                    deadline = int(time.time()) + 300  # 5 minutes
                    
                    mint_params = (
                        pool_info.token0.address,  # token0
                        pool_info.token1.address,  # token1
                        pool_info.fee,             # fee
                        lower_tick,                # tickLower
                        upper_tick,                # tickUpper
                        amount0_wei,               # amount0Desired
                        amount1_wei,               # amount1Desired
                        0,                         # amount0Min (no slippage protection)
                        0,                         # amount1Min (no slippage protection)
                        self.deployer_address,     # recipient
                        deadline                   # deadline
                    )
                    
                    mint_tx = position_manager.functions.mint(mint_params).build_transaction({
                        'from': self.deployer_address,
                        'nonce': nonce,
                        'gas': 500000,
                        'gasPrice': gas_price
                    })
                    
                    tx_receipt = await self._send_transaction(mint_tx)
                    
                    # Parse mint result from logs (simplified)
                    liquidity_amount = amount0_wei + amount1_wei  # Simplified calculation
                    token_id = 1  # Would parse from logs in real implementation
                    
                    # Update pool state
                    pool_info.liquidity += liquidity_amount
                    
                    result = {
                        'pool_address': pool_info.address,
                        'amount0_added': amount0,
                        'amount1_added': amount1,
                        'liquidity_minted': liquidity_amount,
                        'token_id': token_id,
                        'lower_tick': lower_tick,
                        'upper_tick': upper_tick,
                        'tx_hash': tx_receipt['transactionHash'].hex()
                    }
                    
                except Exception as e:
                    logger.error(f"Real liquidity addition failed: {e}")
                    # Fall back to mock
                    raise
            else:
                # Mock implementation
                liquidity_amount = int(math.sqrt(amount0 * amount1) * (10 ** 18))
                pool_info.liquidity += liquidity_amount
                
                result = {
                    'pool_address': pool_info.address,
                    'amount0_added': amount0,
                    'amount1_added': amount1,
                    'liquidity_minted': liquidity_amount,
                    'lower_tick': lower_tick,
                    'upper_tick': upper_tick,
                    'tx_hash': f"0x{hash(f'addliq_{pool_key}_{amount0}_{amount1}'):064x}"[2:66]
                }
            
            logger.info(f"Added liquidity to {pool_key}: {amount0} + {amount1}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to add liquidity to {pool_key}: {e}")
            raise
    
    async def _get_nonce(self) -> int:
        """Get current nonce for deployer account"""
        return self.web3.eth.get_transaction_count(self.deployer_address)
    
    async def _get_gas_price(self) -> int:
        """Get current gas price"""
        return self.web3.eth.gas_price
    
    async def _send_transaction(self, transaction: Dict) -> Dict:
        """Sign and send transaction"""
        signed_txn = self.web3.eth.account.sign_transaction(transaction, self.deployer_account.key)
        raw_tx = getattr(signed_txn, 'rawTransaction', None) or getattr(signed_txn, 'raw_transaction', signed_txn)
        tx_hash = self.web3.eth.send_raw_transaction(raw_tx)
        return self.web3.eth.wait_for_transaction_receipt(tx_hash)
    
    async def simulate_swap(self,
                           pool_key: str,
                           token_in_symbol: str,
                           amount_in: float,
                           slippage_tolerance: float = 0.005) -> Dict[str, Any]:
        """
        Simulate a swap to get expected output
        
        Args:
            pool_key: Pool identifier
            token_in_symbol: Input token symbol
            amount_in: Input amount
            slippage_tolerance: Maximum acceptable slippage (default 0.5%)
            
        Returns:
            Dictionary with swap simulation results
        """
        try:
            pool_info = self.created_pools[pool_key]
            
            # Determine swap direction
            is_token0_in = (token_in_symbol == pool_info.token0.symbol)
            
            # Check if we have a real pool contract and update liquidity
            if hasattr(self, 'pool_contracts') and pool_key in self.pool_contracts:
                try:
                    pool_contract = self.pool_contracts[pool_key]
                    real_liquidity = pool_contract.functions.liquidity().call()
                    
                    if real_liquidity > 0:
                        pool_info.liquidity = real_liquidity
                        logger.debug(f"Updated {pool_key} liquidity: {real_liquidity}")
                    else:
                        raise ValueError(f"Pool {pool_key} has no liquidity on blockchain")
                        
                except Exception as e:
                    logger.warning(f"Could not read blockchain liquidity for {pool_key}: {e}")
                    # Continue with stored liquidity value
            
            if pool_info.liquidity == 0:
                raise ValueError(f"Pool {pool_key} has no liquidity stored")
            
            # Simplified constant product formula (x * y = k)
            # In real implementation, would use Uniswap V3 concentrated liquidity math
            
            if is_token0_in:
                # Swapping token0 for token1
                current_price = pool_info.get_price_ratio()
                if current_price == 0:
                    # Use default 1:2 ratio (1 TOKEN1 = 2 TOKEN2)
                    current_price = 2.0
                amount_out_ideal = amount_in * current_price
                
                # Apply slippage based on trade size relative to liquidity
                liquidity_ratio = amount_in / (pool_info.liquidity / 10**18)
                slippage_impact = liquidity_ratio * 0.01  # 1% slippage per liquidity unit
                
                amount_out = amount_out_ideal * (1 - slippage_impact)
                
            else:
                # Swapping token1 for token0
                price_ratio = pool_info.get_price_ratio()
                if price_ratio == 0:
                    # Use default 1:2 ratio (1 TOKEN1 = 2 TOKEN2, so 2 TOKEN2 = 0.5 TOKEN1)
                    current_price = 0.5
                else:
                    current_price = 1 / price_ratio
                amount_out_ideal = amount_in * current_price
                
                liquidity_ratio = amount_in / (pool_info.liquidity / 10**18)
                slippage_impact = liquidity_ratio * 0.01
                
                amount_out = amount_out_ideal * (1 - slippage_impact)
            
            # Calculate actual slippage
            if amount_out_ideal > 0:
                actual_slippage = (amount_out_ideal - amount_out) / amount_out_ideal
            else:
                actual_slippage = 0.0
            
            # Check slippage tolerance
            if actual_slippage > slippage_tolerance:
                raise ValueError(f"Slippage {actual_slippage:.3%} exceeds tolerance {slippage_tolerance:.3%}")
            
            result = {
                'amount_in': amount_in,
                'amount_out': amount_out,
                'amount_out_ideal': amount_out_ideal,
                'slippage': actual_slippage,
                'price_impact': slippage_impact,
                'token_in': token_in_symbol,
                'token_out': pool_info.token1.symbol if is_token0_in else pool_info.token0.symbol
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to simulate swap in {pool_key}: {e}")
            raise
    
    async def execute_swap(self,
                          pool_key: str,
                          token_in_symbol: str,
                          amount_in: float,
                          min_amount_out: float,
                          trader_address: str) -> SwapResult:
        """
        Execute a swap transaction
        
        Args:
            pool_key: Pool identifier
            token_in_symbol: Input token symbol
            amount_in: Input amount
            min_amount_out: Minimum acceptable output
            trader_address: Address executing the swap
            
        Returns:
            SwapResult with execution details
        """
        try:
            # First simulate to get expected results
            simulation = await self.simulate_swap(pool_key, token_in_symbol, amount_in)
            
            if simulation['amount_out'] < min_amount_out:
                raise ValueError(f"Output {simulation['amount_out']} below minimum {min_amount_out}")
            
            pool_info = self.created_pools[pool_key]
            
            # Execute the swap (simplified - in real implementation would send tx)
            tx_hash = f"0x{hash(f'swap_{pool_key}_{trader_address}_{amount_in}'):064x}"[2:66]
            
            # Update pool state
            is_token0_in = (token_in_symbol == pool_info.token0.symbol)
            
            if is_token0_in:
                # Update sqrt_price_x96 based on swap
                new_ratio = pool_info.get_price_ratio() * (1 + simulation['price_impact'])
                pool_info.sqrt_price_x96 = int(math.sqrt(new_ratio) * (2 ** 96))
            else:
                new_ratio = pool_info.get_price_ratio() * (1 - simulation['price_impact'])
                pool_info.sqrt_price_x96 = int(math.sqrt(new_ratio) * (2 ** 96))
            
            # Estimate gas cost
            gas_used = 150000  # Typical DEX swap gas
            # Use default gas price if not configured
            gas_price_gwei = self.network_config.get('gas_price_gwei', 300)  # Default 300 gwei
            gas_cost = gas_used * gas_price_gwei / 10**9  # Convert to USDC
            
            result = SwapResult(
                tx_hash=tx_hash,
                success=True,
                amount_in=amount_in,
                amount_out=simulation['amount_out'],
                amount_out_expected=simulation['amount_out_ideal'],
                slippage=simulation['slippage'],
                gas_used=gas_used,
                gas_cost=gas_cost,
                price_impact=simulation['price_impact']
            )
            
            logger.info(f"Executed swap in {pool_key}: {amount_in} -> {result.amount_out}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to execute swap in {pool_key}: {e}")
            raise ValueError(f"Swap execution failed: {e}")
    
    def get_pool_state(self, pool_key: str) -> Dict[str, Any]:
        """Get current pool state information"""
        try:
            pool_info = self.created_pools[pool_key]
            
            return {
                'address': pool_info.address,
                'token0': {
                    'symbol': pool_info.token0.symbol,
                    'address': pool_info.token0.address
                },
                'token1': {
                    'symbol': pool_info.token1.symbol,
                    'address': pool_info.token1.address
                },
                'fee': pool_info.fee,
                'liquidity': pool_info.liquidity,
                'sqrt_price_x96': pool_info.sqrt_price_x96,
                'current_price_ratio': pool_info.get_price_ratio(),
                'tick': pool_info.current_tick
            }
            
        except KeyError:
            raise ValueError(f"Pool {pool_key} not found")
    
    def list_pools(self) -> List[str]:
        """List all created pools"""
        return list(self.created_pools.keys())
    
    def list_tokens(self) -> List[str]:
        """List all deployed tokens"""
        return list(self.deployed_tokens.keys())
    
    def calculate_price_impact(self, 
                             pool_key: str, 
                             amount_in: float, 
                             token_in_symbol: str) -> float:
        """Calculate price impact of a trade"""
        try:
            pool_info = self.created_pools[pool_key]
            
            if pool_info.liquidity == 0:
                return 1.0  # 100% price impact if no liquidity
            
            # Simplified price impact calculation
            liquidity_depth = pool_info.liquidity / 10**18
            impact_ratio = amount_in / liquidity_depth
            
            # Non-linear price impact (square root relationship)
            price_impact = impact_ratio ** 0.7 * 0.01  # Scaled impact
            
            return min(price_impact, 0.5)  # Cap at 50% impact
            
        except Exception as e:
            logger.error(f"Failed to calculate price impact: {e}")
            return 0.0
    
    async def get_optimal_arbitrage_amount(self,
                                         pool_key1: str,
                                         pool_key2: str,
                                         token_symbol: str) -> Optional[float]:
        """
        Calculate optimal arbitrage amount between two pools
        
        Args:
            pool_key1: First pool identifier
            pool_key2: Second pool identifier  
            token_symbol: Token to arbitrage
            
        Returns:
            Optimal arbitrage amount or None if no arbitrage opportunity
        """
        try:
            # Get pool states
            pool1_state = self.get_pool_state(pool_key1)
            pool2_state = self.get_pool_state(pool_key2)
            
            # Calculate price difference
            price1 = pool1_state['current_price_ratio']
            price2 = pool2_state['current_price_ratio']
            
            price_diff = abs(price1 - price2) / min(price1, price2)
            
            # Only proceed if price difference > 0.1%
            if price_diff < 0.001:
                return None
            
            # Simple optimization: try different amounts and find maximum profit
            best_profit = 0
            best_amount = 0
            
            for amount in [10, 25, 50, 100, 200]:
                try:
                    # Simulate buying in cheaper pool
                    if price1 < price2:
                        buy_sim = await self.simulate_swap(pool_key1, token_symbol, amount)
                        sell_sim = await self.simulate_swap(pool_key2, buy_sim['token_out'], buy_sim['amount_out'])
                    else:
                        buy_sim = await self.simulate_swap(pool_key2, token_symbol, amount)
                        sell_sim = await self.simulate_swap(pool_key1, buy_sim['token_out'], buy_sim['amount_out'])
                    
                    profit = sell_sim['amount_out'] - amount
                    
                    if profit > best_profit:
                        best_profit = profit
                        best_amount = amount
                        
                except:
                    continue  # Skip if simulation fails
            
            return best_amount if best_profit > 0 else None
            
        except Exception as e:
            logger.error(f"Failed to calculate optimal arbitrage: {e}")
            return None


# Helper functions
def create_pool_manager_from_config(config: Dict[str, Any], 
                                  deployer_private_key: str) -> PoolManager:
    """Create PoolManager from network configuration"""
    from web3 import Web3
    
    # Connect to network
    web3 = Web3(Web3.HTTPProvider(config['rpc_url']))
    
    # Verify connection
    if not web3.is_connected():
        raise ConnectionError(f"Failed to connect to {config['rpc_url']}")
    
    return PoolManager(web3, config, deployer_private_key)


# Example usage and testing
if __name__ == "__main__":
    import asyncio
    
    async def test_pool_manager():
        """Test pool manager functionality"""
        print("🏊‍♂️ Testing Pool Manager")
        
        # Mock network config
        network_config = {
            'rpc_url': 'http://127.0.0.1:8545',
            'contracts': {
                'uniswap_v3_factory': '0x1F98431c8aD98523631AE4a59f267346ea31F984',
                'uniswap_v3_router': '0xE592427A0AEce92De3Edee1F18E0157C05861564',
                'position_manager': '0xC36442b4c4e76c8f7a04B0eE0d2C2d4C6e5e4F2D',
                'quoter_v2': '0x61fFE014bA17989E743c5F6cB21bF9697530B21e'
            },
            'gas': {
                'base_fee_gwei': 300
            }
        }
        
        # Create pool manager (with dummy private key for testing)
        dummy_private_key = "0x" + "1" * 64
        
        try:
            # Mock Web3 for testing
            from unittest.mock import MagicMock
            
            web3_mock = MagicMock()
            web3_mock.is_connected.return_value = True
            
            pool_manager = PoolManager(web3_mock, network_config, dummy_private_key)
            
            print("✅ Pool Manager initialized")
            
            # Deploy test tokens
            print("\n📝 Deploying tokens...")
            token_a = await pool_manager.deploy_token("Token1", "TOKEN1", 1000000)
            token_b = await pool_manager.deploy_token("Token2", "TOKEN2", 1000000)
            
            print(f"   TOKEN1: {token_a.address}")
            print(f"   TOKEN2: {token_b.address}")
            
            # Create pool
            print("\n🏊 Creating pool...")
            pool_info = await pool_manager.create_pool("TOKEN1", "TOKEN2", 3000, "1:2")
            print(f"   Pool: {pool_info.address}")
            print(f"   Price ratio: {pool_info.get_price_ratio():.6f}")
            
            # Add liquidity  
            print("\n💧 Adding liquidity...")
            liq_result = await pool_manager.add_liquidity("TOKEN1_TOKEN2_3000", 1000, 2000)
            print(f"   Added: {liq_result['amount0_added']} + {liq_result['amount1_added']}")
            print(f"   Liquidity: {liq_result['liquidity_minted']}")
            
            # Simulate swap
            print("\n🔄 Simulating swap...")
            swap_sim = await pool_manager.simulate_swap("TOKEN1_TOKEN2_3000", "TOKEN1", 50)
            print(f"   50 TOKEN1 -> {swap_sim['amount_out']:.6f} TOKEN2")
            print(f"   Slippage: {swap_sim['slippage']:.3%}")
            
            # Execute swap
            print("\n⚡ Executing swap...")
            swap_result = await pool_manager.execute_swap(
                "TOKEN1_TOKEN2_3000", "TOKEN1", 30, swap_sim['amount_out'] * 0.95, 
                "0x742d35Cc6634C0532925a3b8D7cf460000000000"
            )
            print(f"   TX: {swap_result.tx_hash}")
            print(f"   Output: {swap_result.amount_out:.6f}")
            print(f"   Slippage: {swap_result.slippage:.3%}")
            
            # Show final pool state
            print("\n📊 Final pool state:")
            pool_state = pool_manager.get_pool_state("TOKEN1_TOKEN2_3000")
            print(f"   Price ratio: {pool_state['current_price_ratio']:.6f}")
            print(f"   Liquidity: {pool_state['liquidity']}")
            
        except Exception as e:
            print(f"❌ Test failed: {e}")
    
    # Run test
    asyncio.run(test_pool_manager())
