"""
MEV Simulator - Main orchestration engine

This module coordinates all components for comprehensive MEV simulation:
- MEV bots with different strategies and latency profiles
- Victim traders with realistic behavior patterns  
- Pool management and trade execution
- Real-time competition simulation
- Data collection and analysis
- Result export and visualization
"""

import asyncio
import time
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
import csv
import json
from pathlib import Path

from .mev_bot import MEVBot, BotStrategy, MEVOpportunity, AttackResult, create_bot_from_config
from .victim_trader import VictimTrader, VictimTraderManager, VictimType, VictimTrade, create_victim_trader_from_config
from .pool_manager import PoolManager, create_pool_manager_from_config
from .latency_simulator import LatencySimulator, CompetitionLatencyManager
from ..utils.helpers import setup_logging, format_currency

logger = logging.getLogger(__name__)


@dataclass
class SimulationRound:
    """Data for a single simulation round"""
    round_number: int
    timestamp: float
    block_number: int
    
    # Victim activity
    victim_trades: List[VictimTrade] = field(default_factory=list)
    
    # MEV activity  
    mev_opportunities: List[MEVOpportunity] = field(default_factory=list)
    mev_attacks: List[AttackResult] = field(default_factory=list)
    
    # Competition data
    competition_results: Dict[str, Any] = field(default_factory=dict)
    
    # Pool state
    pool_states: Dict[str, Dict] = field(default_factory=dict)


@dataclass
class SimulationResults:
    """Complete simulation results"""
    config: Dict[str, Any]
    start_time: float
    end_time: float
    total_rounds: int
    
    # All simulation rounds
    rounds: List[SimulationRound] = field(default_factory=list)
    
    # Final statistics
    mev_bot_stats: Dict[str, Any] = field(default_factory=dict)
    victim_stats: Dict[str, Any] = field(default_factory=dict)
    pool_stats: Dict[str, Any] = field(default_factory=dict)
    
    # Aggregate metrics
    total_mev_profit: float = 0.0
    total_victim_loss: float = 0.0
    total_value_destroyed: float = 0.0
    average_success_rate: float = 0.0


