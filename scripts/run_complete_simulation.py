#!/usr/bin/env python3
"""
Complete MEV Simulation Runner

Runs a full MEV simulation with real contract deployment and analysis.
Handles environment setup, contract deployment, simulation execution, and results analysis.

Usage:
    python scripts/run_complete_simulation.py --environment development
    python scripts/run_complete_simulation.py --environment arc_testnet --confirm
    python scripts/run_complete_simulation.py --quick-test
"""

import asyncio
import argparse
import sys
import yaml
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.simulator import MEVSimulator
from src.deployment.deployer import deploy_mev_environment
from src.analysis.analyzer import MEVAnalyzer
from src.utils.helpers import setup_logging, format_currency, Timer
import logging

logger = logging.getLogger(__name__)


class CompleteMEVSimulation:
    """Complete MEV simulation orchestrator"""
    
    def __init__(self, environment: str = "development"):
        self.environment = environment
        self.config = None
        self.environment_config = None
        self.deployed_environment = None
        self.simulation_results = None
        
    def load_configurations(self) -> None:
        """Load all configuration files"""
        logger.info(f"📋 Loading configurations for environment: {self.environment}")
        
        # Load main config
        config_file = PROJECT_ROOT / "config" / "config.yaml"
        with open(config_file) as f:
            self.config = yaml.safe_load(f)
        
        # Load environment config
        env_file = PROJECT_ROOT / "config" / "environment.yaml"
        with open(env_file) as f:
            env_configs = yaml.safe_load(f)
            
        if self.environment not in env_configs:
            raise ValueError(f"Environment '{self.environment}' not found in environment.yaml")
        
        self.environment_config = env_configs[self.environment]
        
        # Override network config with environment-specific settings
        self.config['network'] = self.environment_config['network']
        
        logger.info(f"✅ Configurations loaded successfully")
        
    def setup_environment_variables(self) -> None:
        """Setup environment variables from config"""
        logger.info("⚙️ Setting up environment variables...")
        
        accounts = self.environment_config.get('accounts', {})
        
        # Set deployer key
        if 'deployer' in accounts:
            os.environ['DEPLOYER_PRIVATE_KEY'] = accounts['deployer']['private_key']
            
        # Set bot keys
        bot_accounts = accounts.get('mev_bots', {})
        for i, (bot_id, bot_config) in enumerate(bot_accounts.items(), 1):
            os.environ[f'BOT{i}_PRIVATE_KEY'] = bot_config['private_key']
            
        # Set victim keys
        victim_accounts = accounts.get('victims', {})
        for i, (victim_id, victim_config) in enumerate(victim_accounts.items(), 1):
            os.environ[f'VICTIM{i}_PRIVATE_KEY'] = victim_config['private_key']
            
        logger.info(f"✅ Environment variables configured")
    
    def update_config_with_environment(self) -> None:
        """Update main config with environment-specific settings"""
        logger.info("🔧 Updating config with environment settings...")
        
        accounts = self.environment_config.get('accounts', {})
        
        # Update MEV bot configurations
        if 'mev_bots' in accounts:
            bot_profiles = self.config['mev_bots']['profiles']
            bot_accounts = accounts['mev_bots']
            
            for bot_id, bot_config in list(bot_profiles.items()):
                if bot_id in bot_accounts:
                    bot_config['wallet_private_key'] = bot_accounts[bot_id]['private_key']
                    bot_config['wallet_address'] = bot_accounts[bot_id]['address']
        
        # Update victim trader configurations  
        if 'victims' in accounts:
            victim_traders = self.config['victim_transactions']['traders']
            victim_accounts = accounts['victims']
            
            victim_mapping = {
                'retail_alice': 'victim1',
                'whale_bob': 'victim2', 
                'dca_charlie': 'victim3',
                'arb_david': 'victim4',
                'panic_eve': 'victim5'
            }
            
            for trader_id, victim_config in victim_traders.items():
                mapped_id = victim_mapping.get(trader_id)
                if mapped_id and mapped_id in victim_accounts:
                    victim_config['wallet_private_key'] = victim_accounts[mapped_id]['private_key']
                    victim_config['wallet_address'] = victim_accounts[mapped_id]['address']
        
        logger.info("✅ Config updated with environment settings")
    
    async def deploy_contracts(self) -> None:
        """Deploy smart contracts to blockchain"""
        logger.info("🚀 Starting contract deployment...")
        
        deployer_key = os.environ.get('DEPLOYER_PRIVATE_KEY')
        if not deployer_key or deployer_key == "YOUR_DEPLOYER_PRIVATE_KEY":
            raise ValueError("DEPLOYER_PRIVATE_KEY not set or using placeholder value")
        
        with Timer("Contract deployment"):
            # Setup environment with existing contracts on Arc Testnet
            from src.deployment.deployer import ContractDeployer
            from src.utils.blockchain import connect_to_network
            
            # Connect to blockchain
            client = connect_to_network(self.config['network'])
            await client.connect()
            
            # Setup deployer and use existing contracts
            deployer = ContractDeployer(client, deployer_key)
            self.deployed_environment = await deployer.setup_complete_environment(
                self.config['network']
            )
        
        logger.info("✅ Contract deployment completed successfully")
        
        # Log deployment details
        tokens = self.deployed_environment['tokens']
        pools = self.deployed_environment['pools']
        
        logger.info(f"📝 Deployed Tokens:")
        for token_name, token_info in tokens.items():
            logger.info(f"   {token_name}: {token_info['address']}")
            
        logger.info(f"🏊‍♂️ Deployed Pools:")
        for pool_name, pool_info in pools.items():
            logger.info(f"   {pool_name}: {pool_info['address']}")
    
    async def run_simulation(self, duration_minutes: float = None, target_rounds: int = None) -> None:
        """Run the MEV simulation"""
        logger.info("🎮 Starting MEV simulation...")
        
        # Use config defaults if not specified
        if duration_minutes is None:
            duration_minutes = self.config['simulation'].get('duration_minutes', 5)
        if target_rounds is None:
            target_rounds = self.config['simulation'].get('target_transactions', 20)
        
        # Create simulator
        simulator = MEVSimulator(self.config)
        
        # Setup with real deployed contracts
        await simulator.setup()
        
        # If we have real deployed environment, connect it
        if self.deployed_environment and hasattr(simulator, 'pool_manager'):
            logger.info("🔗 Connecting deployed contracts to simulator...")
            
            # Update pool manager with real contract addresses
            # This would need more specific implementation based on your contract structure
            
        with Timer("MEV simulation"):
            self.simulation_results = await simulator.run_simulation(
                duration_minutes=duration_minutes,
                target_rounds=target_rounds
            )
        
        logger.info("✅ MEV simulation completed successfully")
        
        # Quick summary
        if self.simulation_results:
            logger.info(f"📊 Simulation Summary:")
            logger.info(f"   Total Rounds: {self.simulation_results.total_rounds}")
            logger.info(f"   MEV Profit: {format_currency(self.simulation_results.total_mev_profit)}")
            logger.info(f"   Victim Loss: {format_currency(self.simulation_results.total_victim_loss)}")
            logger.info(f"   Success Rate: {self.simulation_results.average_success_rate:.1%}")
    
    async def analyze_results(self) -> None:
        """Analyze simulation results"""
        logger.info("📊 Analyzing simulation results...")
        
        if not self.simulation_results or not self.simulation_results.rounds:
            logger.warning("No simulation data to analyze")
            return
        
        # Convert simulation results to DataFrame for analysis
        import pandas as pd
        
        analysis_data = []
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
                analysis_data.append(row)
        
        if not analysis_data:
            logger.warning("No attack data to analyze")
            return
        
        df = pd.DataFrame(analysis_data)
        
        # Run comprehensive analysis
        analyzer = MEVAnalyzer(df)
        
        with Timer("Result analysis"):
            # Run all analyses
            mev_analysis = analyzer.analyze_mev_performance()
            victim_analysis = analyzer.analyze_victim_impact()
            
            if 'total_latency_ms' in df.columns:
                latency_analysis = analyzer.analyze_latency_impact()
            
            statistical_tests = analyzer.run_statistical_tests()
            
            # Generate summary report
            summary_report = analyzer.generate_summary_report()
        
        logger.info("✅ Analysis completed successfully")
        
        # Export results
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        output_dir = Path(self.config['simulation']['output_dir']) / f"simulation_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Export CSV
        csv_file = output_dir / "mev_analysis.csv"
        analyzer.export_to_csv(str(csv_file))
        
        # Export summary
        summary_file = output_dir / "summary_report.json"
        import json
        with open(summary_file, 'w') as f:
            json.dump(summary_report, f, indent=2, default=str)
        
        logger.info(f"📁 Results exported to: {output_dir}")
        
        # Print key findings
        logger.info("🔍 Key Findings:")
        for finding in summary_report.get('key_findings', []):
            logger.info(f"   • {finding}")
    
    async def cleanup(self) -> None:
        """Cleanup resources"""
        logger.info("🧹 Cleaning up resources...")
        
        # Add any cleanup logic here (close connections, etc.)
        
        logger.info("✅ Cleanup completed")
    
    async def run_complete_simulation(self, 
                                    deploy_contracts: bool = True,
                                    duration_minutes: float = None,
                                    target_rounds: int = None) -> None:
        """Run the complete simulation pipeline"""
        try:
            logger.info("🎯 Starting Complete MEV Simulation Pipeline")
            logger.info(f"Environment: {self.environment}")
            
            # Load configurations
            self.load_configurations()
            self.setup_environment_variables()
            self.update_config_with_environment()
            
            # Deploy contracts if requested
            if deploy_contracts:
                await self.deploy_contracts()
            
            # Run simulation
            await self.run_simulation(duration_minutes, target_rounds)
            
            # Analyze results
            await self.analyze_results()
            
            logger.info("🎉 Complete MEV Simulation Pipeline finished successfully!")
            
        except Exception as e:
            logger.error(f"❌ Simulation pipeline failed: {e}")
            raise
        finally:
            await self.cleanup()


