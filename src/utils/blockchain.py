"""
Blockchain interaction utilities for MEV-Simulator

Provides common blockchain operations and Web3 integrations.
"""

import asyncio
import time
import logging
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import TransactionNotFound, BlockNotFound
from eth_account import Account
from .helpers import retry_with_backoff, exponential_backoff, Timer

logger = logging.getLogger(__name__)


@dataclass
class BlockInfo:
    """Block information data structure"""
    number: int
    hash: str
    timestamp: int
    gas_limit: int
    gas_used: int
    base_fee_per_gas: Optional[int]
    transaction_count: int
    

@dataclass
class TransactionInfo:
    """Transaction information data structure"""
    hash: str
    block_number: int
    from_address: str
    to_address: Optional[str]
    value: int
    gas: int
    gas_price: int
    gas_used: Optional[int]
    status: Optional[int]
    

class BlockchainClient:
    """Enhanced Web3 client with MEV-specific utilities"""
    
    def __init__(self, 
                 rpc_url: str,
                 chain_id: int,
                 timeout: int = 30):
        """
        Initialize blockchain client
        
        Args:
            rpc_url: RPC endpoint URL
            chain_id: Blockchain chain ID
            timeout: Request timeout in seconds
        """
        self.rpc_url = rpc_url
        self.chain_id = chain_id
        self.timeout = timeout
        
        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': timeout}))
        
        # Connection state
        self.is_connected = False
        self._last_block = 0
        
        # Performance tracking
        self.call_count = 0
        self.total_response_time = 0.0
        
        logger.info(f"Initialized blockchain client: {rpc_url}")
    
    async def connect(self) -> bool:
        """
        Connect to blockchain and verify connection
        
        Returns:
            True if connection successful
        """
        try:
            with Timer("Blockchain connection"):
                # Test connection
                latest_block = await self.get_latest_block_number()
                
                if latest_block > 0:
                    self.is_connected = True
                    self._last_block = latest_block
                    logger.info(f"✅ Connected to blockchain at block {latest_block}")
                    return True
                else:
                    logger.error("❌ Failed to get latest block")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Blockchain connection failed: {e}")
            return False
    
    async def get_latest_block_number(self) -> int:
        """Get latest block number with retry logic"""
        try:
            start_time = time.time()
            block_number = self.w3.eth.block_number
            
            # Track performance
            self.call_count += 1
            self.total_response_time += (time.time() - start_time)
            
            return block_number
            
        except Exception as e:
            logger.warning(f"Failed to get latest block: {e}")
            raise
    
    async def get_block_info(self, block_number: Union[int, str] = 'latest') -> Optional[BlockInfo]:
        """
        Get detailed block information
        
        Args:
            block_number: Block number or 'latest'
            
        Returns:
            BlockInfo object or None if not found
        """
        try:
            block = self.w3.eth.get_block(block_number, full_transactions=False)
            
            return BlockInfo(
                number=block.number,
                hash=block.hash.hex(),
                timestamp=block.timestamp,
                gas_limit=block.gasLimit,
                gas_used=block.gasUsed,
                base_fee_per_gas=getattr(block, 'baseFeePerGas', None),
                transaction_count=len(block.transactions)
            )
            
        except BlockNotFound:
            logger.warning(f"Block not found: {block_number}")
            return None
        except Exception as e:
            logger.error(f"Failed to get block info for {block_number}: {e}")
            return None
    
    async def get_transaction_info(self, tx_hash: str) -> Optional[TransactionInfo]:
        """
        Get detailed transaction information
        
        Args:
            tx_hash: Transaction hash
            
        Returns:
            TransactionInfo object or None if not found
        """
        try:
            # Get transaction
            tx = self.w3.eth.get_transaction(tx_hash)
            
            # Get receipt for status and gas used
            try:
                receipt = self.w3.eth.get_transaction_receipt(tx_hash)
                status = receipt.status
                gas_used = receipt.gasUsed
            except TransactionNotFound:
                status = None
                gas_used = None
            
            return TransactionInfo(
                hash=tx.hash.hex(),
                block_number=tx.blockNumber or 0,
                from_address=tx['from'],
                to_address=tx.to,
                value=tx.value,
                gas=tx.gas,
                gas_price=tx.gasPrice,
                gas_used=gas_used,
                status=status
            )
            
        except TransactionNotFound:
            logger.warning(f"Transaction not found: {tx_hash}")
            return None
        except Exception as e:
            logger.error(f"Failed to get transaction info for {tx_hash}: {e}")
            return None
    
    async def estimate_gas_price(self) -> Dict[str, int]:
        """
        Estimate current gas prices
        
        Returns:
            Dictionary with gas price information
        """
        try:
            gas_price = self.w3.eth.gas_price
            
            # Try to get fee history for EIP-1559 networks
            try:
                fee_history = self.w3.eth.fee_history(1, 'latest', [50])
                base_fee = fee_history['baseFeePerGas'][0]
                max_priority_fee = int(fee_history['reward'][0][0])
                
                return {
                    'gas_price': gas_price,
                    'base_fee': base_fee,
                    'max_priority_fee': max_priority_fee,
                    'max_fee': base_fee + max_priority_fee
                }
                
            except Exception:
                # Fallback for non-EIP-1559 networks
                return {
                    'gas_price': gas_price,
                    'base_fee': 0,
                    'max_priority_fee': 0,
                    'max_fee': gas_price
                }
                
        except Exception as e:
            logger.error(f"Failed to estimate gas price: {e}")
            return {
                'gas_price': 20000000000,  # 20 gwei default
                'base_fee': 0,
                'max_priority_fee': 0,
                'max_fee': 20000000000
            }
    
    async def wait_for_transaction(self, 
                                 tx_hash: str, 
                                 timeout: int = 120,
                                 poll_interval: float = 2.0) -> Optional[TransactionInfo]:
        """
        Wait for transaction to be mined
        
        Args:
            tx_hash: Transaction hash to wait for
            timeout: Maximum wait time in seconds
            poll_interval: Polling interval in seconds
            
        Returns:
            TransactionInfo when mined, None if timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                tx_info = await self.get_transaction_info(tx_hash)
                
                if tx_info and tx_info.status is not None:
                    logger.info(f"Transaction {tx_hash[:10]}... mined in block {tx_info.block_number}")
                    return tx_info
                
            except Exception as e:
                logger.warning(f"Error checking transaction {tx_hash}: {e}")
            
            await asyncio.sleep(poll_interval)
        
        logger.warning(f"Transaction {tx_hash} timed out after {timeout} seconds")
        return None
    
    async def get_balance(self, address: str, block: str = 'latest') -> int:
        """
        Get account balance in Wei
        
        Args:
            address: Account address
            block: Block number or 'latest'
            
        Returns:
            Balance in Wei
        """
        try:
            return self.w3.eth.get_balance(address, block)
        except Exception as e:
            logger.error(f"Failed to get balance for {address}: {e}")
            return 0
    
    async def get_nonce(self, address: str) -> int:
        """
        Get current nonce for address
        
        Args:
            address: Account address
            
        Returns:
            Current nonce
        """
        try:
            return self.w3.eth.get_transaction_count(address)
        except Exception as e:
            logger.error(f"Failed to get nonce for {address}: {e}")
            return 0
    
    def create_account(self) -> tuple:
        """
        Create new random account
        
        Returns:
            Tuple of (private_key, address)
        """
        account = Account.create()
        return account.private_key.hex(), account.address
    
    def get_contract(self, address: str, abi: List[Dict]) -> Contract:
        """
        Get contract instance
        
        Args:
            address: Contract address
            abi: Contract ABI
            
        Returns:
            Web3 Contract instance
        """
        return self.w3.eth.contract(
            address=Web3.to_checksum_address(address),
            abi=abi
        )
    
    async def call_contract_function(self, 
                                   contract: Contract,
                                   function_name: str,
                                   *args,
                                   block: str = 'latest') -> Any:
        """
        Call read-only contract function
        
        Args:
            contract: Contract instance
            function_name: Function name to call
            *args: Function arguments
            block: Block number or 'latest'
            
        Returns:
            Function result
        """
        try:
            function = getattr(contract.functions, function_name)
            return function(*args).call(block_identifier=block)
            
        except Exception as e:
            logger.error(f"Failed to call {function_name}: {e}")
            raise
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get client performance statistics"""
        avg_response_time = (self.total_response_time / self.call_count 
                           if self.call_count > 0 else 0)
        
        return {
            'connected': self.is_connected,
            'rpc_url': self.rpc_url,
            'chain_id': self.chain_id,
            'last_block': self._last_block,
            'total_calls': self.call_count,
            'avg_response_time_ms': avg_response_time * 1000,
            'calls_per_minute': self.call_count / (self.total_response_time / 60) if self.total_response_time > 0 else 0
        }
    
    async def monitor_new_blocks(self, callback, poll_interval: float = 1.0):
        """
        Monitor for new blocks and call callback
        
        Args:
            callback: Function to call with new block info
            poll_interval: Polling interval in seconds
        """
        logger.info("🔍 Starting block monitoring...")
        
        last_block = await self.get_latest_block_number()
        
        while True:
            try:
                current_block = await self.get_latest_block_number()
                
                if current_block > last_block:
                    # New block(s) detected
                    for block_num in range(last_block + 1, current_block + 1):
                        block_info = await self.get_block_info(block_num)
                        if block_info:
                            await callback(block_info)
                    
                    last_block = current_block
                
            except Exception as e:
                logger.error(f"Block monitoring error: {e}")
            
            await asyncio.sleep(poll_interval)


