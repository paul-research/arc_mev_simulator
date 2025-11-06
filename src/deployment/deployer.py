"""
Smart Contract Deployment System

Handles compilation and deployment of MEV simulation contracts.
"""

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import logging
from web3 import Web3
from web3.contract import Contract
from eth_account import Account
import solcx
from solcx import compile_source, compile_files, install_solc
import time
import math

from ..utils.blockchain import BlockchainClient
from ..utils.helpers import retry_with_backoff
from .uniswap_v3_abis import (
    UNISWAP_V3_FACTORY_ABI, UNISWAP_V3_POOL_ABI, POSITION_MANAGER_ABI,
    SWAP_ROUTER_ABI, QUOTER_V2_ABI, ERC20_ABI
)

logger = logging.getLogger(__name__)


class ContractCompiler:
    """Solidity contract compiler"""
    
    def __init__(self, solc_version: str = "0.8.19"):
        self.solc_version = solc_version
        self.contracts_dir = Path(__file__).parent / "contracts"
        
        # Install solc if not available
        try:
            install_solc(solc_version)
            solcx.set_solc_version(solc_version)
            logger.info(f"Using Solidity compiler version {solc_version}")
        except Exception as e:
            logger.warning(f"Failed to install solc {solc_version}: {e}")
    
    def compile_contract(self, contract_name: str) -> Dict[str, Any]:
        """
        Compile a single contract
        
        Args:
            contract_name: Name of the contract file (without .sol extension)
            
        Returns:
            Compilation result with bytecode and ABI
        """
        contract_file = self.contracts_dir / f"{contract_name}.sol"
        
        if not contract_file.exists():
            raise FileNotFoundError(f"Contract file not found: {contract_file}")
        
        logger.info(f"Compiling contract: {contract_name}")
        
        try:
            # Compile contract
            compiled = compile_files([str(contract_file)], output_values=['abi', 'bin'])
            
            # Extract contract info (handle different key formats)
            for key in compiled.keys():
                if contract_name in key:
                    contract_data = compiled[key]
                    return {
                        'abi': contract_data['abi'],
                        'bytecode': contract_data['bin'],
                        'contract_name': contract_name
                    }
            
            raise ValueError(f"Contract {contract_name} not found in compilation output")
            
        except Exception as e:
            logger.error(f"Failed to compile {contract_name}: {e}")
            raise
    
    def compile_all_contracts(self) -> Dict[str, Dict[str, Any]]:
        """Compile all contracts in the contracts directory"""
        contracts = {}
        
        for contract_file in self.contracts_dir.glob("*.sol"):
            contract_name = contract_file.stem
            try:
                contracts[contract_name] = self.compile_contract(contract_name)
                logger.info(f"✅ Compiled {contract_name}")
            except Exception as e:
                logger.error(f"❌ Failed to compile {contract_name}: {e}")
        
        return contracts