async def run_quick_test(environment: str = "development") -> None:
    """Run a quick test simulation"""
    logger.info("🚀 Running Quick Test Simulation")
    
    simulation = CompleteMEVSimulation(environment)
    await simulation.run_complete_simulation(
        deploy_contracts=True,
        duration_minutes=1,
        target_rounds=10
    )


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Complete MEV Simulation Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick test with local Anvil
  python scripts/run_complete_simulation.py --quick-test
  
  # Development environment (local Anvil)
  python scripts/run_complete_simulation.py --environment development
  
  # Arc Testnet with confirmation
  python scripts/run_complete_simulation.py --environment arc_testnet --confirm
  
  # Custom duration and rounds
  python scripts/run_complete_simulation.py --environment development --duration 10 --rounds 50
        """
    )
    
    # Environment selection
    parser.add_argument('--environment', '-e',
                       choices=['development', 'arc_testnet', 'production'],
                       default='development',
                       help='Environment to use (default: development)')
    
    parser.add_argument('--quick-test', '-q',
                       action='store_true',
                       help='Run quick test simulation')
    
    # Simulation parameters
    parser.add_argument('--duration', '-d',
                       type=float,
                       help='Simulation duration in minutes')
    
    parser.add_argument('--rounds', '-r',
                       type=int,
                       help='Target number of simulation rounds')
    
    parser.add_argument('--no-deploy',
                       action='store_true',
                       help='Skip contract deployment (use existing contracts)')
    
    # Safety and confirmation
    parser.add_argument('--confirm',
                       action='store_true',
                       help='Confirm before running (required for non-development environments)')
    
    # Output options
    parser.add_argument('--verbose', '-v',
                       action='store_true',
                       help='Enable verbose logging')
    
    args = args = parser.parse_args()
    
    # Setup logging
    log_level = 'DEBUG' if args.verbose else 'INFO'
    setup_logging(log_level)
    
    # Safety check for non-development environments
    if args.environment != 'development' and not args.confirm:
        print(f"❌ Environment '{args.environment}' requires --confirm flag for safety")
        print("This will use real blockchain resources and may cost money!")
        sys.exit(1)
    
    try:
        if args.quick_test:
            asyncio.run(run_quick_test(args.environment))
        else:
            simulation = CompleteMEVSimulation(args.environment)
            asyncio.run(simulation.run_complete_simulation(
                deploy_contracts=not args.no_deploy,
                duration_minutes=args.duration,
                target_rounds=args.rounds
            ))
            
    except KeyboardInterrupt:
        print(f"\n🛑 Simulation interrupted by user")
    except Exception as e:
        print(f"❌ Simulation failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