def connect_to_network(network_config: Dict[str, Any]) -> BlockchainClient:
    """
    Create blockchain client from network configuration
    
    Args:
        network_config: Network configuration dictionary
        
    Returns:
        Configured BlockchainClient
    """
    client = BlockchainClient(
        rpc_url=network_config['rpc_url'],
        chain_id=network_config['chain_id'],
        timeout=network_config.get('timeout', 30)
    )
    
    return client


async def get_block_info(client: BlockchainClient, 
                        block_number: Union[int, str] = 'latest') -> Optional[BlockInfo]:
    """Convenience function to get block info"""
    return await client.get_block_info(block_number)


async def estimate_gas_price(client: BlockchainClient) -> Dict[str, int]:
    """Convenience function to estimate gas price"""
    return await client.estimate_gas_price()


async def wait_for_transaction(client: BlockchainClient, 
                             tx_hash: str, 
                             timeout: int = 120) -> Optional[TransactionInfo]:
    """Convenience function to wait for transaction"""
    return await client.wait_for_transaction(tx_hash, timeout)


# Example usage and testing
if __name__ == "__main__":
    async def test_blockchain_client():
        """Test blockchain client functionality"""
        print("🌐 Testing Blockchain Client")
        
        # Test with local Anvil node
        client = BlockchainClient(
            rpc_url="http://127.0.0.1:8545",
            chain_id=31337
        )
        
        try:
            # Test connection
            connected = await client.connect()
            print(f"Connected: {connected}")
            
            if connected:
                # Test block info
                block_info = await client.get_block_info()
                print(f"Latest block: {block_info.number}")
                
                # Test gas price
                gas_info = await client.estimate_gas_price()
                print(f"Gas price: {gas_info['gas_price']} wei")
                
                # Test account creation
                private_key, address = client.create_account()
                print(f"New account: {address}")
                
                # Test balance
                balance = await client.get_balance(address)
                print(f"Balance: {balance} wei")
                
                # Show performance stats
                stats = client.get_performance_stats()
                print(f"Performance: {stats['total_calls']} calls, "
                      f"{stats['avg_response_time_ms']:.1f}ms avg")
        
        except Exception as e:
            print(f"❌ Test failed: {e}")
    
    # Run test
    asyncio.run(test_blockchain_client())
