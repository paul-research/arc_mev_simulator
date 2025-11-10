"""
Victim Trader Simulation for MEV Research

This module simulates realistic victim trading behavior that MEV bots can exploit:
- Natural trading patterns (DCA, arbitrage, large swaps)
- Realistic slippage tolerance and timing
- Multiple victim personas (retail, whale, bot, etc.)
- Configurable trading frequencies and amounts
- Integration with pool manager for actual trade execution
"""

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
import logging
import math

logger = logging.getLogger(__name__)


class VictimType(Enum):
    """Types of victim traders"""
    RETAIL = "retail"              # Small, infrequent trades
    WHALE = "whale"               # Large, market-moving trades  
    DCA_BOT = "dca_bot"           # Dollar-cost averaging bot
    ARBITRAGE_BOT = "arbitrage_bot"     # Cross-DEX arbitrage bot
    LIQUIDITY_PROVIDER = "lp"     # Liquidity provider
    PANIC_SELLER = "panic_seller"  # Emotional, high-slippage trades
    PANIC = "panic"               # Emotional, high-slippage trades (alternative)


@dataclass
class TradingPattern:
    """Trading pattern configuration"""
    name: str
    frequency_seconds: float      # Average time between trades
    amount_range: tuple          # (min, max) trade amounts
    slippage_tolerance: float    # Maximum acceptable slippage
    gas_sensitivity: float       # How much gas cost affects trading (0-1)
    patience_level: float        # Willingness to wait for better prices (0-1)
    token_preference: List[str]  # Preferred tokens to trade
    

@dataclass
class VictimTrade:
    """Represents a victim trade transaction"""
    trade_id: str
    victim_id: str
    victim_type: VictimType
    pool_key: str
    token_in_symbol: str
    token_out_symbol: str
    amount_in: float
    expected_amount_out: float
    max_slippage: float
    gas_price_gwei: float
    timestamp: float
    executed: bool = False
    tx_hash: Optional[str] = None
    actual_amount_out: Optional[float] = None
    actual_slippage: Optional[float] = None
    mev_attacked: bool = False
    

