"""
Latency simulation for realistic MEV bot competition modeling

This module simulates the real-world latency factors that affect MEV bot performance:
- Block detection delays
- Market data update lag  
- Calculation processing time
- Bundle creation overhead
- Network submission latency
- Jitter and variability effects
"""

import asyncio
import random
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class LatencyType(Enum):
    """Types of latency in MEV bot pipeline"""
    BLOCK_DETECTION = "block_detection"
    MARKET_UPDATE = "market_update" 
    CALCULATION = "calculation"
    BUNDLE_CREATION = "bundle_creation"
    NETWORK_SUBMISSION = "network_submission"


@dataclass
class LatencyProfile:
    """Latency profile for a specific MEV bot infrastructure"""
    block_detection: float      # Block detection latency (ms)
    market_update: float        # Market data update latency (ms)
    calculation: float          # MEV calculation latency (ms)
    bundle_creation: float      # Bundle creation latency (ms)
    network_submission: float   # Network submission latency (ms)
    jitter: float              # Jitter ratio (0.0 - 1.0)
    
    def total_average_latency(self) -> float:
        """Calculate average total latency"""
        return (self.block_detection + self.market_update + 
                self.calculation + self.bundle_creation + 
                self.network_submission)
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary"""
        return {
            'block_detection': self.block_detection,
            'market_update': self.market_update,
            'calculation': self.calculation, 
            'bundle_creation': self.bundle_creation,
            'network_submission': self.network_submission,
            'jitter': self.jitter,
            'total_avg': self.total_average_latency()
        }


class LatencySimulator:
    """Simulates realistic network latency for MEV bots"""
    
    # Predefined latency profiles for different infrastructure tiers
    PROFILES = {
        "high_performance": LatencyProfile(
            block_detection=50,
            market_update=100,
            calculation=80,
            bundle_creation=60,
            network_submission=120,
            jitter=0.1
        ),
        "medium_performance": LatencyProfile(
            block_detection=150,
            market_update=200,
            calculation=180,
            bundle_creation=120,
            network_submission=250,
            jitter=0.2
        ),
        "low_performance": LatencyProfile(
            block_detection=300,
            market_update=500,
            calculation=400,
            bundle_creation=250,
            network_submission=600,
            jitter=0.3
        ),
        "variable_performance": LatencyProfile(
            block_detection=200,
            market_update=300,
            calculation=150,
            bundle_creation=100,
            network_submission=400,
            jitter=0.5
        )
    }
    
    def __init__(self, bot_id: str, profile: Optional[LatencyProfile] = None):
        """
        Initialize latency simulator
        
        Args:
            bot_id: Unique identifier for the bot
            profile: Custom latency profile, or None to use default
        """
        self.bot_id = bot_id
        self.profile = profile or self.PROFILES["medium_performance"]
        self.latency_history: Dict[LatencyType, list] = {
            lt: [] for lt in LatencyType
        }
        
    @classmethod
    def from_config(cls, bot_id: str, config: Dict[str, float]) -> "LatencySimulator":
        """Create latency simulator from configuration dictionary"""
        profile = LatencyProfile(**config)
        return cls(bot_id, profile)
    
    def apply_jitter(self, base_latency: float) -> float:
        """Apply random jitter to base latency"""
        jitter_range = base_latency * self.profile.jitter
        jitter = (random.random() - 0.5) * 2 * jitter_range
        return max(0, base_latency + jitter)
    
    async def simulate_latency(self, latency_type: LatencyType) -> float:
        """
        Simulate latency for a specific operation type
        
        Args:
            latency_type: Type of operation to simulate
            
        Returns:
            Actual latency experienced (in milliseconds)
        """
        # Get base latency for this operation type
        base_latency = getattr(self.profile, latency_type.value)
        
        # Apply jitter
        actual_latency = self.apply_jitter(base_latency)
        
        # Record for analytics
        self.latency_history[latency_type].append(actual_latency)
        
        # Log the latency
        logger.debug(
            f"🕐 [{self.bot_id}] {latency_type.value}: {actual_latency:.1f}ms"
        )
        
        # Actually sleep for the latency duration
        await asyncio.sleep(actual_latency / 1000.0)  # Convert ms to seconds
        
        return actual_latency
    
    async def block_detection_delay(self) -> float:
        """Simulate block detection latency"""
        return await self.simulate_latency(LatencyType.BLOCK_DETECTION)
    
    async def market_update_delay(self) -> float:
        """Simulate market data update latency"""
        return await self.simulate_latency(LatencyType.MARKET_UPDATE)
    
    async def calculation_delay(self) -> float:
        """Simulate MEV calculation processing latency"""
        return await self.simulate_latency(LatencyType.CALCULATION)
    
    async def bundle_creation_delay(self) -> float:
        """Simulate bundle creation latency"""
        return await self.simulate_latency(LatencyType.BUNDLE_CREATION)
    
    async def network_submission_delay(self) -> float:
        """Simulate network submission latency"""
        return await self.simulate_latency(LatencyType.NETWORK_SUBMISSION)
    
    def get_statistics(self) -> Dict[str, Dict[str, float]]:
        """Get latency statistics for analysis"""
        stats = {}
        
        for latency_type, history in self.latency_history.items():
            if not history:
                stats[latency_type.value] = {
                    'count': 0,
                    'mean': 0,
                    'min': 0,
                    'max': 0,
                    'std': 0
                }
                continue
                
            stats[latency_type.value] = {
                'count': len(history),
                'mean': sum(history) / len(history),
                'min': min(history),
                'max': max(history),
                'std': (sum((x - sum(history) / len(history))**2 for x in history) / len(history))**0.5
            }
        
        # Add total statistics
        all_latencies = []
        for history in self.latency_history.values():
            all_latencies.extend(history)
            
        if all_latencies:
            stats['total'] = {
                'count': len(all_latencies),
                'mean': sum(all_latencies) / len(all_latencies),
                'min': min(all_latencies),
                'max': max(all_latencies),
                'std': (sum((x - sum(all_latencies) / len(all_latencies))**2 for x in all_latencies) / len(all_latencies))**0.5
            }
        
        return stats
    
    def reset_history(self) -> None:
        """Reset latency history for new simulation run"""
        for latency_type in LatencyType:
            self.latency_history[latency_type] = []
    
    def compare_with(self, other: "LatencySimulator") -> Dict[str, float]:
        """
        Compare latency performance with another simulator
        
        Returns:
            Dictionary with comparison metrics
        """
        self_stats = self.get_statistics()
        other_stats = other.get_statistics()
        
        comparison = {}
        
        for latency_type in LatencyType:
            type_name = latency_type.value
            
            if (type_name in self_stats and type_name in other_stats and
                self_stats[type_name]['count'] > 0 and other_stats[type_name]['count'] > 0):
                
                self_mean = self_stats[type_name]['mean']
                other_mean = other_stats[type_name]['mean']
                
                comparison[type_name] = {
                    'advantage_ms': other_mean - self_mean,
                    'advantage_pct': ((other_mean - self_mean) / other_mean) * 100 if other_mean > 0 else 0
                }
        
        return comparison
    
    def __str__(self) -> str:
        """String representation of latency simulator"""
        return (f"LatencySimulator(bot_id='{self.bot_id}', "
                f"avg_total={self.profile.total_average_latency():.1f}ms, "
                f"jitter={self.profile.jitter:.1%})")
    
    def __repr__(self) -> str:
        return self.__str__()


class CompetitionLatencyManager:
    """Manages latency simulation for multiple competing MEV bots"""
    
    def __init__(self):
        self.simulators: Dict[str, LatencySimulator] = {}
        self.competition_history: list = []
    
    def add_bot(self, bot_id: str, profile: LatencyProfile) -> None:
        """Add a bot with its latency profile"""
        self.simulators[bot_id] = LatencySimulator(bot_id, profile)
        logger.info(f"Added bot {bot_id} with latency profile: {profile}")
    
    def get_simulator(self, bot_id: str) -> Optional[LatencySimulator]:
        """Get latency simulator for a specific bot"""
        return self.simulators.get(bot_id)
    
    async def simulate_competition_round(self, operation_type: LatencyType) -> Dict[str, Tuple[str, float]]:
        """
        Simulate a competition round for all bots
        
        Returns:
            Dictionary mapping bot_id to (rank, latency) tuples
        """
        # Start all bots simultaneously
        tasks = {}
        start_time = time.time()
        
        for bot_id, simulator in self.simulators.items():
            task = asyncio.create_task(simulator.simulate_latency(operation_type))
            tasks[bot_id] = task
        
        # Wait for all to complete and collect results
        results = {}
        for bot_id, task in tasks.items():
            latency = await task
            completion_time = time.time() - start_time
            results[bot_id] = (completion_time * 1000, latency)  # Convert to ms
        
        # Rank bots by completion time
        sorted_results = sorted(results.items(), key=lambda x: x[1][0])
        ranked_results = {}
        
        for rank, (bot_id, (completion_time, latency)) in enumerate(sorted_results, 1):
            ranked_results[bot_id] = (rank, completion_time, latency)
            
        # Record competition history
        self.competition_history.append({
            'operation': operation_type.value,
            'timestamp': time.time(),
            'results': ranked_results
        })
        
        return ranked_results
    
    def get_competition_stats(self) -> Dict[str, Any]:
        """Get comprehensive competition statistics"""
        if not self.competition_history:
            return {}
        
        stats = {
            'total_rounds': len(self.competition_history),
            'bot_performance': {},
            'operation_analysis': {}
        }
        
        # Analyze per-bot performance
        for bot_id in self.simulators.keys():
            bot_ranks = []
            bot_times = []
            
            for round_data in self.competition_history:
                if bot_id in round_data['results']:
                    rank, completion_time, _ = round_data['results'][bot_id]
                    bot_ranks.append(rank)
                    bot_times.append(completion_time)
            
            if bot_ranks:
                stats['bot_performance'][bot_id] = {
                    'avg_rank': sum(bot_ranks) / len(bot_ranks),
                    'win_rate': sum(1 for r in bot_ranks if r == 1) / len(bot_ranks),
                    'avg_completion_time': sum(bot_times) / len(bot_times),
                    'total_rounds': len(bot_ranks)
                }
        
        return stats
    
    def reset_competition(self) -> None:
        """Reset competition history and bot latency history"""
        self.competition_history = []
        for simulator in self.simulators.values():
            simulator.reset_history()


# Example usage and testing
if __name__ == "__main__":
    import asyncio
    
    async def test_latency_simulation():
        """Test the latency simulation functionality"""
        print("🧪 Testing MEV Latency Simulation")
        
        # Create competition manager
        manager = CompetitionLatencyManager()
        
        # Add bots with different profiles
        manager.add_bot("bot1", LatencySimulator.PROFILES["high_performance"])
        manager.add_bot("bot2", LatencySimulator.PROFILES["medium_performance"])
        manager.add_bot("bot3", LatencySimulator.PROFILES["low_performance"])
        manager.add_bot("bot4", LatencySimulator.PROFILES["variable_performance"])
        
        print("\n📊 Running competition simulation...")
        
        # Simulate multiple rounds
        for i in range(5):
            print(f"\n🏁 Round {i+1}: Block Detection Competition")
            results = await manager.simulate_competition_round(LatencyType.BLOCK_DETECTION)
            
            for bot_id, (rank, completion_time, latency) in results.items():
                print(f"   {rank}. {bot_id}: {completion_time:.1f}ms (latency: {latency:.1f}ms)")
        
        # Show final statistics
        print("\n📈 Competition Statistics:")
        stats = manager.get_competition_stats()
        
        for bot_id, performance in stats['bot_performance'].items():
            print(f"   {bot_id}: avg_rank={performance['avg_rank']:.2f}, "
                  f"win_rate={performance['win_rate']:.1%}, "
                  f"avg_time={performance['avg_completion_time']:.1f}ms")
    
    # Run the test
    asyncio.run(test_latency_simulation())