class MEVSimulator:
    """Main MEV simulation orchestrator"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize MEV simulator with configuration
        
        Args:
            config: Full simulation configuration dictionary
        """
        self.config = config
        self.simulation_config = config['simulation']
        
        # Initialize logging
        setup_logging(config.get('logging', {}).get('level', 'INFO'))
        
        # Core components
        self.pool_manager: Optional[PoolManager] = None
        self.mev_bots: Dict[str, MEVBot] = {}
        self.backrun_bots: Dict[str, Any] = {}  # Beneficial arbitrage bots
        self.victim_manager = VictimTraderManager()
        self.latency_manager = CompetitionLatencyManager()
        
        # Simulation state
        self.current_block = 0
        self.simulation_running = False
        self.simulation_results = SimulationResults(
            config=config,
            start_time=time.time(),
            end_time=0,
            total_rounds=0
        )
        
        # Callbacks
        self.round_callbacks: List[Callable] = []
        self.attack_callbacks: List[Callable] = []
        
        logger.info(f"Initialized MEV Simulator: {self.simulation_config['name']}")
    
    async def setup(self) -> None:
        """Setup all simulation components"""
        logger.info("Setting up MEV simulation components...")
        
        # 1. Setup pool manager and deploy contracts
        await self._setup_pools()
        
        # 2. Setup MEV bots
        await self._setup_mev_bots()
        
        # 3. Setup backrun bots (beneficial)
        await self._setup_backrun_bots()
        
        # 4. Setup victim traders
        await self._setup_victim_traders()
        
        # 4. Fund all accounts
        await self._fund_accounts()
        
        logger.info("✅ MEV simulation setup complete")
    
    async def _setup_pools(self) -> None:
        """Setup pool manager using existing deployed contracts"""
        logger.info("🏊‍♂️ Setting up pools and tokens...")
        
        network_config = self.config['network']
        deployer_key = os.getenv('DEPLOYER_PRIVATE_KEY')
        if not deployer_key:
            raise ValueError("DEPLOYER_PRIVATE_KEY required")
        
        # Connect to blockchain
        from ..deployment.deployer import ContractDeployer
        from ..utils.blockchain import connect_to_network
        
        blockchain_client = connect_to_network(network_config)
        if not await blockchain_client.connect():
            raise ConnectionError("Failed to connect to blockchain")
        
        logger.info("✅ Connected to blockchain")
        
        # Setup deployer and pool manager
        deployer = ContractDeployer(blockchain_client, deployer_key)
        from .pool_manager import PoolManager
        self.pool_manager = PoolManager(blockchain_client.w3, network_config, deployer_key)
        self.pool_manager.deployer = deployer
        
        # Register existing contracts (DO NOT deploy new ones)
        contracts = network_config.get('contracts', {})
        token1_addr = blockchain_client.w3.to_checksum_address(contracts['token1_address'])
        token2_addr = blockchain_client.w3.to_checksum_address(contracts['token2_address'])
        pool_addr = blockchain_client.w3.to_checksum_address(contracts['uniswap_pool'])
        
        self.pool_manager.deployed_tokens = {
            'TOKEN1': type('TokenInfo', (), {'address': token1_addr, 'symbol': 'TOKEN1', 'decimals': 18})(),
            'TOKEN2': type('TokenInfo', (), {'address': token2_addr, 'symbol': 'TOKEN2', 'decimals': 18})()
        }
        
        pool_key = 'TOKEN1_TOKEN2_3000'
        self.pool_manager.created_pools[pool_key] = type('PoolInfo', (), {
            'address': pool_addr,
            'token0': self.pool_manager.deployed_tokens['TOKEN1'],
            'token1': self.pool_manager.deployed_tokens['TOKEN2'],
            'fee': 3000,
            'symbol': pool_key,
            'get_price_ratio': lambda: 2.0
        })()
        
        logger.info(f"✅ Pool: {pool_addr}")
        logger.info(f"   TOKEN1: {token1_addr}")
        logger.info(f"   TOKEN2: {token2_addr}")
    
    async def _setup_mev_bots(self) -> None:
        """Setup MEV bots from configuration"""
        logger.info("🤖 Setting up MEV bots...")
        
        mev_config = self.config['mev_bots']
        mev_bot_key = os.getenv('MEV_BOT_PRIVATE_KEY', '0x488e3ab7dc2033bc970e83bc6daf50ed83c4927e5d8f5bd5ca971df3d062cac2')
        
        from eth_account import Account
        mev_account = Account.from_key(mev_bot_key)
        
        for bot_id, bot_config in mev_config['profiles'].items():
            try:
                from .mev_bot import MEVBot, BotStrategy
                from .latency_simulator import LatencyProfile
                
                strategy = BotStrategy(bot_config['strategy'])
                latency_config = bot_config.get('latency', {})
                latency_profile = LatencyProfile(**latency_config)
                
                bot = MEVBot(
                    bot_id=bot_id,
                    strategy_type=strategy,
                    latency_simulator=self.latency_manager,
                    wallet_address=mev_account.address,
                    wallet_private_key=mev_bot_key,
                    initial_balance=bot_config.get('initial_balance', 1.0),
                    strategy_params=bot_config.get('strategy_params', {})
                )
                
                self.mev_bots[bot_id] = bot
                self.latency_manager.add_bot(bot_id, latency_profile)
                
                logger.info(f"Setup MEV bot: {bot}")
                
            except Exception as e:
                logger.error(f"Failed to setup MEV bot {bot_id}: {e}")
                raise
    
    async def _setup_victim_traders(self) -> None:
        """Setup victim traders from configuration"""
        logger.info("👥 Setting up victim traders...")
        
        victim_config = self.config['victim_transactions']
        
        if not victim_config.get('enabled', False):
            logger.info("Victim trading disabled")
            return
        
        for trader_id, trader_config in victim_config['traders'].items():
            try:
                trader_config['victim_id'] = trader_id
                
                # Get wallet private key from environment or config
                if 'wallet_private_key' in trader_config:
                    key_name = trader_config['wallet_private_key']
                    if key_name.startswith('${') and key_name.endswith('}'):
                        env_var = key_name[2:-1]
                        private_key = os.getenv(env_var)
                        if not private_key:
                            # Use default victim keys from environment config
                            private_key = os.getenv('VICTIM1_PRIVATE_KEY', '0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba')
                        trader_config['wallet_private_key'] = private_key
                else:
                    # Default to VICTIM1_PRIVATE_KEY
                    trader_config['wallet_private_key'] = os.getenv('VICTIM1_PRIVATE_KEY', '0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba')
                
                # Create trader
                trader = create_victim_trader_from_config(trader_config)
                self.victim_manager.traders[trader_id] = trader
                
                logger.info(f"Setup victim trader: {trader}")
                
            except Exception as e:
                logger.error(f"Failed to setup victim trader {trader_id}: {e}")
                raise
    
    async def _setup_backrun_bots(self) -> None:
        """Setup backrun bots (beneficial arbitrage bots)"""
        logger.info("Setting up backrun bots...")
        
        backrun_config = self.config.get('backrun_bots', {})
        
        if not backrun_config.get('enabled', False):
            logger.info("Backrun bots disabled")
            return
        
        # Import BackrunBot
        from .mev_bot import BackrunBot
        
        # Get pool config for target price
        pool_config = self.config.get('pools', {}).get('uniswap_v3', {})
        price_ratio_str = pool_config.get('initial_price_ratio', "1:2")
        
        # Parse target ratio (e.g., "1:2" -> 2.0)
        parts = price_ratio_str.split(':')
        target_ratio = float(parts[1]) / float(parts[0])
        
        logger.info(f"Backrun target price ratio: {target_ratio}")
        
        # Create backrun bots from config
        for bot_id, bot_config in backrun_config.items():
            if bot_id in ['enabled', 'count', 'description']:
                continue
                
            try:
                # Get bot parameters
                deviation_threshold = bot_config.get('strategy_params', {}).get(
                    'monitor_price_deviation', 0.003
                )
                initial_balance = bot_config.get('initial_balance_eth', 2.0)
                latency_config = bot_config.get('latency', {})
                total_latency = sum([
                    latency_config.get('block_detection', 100),
                    latency_config.get('calculation', 50),
                    latency_config.get('execution', 150)
                ])
                
                # Create backrun bot
                backrun_bot = BackrunBot(
                    bot_id=bot_id,
                    target_price_ratio=target_ratio,
                    deviation_threshold=deviation_threshold,
                    initial_balance=initial_balance,
                    pool_manager=self.pool_manager,
                    latency_ms=total_latency
                )
                
                self.backrun_bots[bot_id] = backrun_bot
                
                logger.info(f"Setup backrun bot: {bot_id} (target={target_ratio}, threshold={deviation_threshold})")
                
            except Exception as e:
                logger.error(f"Failed to setup backrun bot {bot_id}: {e}")
                raise
    
    async def _fund_accounts(self) -> None:
        """Fund all bot and victim accounts with initial balances"""
        logger.info("💰 Funding accounts...")
        
        # Fund victim traders with initial token balances
        for trader_id, trader in self.victim_manager.traders.items():
            # Set initial token balances based on config
            initial_balances = trader.initial_balances
            
            # If no initial balances specified, use defaults
            if not initial_balances:
                initial_balances = {
                    'TOKEN1': 1000.0,
                    'TOKEN2': 1000.0,
                    'ETH': 5.0
                }
            
            # Update trader balances
            trader.balances.update(initial_balances)
            
            logger.debug(f"Funded {trader_id} with balances: {trader.balances}")
        
        # Fund MEV bots (in simulation, just track balances)
        for bot_id, bot in self.mev_bots.items():
            # MEV bots get ETH for gas and some tokens for trading
            # Keep existing balance (current_balance is the correct attribute)
            logger.debug(f"MEV bot {bot_id} balance: {bot.current_balance} ETH")
        
        total_funded_bots = len(self.mev_bots)
        total_funded_victims = len(self.victim_manager.traders)
        
        logger.info(f"Funded {total_funded_bots} MEV bots and {total_funded_victims} victim traders")
    
    async def run_simulation(self, 
                           duration_minutes: Optional[float] = None,
                           target_rounds: Optional[int] = None) -> SimulationResults:
        """
        Run the complete MEV simulation
        
        Args:
            duration_minutes: Maximum simulation duration
            target_rounds: Target number of simulation rounds
            
        Returns:
            Complete simulation results
        """
        logger.info("🎮 Starting MEV simulation...")
        
        # Use config defaults if not specified
        if duration_minutes is None:
            duration_minutes = self.simulation_config.get('duration_minutes', 10)
        if target_rounds is None:
            target_rounds = self.simulation_config.get('target_transactions', 50)
        
        self.simulation_running = True
        self.simulation_results.start_time = time.time()
        
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        
        try:
            while (self.simulation_running and 
                   time.time() < end_time and 
                   len(self.simulation_results.rounds) < target_rounds):
                
                # Run a single simulation round
                round_result = await self._run_simulation_round()
                self.simulation_results.rounds.append(round_result)
                
                # Execute callbacks
                for callback in self.round_callbacks:
                    try:
                        await callback(round_result)
                    except Exception as e:
                        logger.error(f"Round callback error: {e}")
                
                # Brief pause between rounds
                await asyncio.sleep(0.1)
                
        except KeyboardInterrupt:
            logger.info("Simulation interrupted by user")
        except Exception as e:
            logger.error(f"Simulation error: {e}")
            raise
        finally:
            self.simulation_running = False
            self.simulation_results.end_time = time.time()
        
        # Compile final results
        await self._compile_final_results()
        
        logger.info(f"✅ Simulation complete: {len(self.simulation_results.rounds)} rounds in {duration_minutes:.1f} minutes")
        return self.simulation_results
    
    async def _run_simulation_round(self) -> SimulationRound:
        """Run a single simulation round"""
        self.current_block += 1
        current_time = time.time()
        
        round_data = SimulationRound(
            round_number=len(self.simulation_results.rounds) + 1,
            timestamp=current_time,
            block_number=self.current_block
        )
        
        # 1. Generate victim trades
        available_pools = self.pool_manager.list_pools()
        victim_trades = await self.victim_manager.generate_pending_trades(available_pools)
        
        if victim_trades:
            logger.debug(f"Round {round_data.round_number}: {len(victim_trades)} victim trades generated")
            round_data.victim_trades = victim_trades
        
        # 2. MEV bots detect opportunities
        mev_opportunities = []
        
        for bot in self.mev_bots.values():
            # Create block data for opportunity detection
            block_data = {
                'block_number': self.current_block,
                'pending_transactions': [
                    {
                        'hash': f'0x{hash(f"{trade.trade_id}_{current_time}"):064x}'[2:66],
                        'type': 'swap',
                        'amount_in': trade.amount_in,
                        'pool_address': 'mock_pool_address',
                        'token_in': trade.token_in_symbol,
                        'token_out': trade.token_out_symbol
                    }
                    for trade in victim_trades
                ]
            }
            
            opportunities = await bot.detect_mev_opportunity(block_data)
            mev_opportunities.extend(opportunities)
        
        round_data.mev_opportunities = mev_opportunities
        
        # 3. MEV competition and execution
        attack_results = []
        
        if mev_opportunities:
            # Competition data
            competition_data = {
                'active_bots': list(self.mev_bots.keys()),
                'opportunities_count': len(mev_opportunities),
                'round_number': round_data.round_number
            }
            
            # Each bot tries to execute opportunities
            for opportunity in mev_opportunities:
                competing_bots = []
                
                for bot in self.mev_bots.values():
                    result = await bot.evaluate_and_execute(opportunity, competition_data)
                    if result:
                        attack_results.append(result)
                        competing_bots.append(bot.bot_id)
                        
                        # Execute attack callbacks
                        for callback in self.attack_callbacks:
                            try:
                                await callback(result)
                            except Exception as e:
                                logger.error(f"Attack callback error: {e}")
                
                # Record competition results
                round_data.competition_results[opportunity.opportunity_id] = {
                    'competing_bots': competing_bots,
                    'winner': attack_results[-1].bot_id if attack_results else None
                }
        
        round_data.mev_attacks = attack_results
        
        # 4. Execute victim trades (with MEV impact)
        executed_victims = await self.victim_manager.execute_pending_trades(self.pool_manager)
        
        # Update victim trades with MEV attack information
        for victim_trade in executed_victims:
            for attack in attack_results:
                if attack.opportunity_id and victim_trade.trade_id in attack.opportunity_id:
                    victim_trade.mev_attacked = True
                    # Find victim and record MEV loss
                    victim = self.victim_manager.traders.get(victim_trade.victim_id)
                    if victim:
                        victim.record_mev_attack(victim_trade.trade_id, attack.victim_loss)
        
        # 5. Record pool states
        for pool_key in self.pool_manager.list_pools():
            round_data.pool_states[pool_key] = self.pool_manager.get_pool_state(pool_key)
        
        # 6. Backrun bots monitor and rebalance price
        if self.backrun_bots and (victim_trades or attack_results):
            for pool_key in available_pools:
                for bot_id, backrun_bot in self.backrun_bots.items():
                    try:
                        result = await backrun_bot.monitor_and_rebalance(pool_key)
                        if result:
                            round_data.mev_attacks.append(result)
                    except Exception as e:
                        logger.error(f"Backrun bot {bot_id} error: {e}")
        
        # Log round summary
        if attack_results or victim_trades:
            logger.info(f"Round {round_data.round_number}: {len(victim_trades)} victim trades, "
                       f"{len(mev_opportunities)} MEV opportunities, {len(attack_results)} attacks")
        
        return round_data
    
    async def _compile_final_results(self) -> None:
        """Compile final simulation statistics"""
        logger.info("📊 Compiling final results...")
        
        self.simulation_results.total_rounds = len(self.simulation_results.rounds)
        
        # MEV bot statistics
        for bot_id, bot in self.mev_bots.items():
            self.simulation_results.mev_bot_stats[bot_id] = bot.get_performance_stats()
        
        # Victim statistics
        self.simulation_results.victim_stats = self.victim_manager.get_all_statistics()
        
        # Pool statistics
        self.simulation_results.pool_stats = {}
        for pool_key in self.pool_manager.list_pools():
            self.simulation_results.pool_stats[pool_key] = self.pool_manager.get_pool_state(pool_key)
        
        # Calculate aggregate metrics
        total_mev_profit = 0
        total_victim_loss = 0
        successful_attacks = 0
        total_attacks = 0
        
        for round_data in self.simulation_results.rounds:
            for attack in round_data.mev_attacks:
                total_attacks += 1
                total_mev_profit += attack.net_profit
                total_victim_loss += attack.victim_loss
                if attack.success:
                    successful_attacks += 1
        
        self.simulation_results.total_mev_profit = total_mev_profit
        self.simulation_results.total_victim_loss = total_victim_loss
        self.simulation_results.total_value_destroyed = total_victim_loss - total_mev_profit
        self.simulation_results.average_success_rate = (successful_attacks / total_attacks) if total_attacks > 0 else 0
    
    async def export_results(self, 
                           output_dir: Optional[str] = None, 
                           formats: List[str] = ['csv', 'json']) -> Dict[str, str]:
        """
        Export simulation results to files
        
        Args:
            output_dir: Output directory (uses config default if None)
            formats: List of formats to export ('csv', 'json')
            
        Returns:
            Dictionary mapping format to output file path
        """
        if output_dir is None:
            output_dir = self.config['simulation'].get('output_dir', 'data/results')
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Generate timestamp for unique filenames
        timestamp = time.strftime('%Y-%m-%d_%H-%M-%S')
        simulation_name = self.simulation_config['name']
        
        exported_files = {}
        
        # Export CSV
        if 'csv' in formats:
            csv_file = output_path / f"{simulation_name}_{timestamp}.csv"
            await self._export_csv(csv_file)
            exported_files['csv'] = str(csv_file)
            logger.info(f"Exported CSV results: {csv_file}")
        
        # Export JSON
        if 'json' in formats:
            json_file = output_path / f"{simulation_name}_{timestamp}.json"
            await self._export_json(json_file)
            exported_files['json'] = str(json_file)
            logger.info(f"Exported JSON results: {json_file}")
        
        return exported_files
    
    async def _export_csv(self, file_path: Path) -> None:
        """Export results to CSV format"""
        with open(file_path, 'w', newline='') as csvfile:
            fieldnames = [
                'round_number', 'timestamp', 'block_number',
                'bot_id', 'attack_type', 'success', 'net_profit', 'victim_loss',
                'gas_costs', 'total_latency_ms', 'victim_id', 'victim_type',
                'trade_amount', 'slippage_caused'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for round_data in self.simulation_results.rounds:
                for attack in round_data.mev_attacks:
                    # Find corresponding victim trade
                    victim_trade = None
                    for trade in round_data.victim_trades:
                        if attack.opportunity_id and trade.trade_id in attack.opportunity_id:
                            victim_trade = trade
                            break
                    
                    row = {
                        'round_number': round_data.round_number,
                        'timestamp': round_data.timestamp,
                        'block_number': round_data.block_number,
                        'bot_id': attack.bot_id,
                        'attack_type': attack.attack_type,
                        'success': attack.success,
                        'net_profit': attack.net_profit,
                        'victim_loss': attack.victim_loss,
                        'gas_costs': attack.gas_costs,
                        'total_latency_ms': attack.total_latency_ms,
                        'victim_id': victim_trade.victim_id if victim_trade else '',
                        'victim_type': victim_trade.victim_type.value if victim_trade else '',
                        'trade_amount': victim_trade.amount_in if victim_trade else 0,
                        'slippage_caused': attack.slippage_caused
                    }
                    writer.writerow(row)
    
    async def _export_json(self, file_path: Path) -> None:
        """Export results to JSON format"""
        # Convert dataclasses to dictionaries for JSON serialization
        def serialize_dataclass(obj):
            if hasattr(obj, '__dict__'):
                result = {}
                for key, value in obj.__dict__.items():
                    if isinstance(value, list):
                        result[key] = [serialize_dataclass(item) for item in value]
                    elif isinstance(value, dict):
                        result[key] = {k: serialize_dataclass(v) for k, v in value.items()}
                    elif hasattr(value, '__dict__'):
                        result[key] = serialize_dataclass(value)
                    else:
                        result[key] = value
                return result
            else:
                return obj
        
        results_dict = serialize_dataclass(self.simulation_results)
        
        with open(file_path, 'w') as jsonfile:
            json.dump(results_dict, jsonfile, indent=2, default=str)
    
    def add_round_callback(self, callback: Callable) -> None:
        """Add callback function to be called after each round"""
        self.round_callbacks.append(callback)
    
    def add_attack_callback(self, callback: Callable) -> None:
        """Add callback function to be called after each MEV attack"""
        self.attack_callbacks.append(callback)
    
    def stop_simulation(self) -> None:
        """Stop the running simulation"""
        self.simulation_running = False
        logger.info("Simulation stop requested")


# Factory function
def create_simulator_from_config(config_path: str) -> MEVSimulator:
    """Create MEV simulator from configuration file"""
    import yaml
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    return MEVSimulator(config)


# Example usage
if __name__ == "__main__":
    async def main():
        """Example simulation run"""
        print("🎮 MEV Simulator Example")
        
        # Mock configuration for testing
        mock_config = {
            'simulation': {
                'name': 'test_simulation',
                'duration_minutes': 1,
                'target_transactions': 10,
                'output_dir': 'data/results'
            },
            'network': {
                'rpc_url': 'http://127.0.0.1:8545',
                'contracts': {
                    'uniswap_v3_factory': '0x1F98431c8aD98523631AE4a59f267346ea31F984',
                    'uniswap_v3_router': '0xE592427A0AEce92De3Edee1F18E0157C05861564',
                    'position_manager': '0xC36442b4c4e76c8f7a04B0eE0d2C2d4C6e5e4F2D',
                    'quoter_v2': '0x61fFE014bA17989E743c5F6cB21bF9697530B21e'
                },
                'gas': {'base_fee_gwei': 300}
            },
            'mev_bots': {
                'count': 2,
                'profiles': {
                    'bot1': {
                        'strategy': 'aggressive',
                        'initial_balance_eth': 1.0,
                        'latency': {
                            'block_detection': 50,
                            'market_update': 100,
                            'calculation': 80,
                            'bundle_creation': 60,
                            'network_submission': 120,
                            'jitter': 0.1
                        },
                        'strategy_params': {'bid_percentage': 85}
                    },
                    'bot2': {
                        'strategy': 'conservative',
                        'initial_balance_eth': 1.0,
                        'latency': {
                            'block_detection': 150,
                            'market_update': 200,
                            'calculation': 180,
                            'bundle_creation': 120,
                            'network_submission': 250,
                            'jitter': 0.2
                        },
                        'strategy_params': {'bid_percentage': 60}
                    }
                }
            },
            'pools': {
                'token_a': {'name': 'TestA', 'symbol': 'TESTA', 'total_supply': 1000000, 'decimals': 18},
                'token_b': {'name': 'TestB', 'symbol': 'TESTB', 'total_supply': 1000000, 'decimals': 18},
                'uniswap_v3': {
                    'fee_tier': 3000,
                    'initial_price_ratio': '1:2',
                    'liquidity': {'amount_token_a': 1000, 'amount_token_b': 2000}
                }
            },
            'victim_transactions': {
                'enabled': True,
                'traders': {
                    'victim1': {
                        'type': 'retail',
                        'initial_balances': {'TESTA': 1000, 'TESTB': 500}
                    }
                }
            }
        }
        
        try:
            # Create and setup simulator
            simulator = MEVSimulator(mock_config)
            await simulator.setup()
            
            # Add progress callback
            async def progress_callback(round_data):
                print(f"Round {round_data.round_number}: {len(round_data.mev_attacks)} MEV attacks")
            
            simulator.add_round_callback(progress_callback)
            
            # Run simulation
            results = await simulator.run_simulation(duration_minutes=0.5, target_rounds=5)
            
            # Export results
            exported = await simulator.export_results()
            
            print(f"\n📊 Simulation Results:")
            print(f"Total Rounds: {results.total_rounds}")
            print(f"MEV Profit: {results.total_mev_profit:.6f}")
            print(f"Victim Loss: {results.total_victim_loss:.6f}")
            print(f"Success Rate: {results.average_success_rate:.1%}")
            print(f"Exported: {list(exported.keys())}")
            
        except Exception as e:
            print(f"❌ Simulation failed: {e}")
            import traceback
            traceback.print_exc()
    
    # Run example
    asyncio.run(main())