class VictimTrader:
    """Simulates a single victim trader with specific behavior patterns"""
    
    # Predefined trading patterns for different victim types
    TRADING_PATTERNS = {
        VictimType.RETAIL: TradingPattern(
            name="Retail Trader",
            frequency_seconds=300.0,  # 5 minutes average
            amount_range=(5, 50),     # Small trades
            slippage_tolerance=0.02,  # 2% tolerance
            gas_sensitivity=0.8,      # Very sensitive to gas
            patience_level=0.3,       # Impatient
            token_preference=["TOKEN1", "TOKEN2"]
        ),
        
        VictimType.WHALE: TradingPattern(
            name="Whale Trader", 
            frequency_seconds=1800.0,  # 30 minutes average
            amount_range=(200, 1000),  # Large trades
            slippage_tolerance=0.012,  # 1.2% tolerance (increased for realistic trading)
            gas_sensitivity=0.1,       # Not sensitive to gas
            patience_level=0.8,        # Very patient
            token_preference=["TOKEN1", "TOKEN2"]
        ),
        
        VictimType.DCA_BOT: TradingPattern(
            name="DCA Bot",
            frequency_seconds=60.0,    # 1 minute (regular intervals)
            amount_range=(20, 30),     # Consistent amounts
            slippage_tolerance=0.015,  # 1.5% tolerance (increased for realistic trading)
            gas_sensitivity=0.5,       # Moderate gas sensitivity
            patience_level=0.9,        # Very patient, waits for good prices
            token_preference=["TOKEN1"]
        ),
        
        VictimType.ARBITRAGE_BOT: TradingPattern(
            name="Arbitrage Bot",
            frequency_seconds=15.0,     # 15 seconds (fast)
            amount_range=(50, 200),     # Medium to large
            slippage_tolerance=0.008,   # 0.8% tolerance (increased for realistic trading)
            gas_sensitivity=0.6,        # Gas cost affects profitability
            patience_level=0.2,         # Very impatient, needs quick execution
            token_preference=["TOKEN1", "TOKEN2"]
        ),
        
        VictimType.PANIC_SELLER: TradingPattern(
            name="Panic Seller",
            frequency_seconds=600.0,    # 10 minutes (sporadic)
            amount_range=(100, 500),    # Large emotional trades
            slippage_tolerance=0.05,    # 5% tolerance (high)
            gas_sensitivity=0.2,        # Don't care about gas when panicking
            patience_level=0.1,         # No patience, market sell
            token_preference=["TOKEN1", "TOKEN2"]
        )
    }
    
    def __init__(self,
                 victim_id: str,
                 victim_type: VictimType,
                 wallet_address: str,
                 wallet_private_key: str,
                 initial_balances: Dict[str, float],
                 custom_pattern: Optional[TradingPattern] = None):
        """
        Initialize victim trader
        
        Args:
            victim_id: Unique identifier
            victim_type: Type of victim trader
            wallet_address: Wallet address
            wallet_private_key: Private key for signing transactions
            initial_balances: Initial token balances
            custom_pattern: Custom trading pattern override
        """
        self.victim_id = victim_id
        self.victim_type = victim_type
        self.wallet_address = wallet_address
        self.wallet_private_key = wallet_private_key
        self.initial_balances = initial_balances  # Store for reference
        self.balances = initial_balances.copy()
        
        # Use custom pattern or default for type
        self.pattern = custom_pattern or self.TRADING_PATTERNS[victim_type]
        
        # Trading state
        self.trade_history: List[VictimTrade] = []
        self.active_trades: Dict[str, VictimTrade] = {}
        self.last_trade_time = 0.0
        self.total_volume_traded = 0.0
        self.total_mev_loss = 0.0
        
        # Behavioral state (changes over time)
        self.current_patience = self.pattern.patience_level
        self.current_gas_sensitivity = self.pattern.gas_sensitivity
        self.stress_level = 0.0  # Increases with losses, affects behavior
        
        logger.info(f"Initialized victim trader {victim_id} ({victim_type.value})")
    
    def _calculate_next_trade_interval(self) -> float:
        """Calculate interval until next trade (in seconds)"""
        base_frequency = self.pattern.frequency_seconds
        
        # For quick testing, use shorter intervals
        base_frequency = min(base_frequency, 30.0)  # Max 30 seconds for testing
        
        # Add randomness (exponential distribution for realistic intervals) 
        randomness_factor = random.expovariate(1.0 / base_frequency)
        
        # Adjust based on stress level (stressed traders trade more frequently)
        stress_multiplier = 1.0 - (self.stress_level * 0.5)
        
        next_interval = randomness_factor * stress_multiplier
        return max(1.0, next_interval)  # Minimum 1 second interval for testing
    
    def _select_trade_tokens(self, available_pools: List[str]) -> Optional[tuple]:
        """Select tokens for next trade based on preferences and available pools"""
        # Filter pools based on token preferences
        preferred_pools = []
        
        for pool_key in available_pools:
            tokens = pool_key.split('_')[:2]  # Assume format: TOKEN0_TOKEN1_FEE
            
            if any(token in self.pattern.token_preference for token in tokens):
                preferred_pools.append((pool_key, tokens))
        
        if not preferred_pools:
            return None
        
        # Select random pool from preferences
        pool_key, tokens = random.choice(preferred_pools)
        
        # Decide direction based on current balances
        token0, token1 = tokens
        
        balance0 = self.balances.get(token0, 0)
        balance1 = self.balances.get(token1, 0)
        
        # Prefer trading from token with higher balance
        if balance0 > balance1 and balance0 > 0:
            return pool_key, token0, token1
        elif balance1 > 0:
            return pool_key, token1, token0
        elif balance0 > 0:
            return pool_key, token0, token1
        
        return None
    
    def _calculate_trade_amount(self, token_in_symbol: str) -> float:
        """Calculate trade amount based on pattern and current balance"""
        available_balance = self.balances.get(token_in_symbol, 0)
        
        # Get pattern amount range
        min_amount, max_amount = self.pattern.amount_range
        
        # Adjust for available balance
        max_affordable = available_balance * 0.8  # Keep 20% buffer
        effective_max = min(max_amount, max_affordable)
        effective_min = min(min_amount, effective_max)
        
        if effective_min <= 0:
            return 0
        
        # Different amount selection strategies by victim type
        if self.victim_type == VictimType.DCA_BOT:
            # DCA bots use consistent amounts
            return (effective_min + effective_max) / 2
            
        elif self.victim_type == VictimType.WHALE:
            # Whales prefer larger amounts, biased toward max
            return random.uniform(effective_max * 0.7, effective_max)
            
        elif self.victim_type == VictimType.PANIC_SELLER:
            # Panic sellers often trade large portions
            panic_amount = available_balance * random.uniform(0.3, 0.7)
            return min(panic_amount, effective_max)
            
        else:
            # Default: uniform distribution
            return random.uniform(effective_min, effective_max)
    
    def _adjust_slippage_tolerance(self) -> float:
        """Adjust slippage tolerance based on current state"""
        base_tolerance = self.pattern.slippage_tolerance
        
        # Increase tolerance when stressed (desperate to trade)
        stress_adjustment = self.stress_level * 0.02  # Up to 2% extra
        
        # Decrease patience over time (become more willing to accept slippage)
        patience_adjustment = (1 - self.current_patience) * 0.01
        
        return base_tolerance + stress_adjustment + patience_adjustment
    
    async def generate_trade(self, available_pools: List[str], current_time: float) -> Optional[VictimTrade]:
        """
        Generate a victim trade if conditions are met
        
        Args:
            available_pools: List of available pool keys
            current_time: Current timestamp
            
        Returns:
            VictimTrade if trade should be generated, None otherwise
        """
        # Check if it's time for next trade
        next_trade_interval = self._calculate_next_trade_interval()
        if current_time < self.last_trade_time + next_trade_interval:
            logger.debug(f"[{self.victim_id}] Not time yet: {current_time} < {self.last_trade_time + next_trade_interval}")
            return None
        
        # Select tokens for trade
        logger.debug(f"[{self.victim_id}] Available pools: {available_pools}")
        logger.debug(f"[{self.victim_id}] Current balances: {self.balances}")
        
        trade_selection = self._select_trade_tokens(available_pools)
        if not trade_selection:
            logger.debug(f"[{self.victim_id}] No trade selection available")
            return None
        
        pool_key, token_in, token_out = trade_selection
        
        # Calculate trade amount
        amount_in = self._calculate_trade_amount(token_in)
        logger.debug(f"[{self.victim_id}] Trade amount calculated: {amount_in} {token_in}")
        if amount_in <= 0:
            logger.debug(f"[{self.victim_id}] Trade amount too low: {amount_in}")
            return None
        
        # Adjust slippage tolerance
        max_slippage = self._adjust_slippage_tolerance()
        
        # Create trade
        trade_id = f"{self.victim_id}_{int(current_time * 1000)}"
        
        trade = VictimTrade(
            trade_id=trade_id,
            victim_id=self.victim_id,
            victim_type=self.victim_type,
            pool_key=pool_key,
            token_in_symbol=token_in,
            token_out_symbol=token_out,
            amount_in=amount_in,
            expected_amount_out=0,  # Will be calculated by pool manager
            max_slippage=max_slippage,
            gas_price_gwei=300,  # Default for Arc testnet
            timestamp=current_time
        )
        
        self.active_trades[trade_id] = trade
        self.last_trade_time = current_time
        
        logger.debug(f"[{self.victim_id}] Generated trade: {amount_in} {token_in} -> {token_out}")
        return trade
    
    async def execute_trade(self, trade: VictimTrade, pool_manager) -> bool:
        """
        Execute a victim trade through pool manager
        
        Args:
            trade: VictimTrade to execute
            pool_manager: PoolManager instance
            
        Returns:
            True if trade executed successfully
        """
        try:
            # First simulate to get expected output
            simulation = await pool_manager.simulate_swap(
                trade.pool_key,
                trade.token_in_symbol, 
                trade.amount_in,
                trade.max_slippage
            )
            
            trade.expected_amount_out = simulation['amount_out']
            
            # Check if slippage is acceptable
            if simulation['slippage'] > trade.max_slippage:
                logger.warning(f"[{self.victim_id}] Trade {trade.trade_id} rejected: slippage too high")
                return False
            
            # Execute the swap
            swap_result = await pool_manager.execute_swap(
                trade.pool_key,
                trade.token_in_symbol,
                trade.amount_in,
                simulation['amount_out'] * 0.99,  # 1% buffer
                self.wallet_address,
                self.wallet_private_key
            )
            
            # Update trade with results
            trade.executed = True
            trade.tx_hash = swap_result.tx_hash
            trade.actual_amount_out = swap_result.amount_out
            trade.actual_slippage = swap_result.slippage
            
            # Update balances
            self.balances[trade.token_in_symbol] -= trade.amount_in
            self.balances[trade.token_out_symbol] = self.balances.get(trade.token_out_symbol, 0) + swap_result.amount_out
            
            # Update statistics
            self.total_volume_traded += trade.amount_in
            self.trade_history.append(trade)
            
            # Remove from active trades
            if trade.trade_id in self.active_trades:
                del self.active_trades[trade.trade_id]
            
            logger.info(f"[{self.victim_id}] Executed trade {trade.trade_id}: {swap_result.amount_out:.6f} {trade.token_out_symbol}")
            return True
            
        except Exception as e:
            logger.error(f"[{self.victim_id}] Failed to execute trade {trade.trade_id}: {e}")
            
            # Update trade as failed
            trade.executed = False
            
            # Update stress level due to failed trade
            self.stress_level = min(1.0, self.stress_level + 0.1)
            
            return False
    
    def record_mev_attack(self, trade_id: str, mev_loss: float):
        """Record that a trade was MEV attacked"""
        for trade in self.trade_history:
            if trade.trade_id == trade_id:
                trade.mev_attacked = True
                self.total_mev_loss += mev_loss
                
                # Increase stress due to MEV attack
                self.stress_level = min(1.0, self.stress_level + 0.05)
                
                logger.warning(f"[{self.victim_id}] Trade {trade_id} was MEV attacked: {mev_loss:.6f} loss")
                break
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive victim trading statistics"""
        if not self.trade_history:
            return {
                'total_trades': 0,
                'total_volume': 0,
                'avg_trade_size': 0,
                'mev_attack_rate': 0,
                'total_mev_loss': 0,
                'current_balances': self.balances
            }
        
        successful_trades = [t for t in self.trade_history if t.executed]
        mev_attacked_trades = [t for t in self.trade_history if t.mev_attacked]
        
        total_slippage = sum(t.actual_slippage or 0 for t in successful_trades)
        avg_slippage = total_slippage / len(successful_trades) if successful_trades else 0
        
        return {
            'victim_id': self.victim_id,
            'victim_type': self.victim_type.value,
            'total_trades': len(self.trade_history),
            'successful_trades': len(successful_trades),
            'success_rate': len(successful_trades) / len(self.trade_history) if self.trade_history else 0,
            'total_volume': self.total_volume_traded,
            'avg_trade_size': self.total_volume_traded / len(self.trade_history) if self.trade_history else 0,
            'mev_attack_count': len(mev_attacked_trades),
            'mev_attack_rate': len(mev_attacked_trades) / len(self.trade_history) if self.trade_history else 0,
            'total_mev_loss': self.total_mev_loss,
            'avg_mev_loss_per_attack': self.total_mev_loss / len(mev_attacked_trades) if mev_attacked_trades else 0,
            'avg_slippage': avg_slippage,
            'current_stress_level': self.stress_level,
            'current_balances': self.balances.copy()
        }
    
    def __str__(self) -> str:
        """String representation"""
        return (f"VictimTrader(id='{self.victim_id}', type='{self.victim_type.value}', "
                f"trades={len(self.trade_history)}, volume={self.total_volume_traded:.1f})")


class VictimTraderManager:
    """Manages multiple victim traders for simulation"""
    
    def __init__(self):
        self.traders: Dict[str, VictimTrader] = {}
        self.pending_trades: List[VictimTrade] = []
        
    def add_trader(self, 
                   victim_id: str,
                   victim_type: VictimType, 
                   initial_balances: Dict[str, float],
                   custom_pattern: Optional[TradingPattern] = None) -> VictimTrader:
        """Add a new victim trader"""
        # Generate wallet address
        wallet_address = f"0x{hash(victim_id):040x}"[2:42]
        
        trader = VictimTrader(
            victim_id=victim_id,
            victim_type=victim_type,
            wallet_address=wallet_address,
            initial_balances=initial_balances,
            custom_pattern=custom_pattern
        )
        
        self.traders[victim_id] = trader
        logger.info(f"Added victim trader: {trader}")
        return trader
    
    async def generate_pending_trades(self, available_pools: List[str]) -> List[VictimTrade]:
        """Generate pending trades from all traders"""
        current_time = time.time()
        new_trades = []
        
        for trader in self.traders.values():
            trade = await trader.generate_trade(available_pools, current_time)
            if trade:
                new_trades.append(trade)
                
        self.pending_trades.extend(new_trades)
        return new_trades
    
    async def execute_pending_trades(self, pool_manager) -> List[VictimTrade]:
        """Execute all pending trades"""
        executed_trades = []
        failed_trades = []
        
        for trade in self.pending_trades:
            trader = self.traders[trade.victim_id]
            success = await trader.execute_trade(trade, pool_manager)
            
            if success:
                executed_trades.append(trade)
            else:
                failed_trades.append(trade)
        
        # Clear pending trades
        self.pending_trades = []
        
        logger.info(f"Executed {len(executed_trades)} trades, {len(failed_trades)} failed")
        return executed_trades
    
    def get_all_statistics(self) -> Dict[str, Any]:
        """Get statistics for all traders"""
        stats = {
            'total_traders': len(self.traders),
            'traders': {},
            'aggregate': {
                'total_trades': 0,
                'total_volume': 0,
                'total_mev_loss': 0,
                'avg_mev_attack_rate': 0
            }
        }
        
        attack_rates = []
        
        for trader_id, trader in self.traders.items():
            trader_stats = trader.get_statistics()
            stats['traders'][trader_id] = trader_stats
            
            # Aggregate statistics
            stats['aggregate']['total_trades'] += trader_stats['total_trades']
            stats['aggregate']['total_volume'] += trader_stats['total_volume']
            stats['aggregate']['total_mev_loss'] += trader_stats['total_mev_loss']
            
            if trader_stats['total_trades'] > 0:
                attack_rates.append(trader_stats['mev_attack_rate'])
        
        if attack_rates:
            stats['aggregate']['avg_mev_attack_rate'] = sum(attack_rates) / len(attack_rates)
        
        return stats


# Factory functions
def create_victim_trader_from_config(victim_config: Dict[str, Any]) -> VictimTrader:
    """Create victim trader from configuration"""
    victim_type = VictimType(victim_config.get('type', 'retail'))
    
    # Custom pattern if specified
    custom_pattern = None
    if 'custom_pattern' in victim_config:
        pattern_config = victim_config['custom_pattern']
        custom_pattern = TradingPattern(
            name=pattern_config.get('name', 'Custom'),
            frequency_seconds=pattern_config.get('frequency_seconds', 300.0),
            amount_range=tuple(pattern_config.get('amount_range', [5, 50])),
            slippage_tolerance=pattern_config.get('slippage_tolerance', 0.01),
            gas_sensitivity=pattern_config.get('gas_sensitivity', 0.5),
            patience_level=pattern_config.get('patience_level', 0.5),
            token_preference=pattern_config.get('token_preference', ["TOKEN1", "TOKEN2"])
        )
    
    trader = VictimTrader(
        victim_id=victim_config['victim_id'],
        victim_type=victim_type,
        wallet_address=victim_config.get('wallet_address', f"0x{hash(victim_config['victim_id']):040x}"[2:42]),
        wallet_private_key=victim_config.get('wallet_private_key', '0x' + '0' * 64),
        initial_balances=victim_config.get('initial_balances', {}),
        custom_pattern=custom_pattern
    )
    
    return trader


# Example usage and testing
if __name__ == "__main__":
    import asyncio
    
    async def test_victim_trader():
        """Test victim trader functionality"""
        print("👥 Testing Victim Trader System")
        
        # Create trader manager
        manager = VictimTraderManager()
        
        # Add different types of victim traders
        trader_configs = [
            {
                'victim_id': 'retail_alice',
                'type': VictimType.RETAIL,
                'initial_balances': {'TOKEN1': 1000, 'TOKEN2': 500}
            },
            {
                'victim_id': 'whale_bob',
                'type': VictimType.WHALE,
                'initial_balances': {'TOKEN1': 10000, 'TOKEN2': 20000}
            },
            {
                'victim_id': 'dca_charlie',
                'type': VictimType.DCA_BOT,
                'initial_balances': {'TOKEN1': 5000, 'TOKEN2': 0}
            }
        ]
        
        for config in trader_configs:
            manager.add_trader(
                config['victim_id'],
                config['type'],
                config['initial_balances']
            )
            print(f"Added {config['victim_id']} ({config['type'].value})")
        
        # Simulate trading over time
        available_pools = ['TOKEN1_TOKEN2_3000']
        
        print("\n🎯 Simulating victim trading...")
        for round_num in range(5):
            print(f"\n🔄 Round {round_num + 1}")
            
            # Generate potential trades
            new_trades = await manager.generate_pending_trades(available_pools)
            
            if new_trades:
                for trade in new_trades:
                    print(f"  📝 {trade.victim_id}: {trade.amount_in:.1f} {trade.token_in_symbol} -> {trade.token_out_symbol}")
            
            # Simulate some time passing
            await asyncio.sleep(0.1)
        
        # Show final statistics
        print("\n📊 Final Victim Statistics:")
        stats = manager.get_all_statistics()
        
        for trader_id, trader_stats in stats['traders'].items():
            print(f"\n{trader_id}:")
            print(f"  Type: {trader_stats['victim_type']}")
            print(f"  Total Trades: {trader_stats['total_trades']}")
            print(f"  Volume: {trader_stats['total_volume']:.1f}")
            print(f"  Balances: {trader_stats['current_balances']}")
    
    # Run test
    asyncio.run(test_victim_trader())
