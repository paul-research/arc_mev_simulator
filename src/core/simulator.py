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
        logger.info("🚀 Setting up MEV simulation components...")
        
        # 1. Setup pool manager and deploy contracts
        await self._setup_pools()
        
        # 2. Setup MEV bots
        await self._setup_mev_bots()
        
        # 3. Setup victim traders
        await self._setup_victim_traders()
        
        # 4. Fund all accounts
        await self._fund_accounts()
        
        logger.info("✅ MEV simulation setup complete")
    
    async def _setup_pools(self) -> None:
        """Setup pool manager and deploy tokens/pools"""
        logger.info("🏊‍♂️ Setting up pools and tokens...")
        
        # Get network config and deployer key
        network_config = self.config['network']
        deployer_key = os.getenv('DEPLOYER_PRIVATE_KEY', "0x" + "1" * 64)
        
        # Try real deployment first, fallback to mock if needed
        try:
            # Import deployment system
            from ..deployment.deployer import ContractDeployer
            from ..utils.blockchain import connect_to_network
            
            # Connect to real blockchain
            blockchain_client = connect_to_network(network_config)
            connected = await blockchain_client.connect()
            
            if connected:
                logger.info("✅ Connected to real blockchain - using actual contracts")
                
                # Create real deployer
                deployer = ContractDeployer(blockchain_client, deployer_key)
                
                # Create pool manager with real web3
                from .pool_manager import PoolManager
                self.pool_manager = PoolManager(blockchain_client.w3, network_config, deployer_key)
                self.pool_manager.deployer = deployer  # Connect real deployer
                
            else:
                raise ConnectionError("Failed to connect to blockchain")
                
        except Exception as e:
            logger.warning(f"Failed to connect to real blockchain: {e}")
            logger.info("🔄 Falling back to simulation mode")
            
            # Fallback to mock implementation for testing
            from unittest.mock import MagicMock
            mock_web3 = MagicMock()
            mock_web3.is_connected.return_value = True
            
            from .pool_manager import PoolManager
            self.pool_manager = PoolManager(mock_web3, network_config, deployer_key)
        
        # Use existing tokens from network config if available
        pools_config = self.config['pools']
        network_contracts = self.config['network'].get('contracts', {})
        
        # Check if we have existing token addresses
        if 'token1_token' in network_contracts and 'token2_token' in network_contracts:
            logger.info("📝 Using existing tokens from network config...")
            
            # Create TokenInfo objects for existing tokens
            from src.core.pool_manager import TokenInfo
            
            token1_info = TokenInfo(
                address=network_contracts['token1_token'],
                name="Token1",
                symbol="TOKEN1",
                decimals=18,
                total_supply=1000000
            )
            
            token2_info = TokenInfo(
                address=network_contracts['token2_token'],
                name="Token2", 
                symbol="TOKEN2",
                decimals=18,
                total_supply=1000000
            )
            
            # Store in pool manager
            self.pool_manager.deployed_tokens['TOKEN1'] = token1_info
            self.pool_manager.deployed_tokens['TOKEN2'] = token2_info
            
            logger.info(f"✅ Using existing Token1: {token1_info.address}")
            logger.info(f"✅ Using existing Token2: {token2_info.address}")
            
        else:
            # Deploy new tokens
            logger.info("📝 Deploying new tokens...")
            token_a_config = pools_config['token_a']
            token_b_config = pools_config['token_b']
            
            token_a = await self.pool_manager.deploy_token(
                token_a_config['name'],
                token_a_config['symbol'],
                token_a_config['total_supply'],
                token_a_config['decimals']
            )
            
            token_b = await self.pool_manager.deploy_token(
                token_b_config['name'],
                token_b_config['symbol'], 
                token_b_config['total_supply'],
                token_b_config['decimals']
            )
            
            logger.info(f"Deployed tokens: {token_a.symbol}, {token_b.symbol}")
        
        # Check if tokens are loaded (either existing or newly deployed)
        if 'TOKEN1' in self.pool_manager.deployed_tokens and 'TOKEN2' in self.pool_manager.deployed_tokens:
            logger.info("✅ Tokens ready: TOKEN1, TOKEN2")
        
        # Check if we have an existing pool
        if 'uniswap_pool' in network_contracts:
            logger.info("🏊‍♂️ Using existing Uniswap V3 pool...")
            
            # Create PoolInfo object for existing pool
            from src.core.pool_manager import PoolInfo
            
            token1_info = self.pool_manager.deployed_tokens['TOKEN1'] 
            token2_info = self.pool_manager.deployed_tokens['TOKEN2']
            
            existing_pool_info = PoolInfo(
                address=network_contracts['uniswap_pool'],
                token0=token1_info,
                token1=token2_info,
                fee=3000,
                tick_spacing=60,
                current_tick=0,
                sqrt_price_x96=0,  # Will be updated when queried
                liquidity=0  # Will be updated when queried
            )
            
            # Store existing pool
            pool_key = f"TOKEN1_TOKEN2_3000"
            self.pool_manager.created_pools[pool_key] = existing_pool_info
            
            # Connect real pool contract for blockchain queries
            try:
                from ..deployment.uniswap_v3_abis import UNISWAP_V3_POOL_ABI
                real_pool_contract = self.pool_manager.web3.eth.contract(
                    address=network_contracts['uniswap_pool'],
                    abi=UNISWAP_V3_POOL_ABI
                )
                
                # Store pool contract for real queries
                if not hasattr(self.pool_manager, 'pool_contracts'):
                    self.pool_manager.pool_contracts = {}
                self.pool_manager.pool_contracts[pool_key] = real_pool_contract
                
                logger.info(f"✅ Connected real pool contract: {existing_pool_info.address}")
                
            except Exception as e:
                logger.warning(f"Could not connect real pool contract: {e}")
            
            logger.info(f"✅ Using existing pool: {existing_pool_info.address}")
            
        else:
            # Create new pool  
            logger.info("🏊‍♂️ Creating new Uniswap V3 pool...")
            pool_config = pools_config['uniswap_v3']
            pool_info = await self.pool_manager.create_pool(
                "TOKEN1",
                "TOKEN2", 
                pool_config['fee_tier'],
                pool_config['initial_price_ratio']
            )
            
            # Add initial liquidity
            liquidity_config = pool_config['liquidity']
            await self.pool_manager.add_liquidity(
                f"TOKEN1_TOKEN2_{pool_config['fee_tier']}",
                liquidity_config['amount_token_a'],
                liquidity_config['amount_token_b']
            )
            
            logger.info(f"Created pool with {liquidity_config['amount_token_a']}:{liquidity_config['amount_token_b']} liquidity")
    
    async def _setup_mev_bots(self) -> None:
        """Setup MEV bots from configuration"""
        logger.info("🤖 Setting up MEV bots...")
        
        mev_config = self.config['mev_bots']
        
        for bot_id, bot_config in mev_config['profiles'].items():
            try:
                # Create bot from config
                bot = create_bot_from_config(bot_id, bot_config)
                self.mev_bots[bot_id] = bot
                
                # Add to latency manager
                latency_config = bot_config.get('latency', {})
                from .latency_simulator import LatencyProfile
                latency_profile = LatencyProfile(**latency_config)
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
                
                # Create trader
                trader = create_victim_trader_from_config(trader_config)
                self.victim_manager.traders[trader_id] = trader
                
                logger.info(f"Setup victim trader: {trader}")
                
            except Exception as e:
                logger.error(f"Failed to setup victim trader {trader_id}: {e}")
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