class ContractDeployer:
    """Smart contract deployment system"""
    
    def __init__(self, 
                 blockchain_client: BlockchainClient,
                 deployer_private_key: str):
        """
        Initialize deployer
        
        Args:
            blockchain_client: Connected blockchain client
            deployer_private_key: Private key for deployment account
        """
        self.client = blockchain_client
        self.w3 = blockchain_client.w3
        
        # Setup deployer account
        self.deployer_account = Account.from_key(deployer_private_key)
        self.deployer_address = self.deployer_account.address
        
        # Contract compiler
        self.compiler = ContractCompiler()
        
        # Deployed contracts registry
        self.deployed_contracts: Dict[str, Dict[str, Any]] = {}
        
        logger.info(f"Initialized deployer with account: {self.deployer_address}")
    
    async def check_deployer_balance(self) -> float:
        """Check deployer account balance"""
        balance_wei = await self.client.get_balance(self.deployer_address)
        balance_eth = balance_wei / 1e18
        
        logger.info(f"Deployer balance: {balance_eth:.6f} ETH")
        return balance_eth
    
    async def deploy_contract(self, 
                            contract_name: str,
                            constructor_args: List[Any] = None,
                            gas_limit: int = 3000000) -> Contract:
        """
        Deploy a smart contract
        
        Args:
            contract_name: Name of the contract to deploy
            constructor_args: Arguments for contract constructor
            gas_limit: Gas limit for deployment
            
        Returns:
            Deployed contract instance
        """
        constructor_args = constructor_args or []
        
        logger.info(f"Deploying contract: {contract_name}")
        
        # Compile contract
        contract_data = self.compiler.compile_contract(contract_name)
        
        # Create contract factory
        contract_factory = self.w3.eth.contract(
            abi=contract_data['abi'],
            bytecode=contract_data['bytecode']
        )
        
        # Get current nonce and gas price
        nonce = await self.client.get_nonce(self.deployer_address)
        gas_info = await self.client.estimate_gas_price()
        
        # Build deployment transaction
        transaction = contract_factory.constructor(*constructor_args).build_transaction({
            'from': self.deployer_address,
            'nonce': nonce,
            'gas': gas_limit,
            'gasPrice': gas_info['gas_price']
        })
        
        # Sign and send transaction
        signed_txn = self.w3.eth.account.sign_transaction(transaction, self.deployer_account.key)
        # Handle different web3.py versions
        raw_tx = getattr(signed_txn, 'rawTransaction', None) or getattr(signed_txn, 'raw_transaction', signed_txn)
        tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
        
        logger.info(f"Deployment tx sent: {tx_hash.hex()}")
        
        # Wait for transaction receipt
        tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        
        if tx_receipt.status == 0:
            raise Exception(f"Contract deployment failed: {tx_hash.hex()}")
        
        # Create contract instance
        contract = self.w3.eth.contract(
            address=tx_receipt.contractAddress,
            abi=contract_data['abi']
        )
        
        # Store deployment info
        self.deployed_contracts[contract_name] = {
            'address': tx_receipt.contractAddress,
            'abi': contract_data['abi'],
            'tx_hash': tx_hash.hex(),
            'gas_used': tx_receipt.gasUsed,
            'constructor_args': constructor_args,
            'contract': contract
        }
        
        logger.info(f"✅ {contract_name} deployed at: {tx_receipt.contractAddress}")
        logger.info(f"Gas used: {tx_receipt.gasUsed:,}")
        
        return contract
    
    async def deploy_erc20_token(self, 
                               name: str,
                               symbol: str,
                               decimals: int = 18,
                               total_supply: int = 1000000) -> Contract:
        """Deploy an ERC20 token"""
        return await self.deploy_contract(
            'ERC20Token',
            [name, symbol, decimals, total_supply]
        )
    
    async def create_uniswap_v3_pool(self, 
                                     token0_address: str, 
                                     token1_address: str,
                                     fee: int = 3000,
                                     initial_price_ratio: float = 2.0) -> Contract:
        """Create Uniswap V3 pool using Factory"""
        # Get factory contract
        factory_address = "0x1F98431c8aD98523631AE4a59f267346ea31F984"
        factory = self.w3.eth.contract(
            address=factory_address,
            abi=UNISWAP_V3_FACTORY_ABI
        )
        
        # Check if pool already exists
        existing_pool = factory.functions.getPool(token0_address, token1_address, fee).call()
        
        if existing_pool != "0x0000000000000000000000000000000000000000":
            logger.info(f"Pool already exists at: {existing_pool}")
            pool_contract = self.w3.eth.contract(
                address=existing_pool,
                abi=UNISWAP_V3_POOL_ABI
            )
        else:
            # Create new pool
            logger.info(f"Creating Uniswap V3 pool for {token0_address}/{token1_address}")
            
            nonce = await self.client.get_nonce(self.deployer_address)
            gas_info = await self.client.estimate_gas_price()
            
            # Create pool transaction
            create_tx = factory.functions.createPool(
                token0_address, token1_address, fee
            ).build_transaction({
                'from': self.deployer_address,
                'nonce': nonce,
                'gas': 3000000,
                'gasPrice': gas_info['gas_price']
            })
            
            # Sign and send
            signed_txn = self.w3.eth.account.sign_transaction(create_tx, self.deployer_account.key)
            raw_tx = getattr(signed_txn, 'rawTransaction', None) or getattr(signed_txn, 'raw_transaction', signed_txn)
            tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
            
            logger.info(f"Pool creation tx sent: {tx_hash.hex()}")
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt.status == 0:
                raise Exception(f"Pool creation failed: {tx_hash.hex()}")
            
            # Get the pool address
            pool_address = factory.functions.getPool(token0_address, token1_address, fee).call()
            pool_contract = self.w3.eth.contract(
                address=pool_address,
                abi=UNISWAP_V3_POOL_ABI
            )
            
            logger.info(f"✅ Uniswap V3 pool created at: {pool_address}")
        
        # Initialize pool if not initialized
        try:
            slot0 = pool_contract.functions.slot0().call()
            if slot0[0] == 0:  # sqrtPriceX96 is 0, pool not initialized
                await self._initialize_pool(pool_contract, initial_price_ratio)
        except Exception as e:
            logger.warning(f"Could not check pool initialization: {e}")
            # Try to initialize anyway
            await self._initialize_pool(pool_contract, initial_price_ratio)
        
        return pool_contract
    
    async def _initialize_pool(self, pool_contract: Contract, price_ratio: float):
        """Initialize Uniswap V3 pool with initial price"""
        # Calculate sqrtPriceX96 from price ratio
        # price_ratio is token1/token0 (how many token1 per token0)
        sqrt_price = math.sqrt(price_ratio)
        sqrt_price_x96 = int(sqrt_price * (2 ** 96))
        
        logger.info(f"Initializing pool with price ratio {price_ratio} (sqrtPriceX96: {sqrt_price_x96})")
        
        nonce = await self.client.get_nonce(self.deployer_address)
        gas_info = await self.client.estimate_gas_price()
        
        # Initialize pool
        init_tx = pool_contract.functions.initialize(sqrt_price_x96).build_transaction({
            'from': self.deployer_address,
            'nonce': nonce,
            'gas': 500000,
            'gasPrice': gas_info['gas_price']
        })
        
        signed_txn = self.w3.eth.account.sign_transaction(init_tx, self.deployer_account.key)
        raw_tx = getattr(signed_txn, 'rawTransaction', None) or getattr(signed_txn, 'raw_transaction', signed_txn)
        tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
        
        logger.info(f"Pool initialization tx sent: {tx_hash.hex()}")
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        
        if receipt.status == 0:
            raise Exception(f"Pool initialization failed: {tx_hash.hex()}")
            
        logger.info("✅ Pool initialized successfully")
    
    async def setup_complete_environment(self, 
                                       network_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Setup MEV simulation environment using existing contracts on Arc Testnet
        
        Args:
            network_config: Network configuration with contract addresses
        
        Returns:
            Dictionary with all contract addresses and instances
        """
        logger.info("🚀 Setting up MEV simulation environment with existing contracts...")
        
        # Use provided network config or fallback
        if network_config is None:
            # Default Arc Testnet addresses
            network_config = {
                'contracts': {
                    'paul_king_token': "0x6911406ae5C9fa9314B4AEc086304c001fb3b656",
                    'paul_queen_token': "0x3eaE1139A9A19517B0dB5696073d957542886BF8",
                    'wusdc_native': "0x3600000000000000000000000000000000000000",
                    'swap_router': "0xe372f58a9e03c7b56b3ea9a2a08f18767b75ca67",
                    'uniswap_pool': "0x39A9Ba5F012aB6D6fc90E563C72bD85949Ca0FF6"
                }
            }
        
        contracts = network_config.get('contracts', {})
        
        # Check balance
        balance = await self.check_deployer_balance()
        logger.info(f"Deployer balance: {balance:.6f} USDC")
        
        # Connect to existing tokens
        logger.info("📝 Connecting to existing tokens...")
        
        paul_king_addr = contracts.get('paul_king_token')
        paul_queen_addr = contracts.get('paul_queen_token')
        
        if not paul_king_addr or not paul_queen_addr:
            raise ValueError("Missing token addresses in network config")
        
        # Create contract instances for existing tokens
        paul_king = self.w3.eth.contract(
            address=paul_king_addr,
            abi=ERC20_ABI
        )
        paul_queen = self.w3.eth.contract(
            address=paul_queen_addr,
            abi=ERC20_ABI
        )
        
        logger.info(f"✅ Connected to PaulKing token: {paul_king_addr}")
        logger.info(f"✅ Connected to PaulQueen token: {paul_queen_addr}")
        
        # Connect to existing pool
        logger.info("🏊‍♂️ Connecting to existing Uniswap pool...")
        pool_addr = contracts.get('uniswap_pool')
        
        if pool_addr:
            # Connect to Uniswap V3 Pool
            try:
                v3_pool = self.w3.eth.contract(
                    address=pool_addr,
                    abi=UNISWAP_V3_POOL_ABI
                )
                # Verify it's a V3 pool by calling slot0
                slot0 = v3_pool.functions.slot0().call()
                logger.info(f"Connected to Uniswap V3 pool: {pool_addr}")
                
            except Exception as e:
                logger.error(f"Failed to connect to Uniswap V3 pool: {e}")
                v3_pool = None
        else:
            logger.warning("No pool address provided")
            v3_pool = None
        
        # Get swap router
        router_addr = contracts.get('swap_router', contracts.get('uniswap_v3_router'))
        
        # Prepare return data
        environment = {
            'tokens': {
                'paul_king': {
                    'address': paul_king_addr,
                    'contract': paul_king
                },
                'paul_queen': {
                    'address': paul_queen_addr,
                    'contract': paul_queen
                }
            },
            'pools': {
                'pking_pqueen': {
                    'address': pool_addr if pool_addr else "0x0000000000000000000000000000000000000000",
                    'contract': v3_pool,
                    'token0': paul_king_addr,
                    'token1': paul_queen_addr,
                    'fee': 3000
                }
            },
            'uniswap_contracts': {
                'factory': contracts.get('uniswap_v3_factory', "0x1F98431c8aD98523631AE4a59f267346ea31F984"),
                'router': router_addr or "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
                'position_manager': contracts.get('position_manager', "0xC36442b4c4e76c8f7a04B0eE0d2C2d4C6e5e4F2D"),
                'quoter_v2': contracts.get('quoter_v2', "0x61fFE014bA17989E743c5F6cB21bF9697530B21e")
            },
            'deployer': self.deployer_address
        }
        
        logger.info("✅ MEV simulation environment ready with existing contracts!")
        return environment
    
    async def _setup_uniswap_v3_liquidity(self, token0: Contract, token1: Contract, pool: Contract):
        """Setup initial liquidity in Uniswap V3 pool"""
        logger.info("💧 Setting up Uniswap V3 liquidity...")
        
        # Define liquidity amounts
        amount0 = 1000 * (10 ** 18)  # 1000 tokens
        amount1 = 2000 * (10 ** 18)  # 2000 tokens (1:2 ratio)
        
        # Get Position Manager contract
        position_manager_address = "0xC36442b4c4e76c8f7a04B0eE0d2C2d4C6e5e4F2D"
        position_manager = self.w3.eth.contract(
            address=position_manager_address,
            abi=POSITION_MANAGER_ABI
        )
        
        try:
            # Get pool info
            token0_addr = pool.functions.token0().call()
            token1_addr = pool.functions.token1().call()
            fee = pool.functions.fee().call()
            
            # Determine which token is which
            if token0.address.lower() == token0_addr.lower():
                token0_contract, token1_contract = token0, token1
                amount0_desired, amount1_desired = amount0, amount1
            else:
                token0_contract, token1_contract = token1, token0
                amount0_desired, amount1_desired = amount1, amount0
            
            # Get gas info and nonce
            gas_info = await self.client.estimate_gas_price()
            nonce = await self.client.get_nonce(self.deployer_address)
            
            # Approve tokens for Position Manager
            logger.info("Approving tokens for Position Manager...")
            
            # Approve token0
            approve_tx0 = token0_contract.functions.approve(
                position_manager_address, amount0_desired
            ).build_transaction({
                'from': self.deployer_address,
                'nonce': nonce,
                'gas': 100000,
                'gasPrice': gas_info['gas_price']
            })
            signed_tx0 = self.w3.eth.account.sign_transaction(approve_tx0, self.deployer_account.key)
            raw_tx0 = getattr(signed_tx0, 'rawTransaction', None) or getattr(signed_tx0, 'raw_transaction', signed_tx0)
            tx_hash0 = self.w3.eth.send_raw_transaction(raw_tx0)
            self.w3.eth.wait_for_transaction_receipt(tx_hash0)
            
            # Approve token1
            nonce += 1
            approve_tx1 = token1_contract.functions.approve(
                position_manager_address, amount1_desired
            ).build_transaction({
                'from': self.deployer_address,
                'nonce': nonce,
                'gas': 100000,
                'gasPrice': gas_info['gas_price']
            })
            signed_tx1 = self.w3.eth.account.sign_transaction(approve_tx1, self.deployer_account.key)
            raw_tx1 = getattr(signed_tx1, 'rawTransaction', None) or getattr(signed_tx1, 'raw_transaction', signed_tx1)
            tx_hash1 = self.w3.eth.send_raw_transaction(raw_tx1)
            self.w3.eth.wait_for_transaction_receipt(tx_hash1)
            
            # Add liquidity using Position Manager
            # Full range: tick -887220 to 887220 (approximately)
            nonce += 1
            deadline = int(time.time()) + 300  # 5 minutes from now
            
            mint_params = (
                token0_addr,      # token0
                token1_addr,      # token1
                fee,              # fee
                -887220,          # tickLower (full range)
                887220,           # tickUpper (full range)
                amount0_desired,  # amount0Desired
                amount1_desired,  # amount1Desired
                0,                # amount0Min (no slippage protection for initial)
                0,                # amount1Min (no slippage protection for initial)
                self.deployer_address,  # recipient
                deadline          # deadline
            )
            
            mint_tx = position_manager.functions.mint(mint_params).build_transaction({
                'from': self.deployer_address,
                'nonce': nonce,
                'gas': 500000,
                'gasPrice': gas_info['gas_price']
            })
            
            signed_mint_tx = self.w3.eth.account.sign_transaction(mint_tx, self.deployer_account.key)
            raw_mint_tx = getattr(signed_mint_tx, 'rawTransaction', None) or getattr(signed_mint_tx, 'raw_transaction', signed_mint_tx)
            mint_tx_hash = self.w3.eth.send_raw_transaction(raw_mint_tx)
            mint_receipt = self.w3.eth.wait_for_transaction_receipt(mint_tx_hash)
            
            if mint_receipt.status == 0:
                raise Exception(f"Liquidity mint failed: {mint_tx_hash.hex()}")
            
            logger.info(f"✅ Uniswap V3 liquidity added: {amount0_desired/1e18} + {amount1_desired/1e18}")
            logger.info(f"NFT Position created: {mint_tx_hash.hex()}")
            
        except Exception as e:
            logger.error(f"Failed to setup Uniswap V3 liquidity: {e}")
            # Continue without initial liquidity
    
    def get_contract_addresses(self) -> Dict[str, str]:
        """Get all deployed contract addresses"""
        addresses = {}
        for name, info in self.deployed_contracts.items():
            addresses[name] = info['address']
        return addresses
    
    def export_deployment_info(self, output_file: str) -> None:
        """Export deployment information to JSON file"""
        deployment_info = {
            'deployer_address': self.deployer_address,
            'network': {
                'rpc_url': self.client.rpc_url,
                'chain_id': self.client.chain_id
            },
            'contracts': {}
        }
        
        for name, info in self.deployed_contracts.items():
            deployment_info['contracts'][name] = {
                'address': info['address'],
                'tx_hash': info['tx_hash'],
                'gas_used': info['gas_used'],
                'constructor_args': info['constructor_args']
            }
        
        with open(output_file, 'w') as f:
            json.dump(deployment_info, f, indent=2)
        
        logger.info(f"Deployment info exported to: {output_file}")


# Factory function
async def deploy_mev_environment(network_config: Dict[str, Any], 
                               deployer_private_key: str) -> Dict[str, Any]:
    """
    Deploy complete MEV simulation environment
    
    Args:
        network_config: Network configuration
        deployer_private_key: Private key for deployment
        
    Returns:
        Deployed environment information
    """
    from ..utils.blockchain import connect_to_network
    
    # Connect to blockchain
    client = connect_to_network(network_config)
    connected = await client.connect()
    
    if not connected:
        raise ConnectionError("Failed to connect to blockchain")
    
    # Deploy contracts
    deployer = ContractDeployer(client, deployer_private_key)
    environment = await deployer.setup_complete_environment()
    
    # Export deployment info
    timestamp = int(time.time())
    output_file = f"data/deployments/deployment_{timestamp}.json"
    deployer.export_deployment_info(output_file)
    
    return environment


# Example usage and testing
if __name__ == "__main__":
    import asyncio
    
    async def test_deployment():
        """Test contract deployment"""
        print("🧪 Testing Contract Deployment")
        
        # Mock network config for testing
        network_config = {
            'rpc_url': 'http://127.0.0.1:8545',
            'chain_id': 31337
        }
        
        # Use test private key (never use in production!)
        test_private_key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
        
        try:
            environment = await deploy_mev_environment(network_config, test_private_key)
            
            print("✅ Environment deployed successfully!")
            print(f"Tokens: {list(environment['tokens'].keys())}")
            print(f"Pools: {list(environment['pools'].keys())}")
            
        except Exception as e:
            print(f"❌ Deployment failed: {e}")
            import traceback
            traceback.print_exc()
    
    # Run test
    asyncio.run(test_deployment())
