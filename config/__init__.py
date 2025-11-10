"""
Configuration management for MEV-Simulator
"""

import yaml
import os
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class NetworkConfig:
    """Network configuration dataclass"""
    name: str
    rpc_url: str
    chain_id: int
    block_time_ms: int
    native_token: str
    native_token_address: str
    gas: Dict[str, Any]
    contracts: Dict[str, Optional[str]]
    mev: Dict[str, Any]


@dataclass 
class BotProfile:
    """MEV bot profile configuration"""
    name: str
    strategy: str
    wallet_private_key: str
    initial_balance_eth: float
    latency: Dict[str, float]
    strategy_params: Dict[str, Any]


class ConfigManager:
    """Centralized configuration management"""
    
    def __init__(self, config_dir: str = None):
        if config_dir is None:
            config_dir = Path(__file__).parent
        self.config_dir = Path(config_dir)
        
        self._main_config = None
        self._networks_config = None
        
    def load_config(self) -> Dict[str, Any]:
        """Load main configuration file"""
        if self._main_config is None:
            config_path = self.config_dir / "config.yaml"
            with open(config_path, 'r') as f:
                self._main_config = yaml.safe_load(f)
                
        return self._main_config
    
    def load_networks(self) -> Dict[str, Any]:
        """Load networks configuration file"""
        if self._networks_config is None:
            networks_path = self.config_dir / "networks.yaml"
            with open(networks_path, 'r') as f:
                self._networks_config = yaml.safe_load(f)
                
        return self._networks_config
    
    def get_network_config(self, network_name: str = None) -> NetworkConfig:
        """Get specific network configuration"""
        networks = self.load_networks()
        
        if network_name is None:
            network_name = networks.get('default_network', 'arc_testnet')
            
        network_data = networks['networks'][network_name]
        return NetworkConfig(**network_data)
    
    def get_bot_profiles(self) -> Dict[str, BotProfile]:
        """Get all MEV bot profiles"""
        config = self.load_config()
        profiles = {}
        
        for bot_id, bot_data in config['mev_bots']['profiles'].items():
            profiles[bot_id] = BotProfile(**bot_data)
            
        return profiles
    
    def get_pool_config(self) -> Dict[str, Any]:
        """Get pool configuration"""
        config = self.load_config()
        return config['pools']
    
    def get_simulation_config(self) -> Dict[str, Any]:
        """Get simulation configuration"""
        config = self.load_config()
        return config['simulation']
    
    def expand_env_vars(self, text: str) -> str:
        """Expand environment variables in configuration strings"""
        import re
        
        def replace_env_var(match):
            var_name = match.group(1)
            return os.getenv(var_name, match.group(0))
        
        return re.sub(r'\$\{([^}]+)\}', replace_env_var, text)
    
    def validate_config(self) -> bool:
        """Validate configuration completeness"""
        try:
            config = self.load_config()
            networks = self.load_networks()
            
            # Check required sections
            required_sections = ['simulation', 'network', 'mev_bots', 'pools']
            for section in required_sections:
                if section not in config:
                    raise ValueError(f"Missing required config section: {section}")
            
            # Check bot profiles
            bot_count = config['mev_bots']['count']
            profiles = config['mev_bots']['profiles']
            
            if len(profiles) != bot_count:
                raise ValueError(f"Bot count mismatch: expected {bot_count}, got {len(profiles)}")
                
            # Check network configuration
            network_name = config['network']['name']
            if network_name not in networks['networks']:
                raise ValueError(f"Unknown network: {network_name}")
            
            return True
            
        except Exception as e:
            print(f"Configuration validation failed: {e}")
            return False


# Global config manager instance
config_manager = ConfigManager()

# Convenience functions
def load_config() -> Dict[str, Any]:
    """Load main configuration"""
    return config_manager.load_config()

def get_network_config(network_name: str = None) -> NetworkConfig:
    """Get network configuration"""
    return config_manager.get_network_config(network_name)

def get_bot_profiles() -> Dict[str, BotProfile]:
    """Get bot profiles"""
    return config_manager.get_bot_profiles()

def validate_config() -> bool:
    """Validate configuration"""
    return config_manager.validate_config()

__all__ = [
    'ConfigManager',
    'NetworkConfig', 
    'BotProfile',
    'config_manager',
    'load_config',
    'get_network_config',
    'get_bot_profiles', 
    'validate_config'
]


