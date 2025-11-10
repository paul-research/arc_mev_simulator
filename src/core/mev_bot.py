# Circle Research Team - paul.kwon@circle.com
"""
MEV Bot implementation with strategy patterns and competition logic

This module implements intelligent MEV bots capable of:
- Sandwich attack detection and execution
- Multiple strategy patterns (aggressive, conservative, adaptive)
- Real-time competition analysis
- Profitability optimization
- Gas fee management and bidding strategies
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
import logging
from abc import ABC, abstractmethod
import random

from .latency_simulator import LatencySimulator, LatencyType

logger = logging.getLogger(__name__)


class BotStrategy(Enum):
    """MEV bot strategy types"""
    AGGRESSIVE = "aggressive"      # High bid, fast execution, maximum profit
    CONSERVATIVE = "conservative"  # Lower bid, safe execution, steady profit
    SLOW = "slow"                 # Minimal bid, patient execution
    ADAPTIVE = "adaptive"         # Learning strategy that adapts to competition


@dataclass
class MEVOpportunity:
    """Represents a detected MEV opportunity"""
    opportunity_id: str
    type: str  # sandwich, arbitrage, liquidation
    victim_tx_hash: Optional[str]
    pool_address: str
    token_in: str
    token_out: str
    victim_amount_in: float
    estimated_profit: float
    gas_cost: float
    confidence_score: float  # 0.0 - 1.0
    detected_at: float
    expiry_at: float
    

@dataclass
class AttackResult:
    """Result of an executed MEV attack"""
    opportunity_id: str
    bot_id: str
    attack_type: str
    success: bool
    
    # Transaction details
    frontrun_tx_hash: Optional[str] = None
    victim_tx_hash: Optional[str] = None
    backrun_tx_hash: Optional[str] = None
    
    # Financial results
    gross_profit: float = 0.0
    gas_costs: float = 0.0
    net_profit: float = 0.0
    victim_loss: float = 0.0
    
    # Execution metrics
    total_latency_ms: float = 0.0
    execution_timestamp: float = field(default_factory=time.time)
    
    # Market impact
    slippage_caused: float = 0.0
    pool_price_impact: float = 0.0
    

class BotStrategyEngine(ABC):
    """Abstract base class for bot strategy implementations"""
    
    @abstractmethod
    def calculate_bid_amount(self, opportunity: MEVOpportunity, competition_level: float) -> float:
        """Calculate how much to bid for this opportunity"""
        pass
    
    @abstractmethod
    def should_execute_attack(self, opportunity: MEVOpportunity, competition_data: Dict) -> bool:
        """Decide whether to execute this attack"""
        pass
    
    @abstractmethod
    def calculate_frontrun_amount(self, opportunity: MEVOpportunity) -> float:
        """Calculate optimal frontrun trade size"""
        pass
    
    @abstractmethod
    def adapt_to_results(self, recent_results: List[AttackResult]) -> None:
        """Adapt strategy based on recent performance"""
        pass


class AggressiveStrategy(BotStrategyEngine):
    """Aggressive high-frequency strategy"""
    
    def __init__(self, bid_percentage: float = 85.0):
        self.bid_percentage = bid_percentage
        
    def calculate_bid_amount(self, opportunity: MEVOpportunity, competition_level: float) -> float:
        base_bid = opportunity.estimated_profit * (self.bid_percentage / 100.0)
        # Increase bid based on competition
        competition_multiplier = 1.0 + (competition_level * 0.5)
        return base_bid * competition_multiplier
    
    def should_execute_attack(self, opportunity: MEVOpportunity, competition_data: Dict) -> bool:
        # Aggressive: execute if profit > gas cost * 2
        return opportunity.estimated_profit > (opportunity.gas_cost * 2.0)
    
    def calculate_frontrun_amount(self, opportunity: MEVOpportunity) -> float:
        # Aggressive: larger frontrun for maximum impact
        return opportunity.victim_amount_in * 0.6  # 60% of victim amount
    
    def adapt_to_results(self, recent_results: List[AttackResult]) -> None:
        # Increase aggression if winning
        success_rate = sum(1 for r in recent_results if r.success) / len(recent_results) if recent_results else 0
        if success_rate > 0.7:
            self.bid_percentage = min(95.0, self.bid_percentage * 1.1)


class ConservativeStrategy(BotStrategyEngine):
    """Conservative steady-profit strategy"""
    
    def __init__(self, bid_percentage: float = 60.0):
        self.bid_percentage = bid_percentage
        
    def calculate_bid_amount(self, opportunity: MEVOpportunity, competition_level: float) -> float:
        # Conservative: lower, stable bids
        base_bid = opportunity.estimated_profit * (self.bid_percentage / 100.0)
        return base_bid  # Don't increase much for competition
    
    def should_execute_attack(self, opportunity: MEVOpportunity, competition_data: Dict) -> bool:
        # Conservative: only execute high-confidence, profitable opportunities
        return (opportunity.estimated_profit > (opportunity.gas_cost * 3.0) and 
                opportunity.confidence_score > 0.8)
    
    def calculate_frontrun_amount(self, opportunity: MEVOpportunity) -> float:
        # Conservative: smaller, safer frontrun
        return opportunity.victim_amount_in * 0.3  # 30% of victim amount
    
    def adapt_to_results(self, recent_results: List[AttackResult]) -> None:
        # Adjust bid based on profitability
        if recent_results:
            avg_profit = sum(r.net_profit for r in recent_results) / len(recent_results)
            if avg_profit < 0:
                self.bid_percentage *= 0.9  # Reduce bids if losing money


class AdaptiveStrategy(BotStrategyEngine):
    """Learning strategy that adapts to competition"""
    
    def __init__(self, initial_bid_percentage: float = 70.0):
        self.bid_percentage = initial_bid_percentage
        self.learning_rate = 0.1
        self.competition_history: List[float] = []
        self.performance_history: List[float] = []
        
    def calculate_bid_amount(self, opportunity: MEVOpportunity, competition_level: float) -> float:
        # Adaptive: adjust based on learned competition patterns
        self.competition_history.append(competition_level)
        
        # Use recent competition history to predict optimal bid
        if len(self.competition_history) > 5:
            avg_competition = sum(self.competition_history[-5:]) / 5
            adaptive_multiplier = 1.0 + (avg_competition * 0.7)
        else:
            adaptive_multiplier = 1.0 + (competition_level * 0.4)
            
        base_bid = opportunity.estimated_profit * (self.bid_percentage / 100.0)
        return base_bid * adaptive_multiplier
    
    def should_execute_attack(self, opportunity: MEVOpportunity, competition_data: Dict) -> bool:
        # Adaptive: learn from past success rates
        min_profit_ratio = 2.5  # Default
        
        if self.performance_history:
            recent_performance = sum(self.performance_history[-10:]) / min(10, len(self.performance_history))
            if recent_performance > 0:
                min_profit_ratio = max(1.5, min_profit_ratio * 0.9)  # Be more aggressive
            else:
                min_profit_ratio = min(4.0, min_profit_ratio * 1.1)  # Be more conservative
                
        return opportunity.estimated_profit > (opportunity.gas_cost * min_profit_ratio)
    
    def calculate_frontrun_amount(self, opportunity: MEVOpportunity) -> float:
        # Adaptive: adjust frontrun size based on success patterns
        base_ratio = 0.4  # 40% default
        
        if len(self.performance_history) > 3:
            recent_avg = sum(self.performance_history[-3:]) / 3
            if recent_avg > 0:
                base_ratio = min(0.6, base_ratio * 1.1)  # Increase if profitable
            else:
                base_ratio = max(0.2, base_ratio * 0.9)  # Decrease if losing
                
        return opportunity.victim_amount_in * base_ratio
    
    def adapt_to_results(self, recent_results: List[AttackResult]) -> None:
        # Learn from all results
        for result in recent_results:
            self.performance_history.append(result.net_profit)
            
            # Adjust bid percentage based on success
            if result.success and result.net_profit > 0:
                self.bid_percentage = min(90.0, self.bid_percentage * (1 + self.learning_rate))
            elif not result.success or result.net_profit <= 0:
                self.bid_percentage = max(30.0, self.bid_percentage * (1 - self.learning_rate))
        
        # Keep history manageable
        if len(self.performance_history) > 50:
            self.performance_history = self.performance_history[-30:]


class MEVBot:
    """Intelligent MEV bot with configurable strategy and latency simulation"""
    
    def __init__(self, 
                 bot_id: str,
                 strategy_type: BotStrategy,
                 latency_simulator: LatencySimulator,
                 wallet_address: str,
                 initial_balance: float,
                 strategy_params: Optional[Dict[str, Any]] = None):
        """
        Initialize MEV bot
        
        Args:
            bot_id: Unique identifier for this bot
            strategy_type: Bot strategy type
            latency_simulator: Latency simulation engine
            wallet_address: Bot's wallet address
            initial_balance: Starting balance in USDC
            strategy_params: Strategy-specific parameters
        """
        self.bot_id = bot_id
        self.strategy_type = strategy_type
        self.latency_simulator = latency_simulator
        self.wallet_address = wallet_address
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        
        # Initialize strategy engine
        self.strategy_engine = self._create_strategy_engine(strategy_type, strategy_params or {})
        
        # Performance tracking
        self.attack_history: List[AttackResult] = []
        self.opportunities_seen: List[MEVOpportunity] = []
        self.active_attacks: Dict[str, MEVOpportunity] = {}
        
        # Competition analysis
        self.competitor_data: Dict[str, Dict] = {}
        
        logger.info(f"Initialized MEV bot {bot_id} with {strategy_type.value} strategy")
    
    def _create_strategy_engine(self, strategy_type: BotStrategy, params: Dict[str, Any]) -> BotStrategyEngine:
        """Create appropriate strategy engine"""
        if strategy_type == BotStrategy.AGGRESSIVE:
            return AggressiveStrategy(params.get('bid_percentage', 85.0))
        elif strategy_type == BotStrategy.CONSERVATIVE:
            return ConservativeStrategy(params.get('bid_percentage', 60.0))
        elif strategy_type == BotStrategy.ADAPTIVE:
            return AdaptiveStrategy(params.get('bid_percentage', 70.0))
        elif strategy_type == BotStrategy.SLOW:
            return ConservativeStrategy(params.get('bid_percentage', 40.0))
        else:
            raise ValueError(f"Unknown strategy type: {strategy_type}")
    
    async def detect_mev_opportunity(self, block_data: Dict) -> List[MEVOpportunity]:
        """
        Detect MEV opportunities in new block data
        
        Args:
            block_data: New block information and pending transactions
            
        Returns:
            List of detected MEV opportunities
        """
        # Simulate block detection latency
        await self.latency_simulator.block_detection_delay()
        
        opportunities = []
        
        # Analyze pending transactions for sandwich opportunities
        pending_txs = block_data.get('pending_transactions', [])
        
        for tx in pending_txs:
            # Simulate market data update latency
            await self.latency_simulator.market_update_delay()
            
            # Check if this is a profitable sandwich target
            if self._is_sandwich_target(tx):
                opportunity = self._create_sandwich_opportunity(tx)
                if opportunity:
                    opportunities.append(opportunity)
                    self.opportunities_seen.append(opportunity)
        
        logger.debug(f"[{self.bot_id}] Detected {len(opportunities)} MEV opportunities")
        return opportunities
    
    def _is_sandwich_target(self, tx: Dict) -> bool:
        """Check if transaction is a good sandwich attack target"""
        # Simple heuristic: large swaps are good targets
        if tx.get('type') == 'swap':
            amount = tx.get('amount_in', 0)
            return amount > 10.0  # Threshold for profitable sandwich
        return False
    
    def _create_sandwich_opportunity(self, tx: Dict) -> Optional[MEVOpportunity]:
        """Create MEVOpportunity from target transaction"""
        try:
            opportunity = MEVOpportunity(
                opportunity_id=f"{self.bot_id}_{int(time.time() * 1000)}",
                type="sandwich",
                victim_tx_hash=tx.get('hash'),
                pool_address=tx.get('pool_address'),
                token_in=tx.get('token_in'),
                token_out=tx.get('token_out'),
                victim_amount_in=tx.get('amount_in', 0),
                estimated_profit=self._estimate_sandwich_profit(tx),
                gas_cost=self._estimate_gas_cost(),
                confidence_score=random.uniform(0.6, 0.95),  # Simulated confidence
                detected_at=time.time(),
                expiry_at=time.time() + 30.0  # 30 second window
            )
            return opportunity
            
        except Exception as e:
            logger.error(f"Failed to create opportunity: {e}")
            return None
    
    def _estimate_sandwich_profit(self, tx: Dict) -> float:
        """Estimate potential profit from sandwich attack"""
        # Simplified profit estimation
        amount_in = tx.get('amount_in', 0)
        
        # Profit roughly proportional to square root of trade size
        # (diminishing returns due to slippage)
        base_profit_rate = 0.003  # 0.3% base profit
        size_factor = (amount_in / 100.0) ** 0.5
        
        estimated_profit = amount_in * base_profit_rate * size_factor
        return max(0.001, estimated_profit)  # Minimum profit threshold
    
    def _estimate_gas_cost(self) -> float:
        """Estimate gas cost for sandwich attack (3 transactions)"""
        # Simplified gas estimation: frontrun + victim + backrun
        gas_per_tx = 150000  # Typical DEX swap gas
        gas_price_gwei = 300  # Arc testnet gas price
        
        total_gas = gas_per_tx * 3  # 3 transactions
        gas_cost_eth = (total_gas * gas_price_gwei) / 1e9 / 1e18  # Convert to ETH
        
        return gas_cost_eth
    
    async def evaluate_and_execute(self, opportunity: MEVOpportunity, competition_data: Dict) -> Optional[AttackResult]:
        """
        Evaluate opportunity and execute if profitable
        
        Args:
            opportunity: The MEV opportunity to evaluate
            competition_data: Information about competing bots
            
        Returns:
            AttackResult if executed, None if skipped
        """
        # Simulate calculation latency
        await self.latency_simulator.calculation_delay()
        
        # Check if we should execute this attack
        if not self.strategy_engine.should_execute_attack(opportunity, competition_data):
            logger.debug(f"[{self.bot_id}] Skipping opportunity {opportunity.opportunity_id}")
            return None
        
        # Calculate our bid
        competition_level = len(competition_data.get('active_bots', []))  / 10.0  # Normalize
        bid_amount = self.strategy_engine.calculate_bid_amount(opportunity, competition_level)
        
        # Check if we have enough balance
        if bid_amount > self.current_balance:
            logger.warning(f"[{self.bot_id}] Insufficient balance for bid: {bid_amount} > {self.current_balance}")
            return None
        
        # Execute the attack
        result = await self._execute_sandwich_attack(opportunity, bid_amount)
        
        # Update balance and history
        if result.success:
            self.current_balance += result.net_profit
        else:
            self.current_balance -= result.gas_costs
            
        self.attack_history.append(result)
        
        # Adapt strategy based on results
        if len(self.attack_history) >= 5:
            recent_results = self.attack_history[-5:]
            self.strategy_engine.adapt_to_results(recent_results)
        
        return result
    
    async def _execute_sandwich_attack(self, opportunity: MEVOpportunity, bid_amount: float) -> AttackResult:
        """Execute a sandwich attack"""
        start_time = time.time()
        
        try:
            # Simulate bundle creation latency
            await self.latency_simulator.bundle_creation_delay()
            
            # Calculate frontrun amount
            frontrun_amount = self.strategy_engine.calculate_frontrun_amount(opportunity)
            
            # Simulate network submission latency
            await self.latency_simulator.network_submission_delay()
            
            # Simulate attack execution (simplified)
            execution_success = random.random() > 0.2  # 80% success rate
            
            if execution_success:
                # Calculate realistic results
                gross_profit = opportunity.estimated_profit * random.uniform(0.8, 1.2)
                gas_costs = opportunity.gas_cost * random.uniform(0.9, 1.3)
                net_profit = gross_profit - gas_costs
                victim_loss = gross_profit * random.uniform(1.1, 1.5)  # Victim loses more than bot gains
                slippage_caused = frontrun_amount / opportunity.victim_amount_in * 0.02  # 2% per unit
                
                result = AttackResult(
                    opportunity_id=opportunity.opportunity_id,
                    bot_id=self.bot_id,
                    attack_type="sandwich",
                    success=True,
                    frontrun_tx_hash=f"0x{random.randint(10**63, 10**64-1):064x}",
                    victim_tx_hash=opportunity.victim_tx_hash,
                    backrun_tx_hash=f"0x{random.randint(10**63, 10**64-1):064x}",
                    gross_profit=gross_profit,
                    gas_costs=gas_costs,
                    net_profit=net_profit,
                    victim_loss=victim_loss,
                    slippage_caused=slippage_caused,
                    pool_price_impact=slippage_caused * 0.5,
                    total_latency_ms=(time.time() - start_time) * 1000
                )
                
                logger.info(f"[{self.bot_id}] Successful sandwich attack: {net_profit:.6f} USDC profit")
                
            else:
                # Failed attack
                result = AttackResult(
                    opportunity_id=opportunity.opportunity_id,
                    bot_id=self.bot_id,
                    attack_type="sandwich",
                    success=False,
                    gas_costs=opportunity.gas_cost,
                    net_profit=-opportunity.gas_cost,
                    total_latency_ms=(time.time() - start_time) * 1000
                )
                
                logger.warning(f"[{self.bot_id}] Failed sandwich attack: -{opportunity.gas_cost:.6f} USDC loss")
                
            return result
            
        except Exception as e:
            logger.error(f"[{self.bot_id}] Attack execution failed: {e}")
            return AttackResult(
                opportunity_id=opportunity.opportunity_id,
                bot_id=self.bot_id,
                attack_type="sandwich",
                success=False,
                gas_costs=opportunity.gas_cost,
                net_profit=-opportunity.gas_cost,
                total_latency_ms=(time.time() - start_time) * 1000
            )
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics"""
        if not self.attack_history:
            return {
                'total_attacks': 0,
                'success_rate': 0,
                'total_profit': 0,
                'avg_profit_per_attack': 0,
                'roi': 0
            }
        
        successful_attacks = [r for r in self.attack_history if r.success]
        total_profit = sum(r.net_profit for r in self.attack_history)
        
        stats = {
            'total_attacks': len(self.attack_history),
            'successful_attacks': len(successful_attacks),
            'success_rate': len(successful_attacks) / len(self.attack_history),
            'total_profit': total_profit,
            'avg_profit_per_attack': total_profit / len(self.attack_history),
            'current_balance': self.current_balance,
            'roi': (self.current_balance - self.initial_balance) / self.initial_balance,
            'opportunities_seen': len(self.opportunities_seen),
            'conversion_rate': len(self.attack_history) / max(1, len(self.opportunities_seen))
        }
        
        # Add latency statistics
        stats['latency_stats'] = self.latency_simulator.get_statistics()
        
        return stats
    
    def __str__(self) -> str:
        """String representation of MEV bot"""
        return (f"MEVBot(id='{self.bot_id}', strategy='{self.strategy_type.value}', "
                f"balance={self.current_balance:.6f}, attacks={len(self.attack_history)})")
    
    def __repr__(self) -> str:
        return self.__str__()


# Factory functions for easy bot creation
def create_bot_from_config(bot_id: str, config: Dict[str, Any]) -> MEVBot:
    """Create MEV bot from configuration dictionary"""
    from .latency_simulator import LatencySimulator
    
    # Create latency simulator
    latency_config = config.get('latency', {})
    latency_simulator = LatencySimulator.from_config(bot_id, latency_config)
    
    # Parse strategy
    strategy_type = BotStrategy(config.get('strategy', 'conservative'))
    
    # Create bot
    bot = MEVBot(
        bot_id=bot_id,
        strategy_type=strategy_type,
        latency_simulator=latency_simulator,
        wallet_address=config.get('wallet_address', f'0x{random.randint(10**39, 10**40-1):040x}'),
        initial_balance=config.get('initial_balance_eth', 1.0),
        strategy_params=config.get('strategy_params', {})
    )
    
    return bot


# Example usage and testing
if __name__ == "__main__":
    import asyncio
    
    async def test_mev_bot():
        """Test MEV bot functionality"""
        print("🤖 Testing MEV Bot Engine")
        
        # Create bots with different strategies
        bots = []
        
        for i, strategy in enumerate([BotStrategy.AGGRESSIVE, BotStrategy.CONSERVATIVE, BotStrategy.ADAPTIVE], 1):
            from .latency_simulator import LatencySimulator
            latency_sim = LatencySimulator(f"bot{i}")
            
            bot = MEVBot(
                bot_id=f"bot{i}",
                strategy_type=strategy,
                latency_simulator=latency_sim,
                wallet_address=f"0x{i:040x}",
                initial_balance=1.0
            )
            bots.append(bot)
            print(f"Created {bot}")
        
        # Simulate some MEV opportunities
        print("\n🎯 Simulating MEV opportunities...")
        
        for round_num in range(5):
            print(f"\n🔄 Round {round_num + 1}")
            
            # Create mock block data
            block_data = {
                'block_number': round_num + 1,
                'pending_transactions': [
                    {
                        'hash': f'0x{random.randint(10**63, 10**64-1):064x}',
                        'type': 'swap',
                        'amount_in': random.uniform(20, 200),
                        'pool_address': f'0x{random.randint(10**39, 10**40-1):040x}',
                        'token_in': 'TokenA',
                        'token_out': 'TokenB'
                    }
                    for _ in range(random.randint(1, 3))
                ]
            }
            
            # Each bot analyzes opportunities
            all_results = []
            for bot in bots:
                opportunities = await bot.detect_mev_opportunity(block_data)
                
                for opportunity in opportunities:
                    competition_data = {'active_bots': [b.bot_id for b in bots]}
                    result = await bot.evaluate_and_execute(opportunity, competition_data)
                    if result:
                        all_results.append(result)
            
            # Show results for this round
            if all_results:
                for result in all_results:
                    status = "✅" if result.success else "❌"
                    print(f"   {status} {result.bot_id}: {result.net_profit:+.6f} ETH")
        
        # Final performance summary
        print("\n📊 Final Performance Summary:")
        for bot in bots:
            stats = bot.get_performance_stats()
            print(f"\n{bot.bot_id} ({bot.strategy_type.value}):")
            print(f"  Success Rate: {stats['success_rate']:.1%}")
            print(f"  Total Profit: {stats['total_profit']:+.6f} ETH")
            print(f"  ROI: {stats['roi']:+.1%}")
            print(f"  Final Balance: {stats['current_balance']:.6f} USDC")
    
    # Run the test
    asyncio.run(test_mev_bot())
