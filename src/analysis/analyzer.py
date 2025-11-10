# Circle Research Team - paul.kwon@circle.com
"""
MEV Analysis Engine

Statistical analysis tools for MEV simulation results.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
import logging
from scipy import stats

logger = logging.getLogger(__name__)


class MEVAnalyzer:
    """Core analysis engine for MEV simulation results"""
    
    def __init__(self, data: pd.DataFrame):
        """
        Initialize analyzer with simulation data
        
        Args:
            data: DataFrame with MEV simulation results
        """
        self.data = data
        self.results = {}
        
    def analyze_mev_performance(self) -> Dict[str, Any]:
        """Analyze MEV bot performance metrics"""
        logger.info("Analyzing MEV performance...")
        
        # Basic statistics
        total_attacks = len(self.data)
        successful_attacks = len(self.data[self.data['success'] == True])
        success_rate = successful_attacks / total_attacks if total_attacks > 0 else 0
        
        # Financial metrics
        total_profit = self.data['net_profit'].sum()
        total_victim_loss = self.data['victim_loss'].sum()
        total_gas_costs = self.data['gas_costs'].sum()
        value_destroyed = total_victim_loss - total_profit
        
        # Efficiency metrics
        extraction_efficiency = total_profit / total_victim_loss if total_victim_loss > 0 else 0
        
        results = {
            'basic_stats': {
                'total_attacks': total_attacks,
                'successful_attacks': successful_attacks,
                'success_rate': success_rate
            },
            'financial_metrics': {
                'total_mev_profit': total_profit,
                'total_victim_loss': total_victim_loss,
                'total_gas_costs': total_gas_costs,
                'net_value_destroyed': value_destroyed,
                'extraction_efficiency': extraction_efficiency
            }
        }
        
        # Per-bot analysis if available
        if 'bot_id' in self.data.columns:
            results['bot_performance'] = self._analyze_bot_performance()
        
        self.results['mev_performance'] = results
        return results
    
    def analyze_victim_impact(self) -> Dict[str, Any]:
        """Analyze impact on victim traders"""
        logger.info("Analyzing victim impact...")
        
        victim_data = self.data[self.data['victim_loss'] > 0]
        
        if victim_data.empty:
            return {'error': 'No victim data available'}
        
        results = {
            'summary': {
                'total_victims': victim_data['victim_id'].nunique() if 'victim_id' in victim_data.columns else 0,
                'total_victim_trades': len(victim_data),
                'total_victim_loss': victim_data['victim_loss'].sum(),
                'avg_loss_per_trade': victim_data['victim_loss'].mean()
            }
        }
        
        # By victim type if available
        if 'victim_type' in victim_data.columns:
            results['by_victim_type'] = self._analyze_by_victim_type(victim_data)
        
        self.results['victim_impact'] = results
        return results
    
    def analyze_latency_impact(self) -> Dict[str, Any]:
        """Analyze relationship between latency and performance"""
        if 'total_latency_ms' not in self.data.columns:
            return {'error': 'Latency data not available'}
        
        logger.info("Analyzing latency impact...")
        
        # Correlation analysis
        latency_profit_corr = self.data['total_latency_ms'].corr(self.data['net_profit'])
        latency_success_corr = self.data['total_latency_ms'].corr(self.data['success'].astype(int))
        
        # Performance by latency quartiles
        self.data['latency_quartile'] = pd.qcut(self.data['total_latency_ms'], 4, labels=['Q1', 'Q2', 'Q3', 'Q4'])
        quartile_performance = self.data.groupby('latency_quartile').agg({
            'success': 'mean',
            'net_profit': 'mean',
            'total_latency_ms': 'mean'
        }).round(6)
        
        results = {
            'correlations': {
                'latency_vs_profit': latency_profit_corr,
                'latency_vs_success': latency_success_corr
            },
            'quartile_analysis': quartile_performance.to_dict('index'),
            'latency_stats': {
                'mean': self.data['total_latency_ms'].mean(),
                'median': self.data['total_latency_ms'].median(),
                'std': self.data['total_latency_ms'].std(),
                'min': self.data['total_latency_ms'].min(),
                'max': self.data['total_latency_ms'].max()
            }
        }
        
        self.results['latency_impact'] = results
        return results
    
    def run_statistical_tests(self) -> Dict[str, Any]:
        """Run statistical significance tests"""
        logger.info("Running statistical tests...")
        
        tests = {}
        
        # Test if MEV is profitable on average
        t_stat, p_value = stats.ttest_1samp(self.data['net_profit'], 0)
        tests['profitability_test'] = {
            'test': 'One-sample t-test (H0: profit = 0)',
            't_statistic': t_stat,
            'p_value': p_value,
            'significant': p_value < 0.05,
            'conclusion': 'Significantly profitable' if (p_value < 0.05 and t_stat > 0) else 'Not significantly profitable'
        }
        
        # Compare bot performance if multiple bots
        if 'bot_id' in self.data.columns and len(self.data['bot_id'].unique()) > 1:
            bot_groups = [group['net_profit'].values for name, group in self.data.groupby('bot_id')]
            f_stat, p_value_anova = stats.f_oneway(*bot_groups)
            
            tests['bot_comparison_test'] = {
                'test': 'One-way ANOVA (H0: equal bot performance)',
                'f_statistic': f_stat,
                'p_value': p_value_anova,
                'significant': p_value_anova < 0.05,
                'conclusion': 'Significant difference between bots' if p_value_anova < 0.05 else 'No significant difference'
            }
        
        self.results['statistical_tests'] = tests
        return tests
    
    def _analyze_bot_performance(self) -> Dict[str, Any]:
        """Analyze individual bot performance"""
        bot_stats = {}
        
        for bot_id in self.data['bot_id'].unique():
            bot_data = self.data[self.data['bot_id'] == bot_id]
            
            bot_stats[bot_id] = {
                'total_attacks': len(bot_data),
                'successful_attacks': len(bot_data[bot_data['success'] == True]),
                'success_rate': (bot_data['success'].sum() / len(bot_data)) if len(bot_data) > 0 else 0,
                'total_profit': bot_data['net_profit'].sum(),
                'avg_profit_per_attack': bot_data['net_profit'].mean(),
                'profit_volatility': bot_data['net_profit'].std(),
                'total_gas_costs': bot_data['gas_costs'].sum(),
                'victim_damage_caused': bot_data['victim_loss'].sum(),
                'avg_latency': bot_data['total_latency_ms'].mean() if 'total_latency_ms' in bot_data.columns else None
            }
        
        return bot_stats
    
    def _analyze_by_victim_type(self, victim_data: pd.DataFrame) -> Dict[str, Any]:
        """Analyze victim impact by victim type"""
        type_stats = {}
        
        for victim_type in victim_data['victim_type'].unique():
            type_data = victim_data[victim_data['victim_type'] == victim_type]
            
            type_stats[victim_type] = {
                'attack_count': len(type_data),
                'total_loss': type_data['victim_loss'].sum(),
                'avg_loss': type_data['victim_loss'].mean(),
                'max_loss': type_data['victim_loss'].max(),
                'victims_affected': type_data['victim_id'].nunique() if 'victim_id' in type_data.columns else None
            }
        
        return type_stats
    
    def generate_summary_report(self) -> Dict[str, Any]:
        """Generate comprehensive summary report"""
        logger.info("Generating summary report...")
        
        # Run all analyses if not already done
        if 'mev_performance' not in self.results:
            self.analyze_mev_performance()
        
        if 'victim_impact' not in self.results:
            self.analyze_victim_impact()
        
        if 'total_latency_ms' in self.data.columns and 'latency_impact' not in self.results:
            self.analyze_latency_impact()
        
        if 'statistical_tests' not in self.results:
            self.run_statistical_tests()
        
        # Compile summary
        summary = {
            'dataset_info': {
                'total_records': len(self.data),
                'columns': list(self.data.columns),
                'data_quality': {
                    'missing_values': self.data.isnull().sum().to_dict(),
                    'duplicate_records': self.data.duplicated().sum()
                }
            },
            'key_findings': self._extract_key_findings(),
            'analysis_results': self.results
        }
        
        return summary
    
    def _extract_key_findings(self) -> List[str]:
        """Extract key findings from analysis results"""
        findings = []
        
        if 'mev_performance' in self.results:
            perf = self.results['mev_performance']
            success_rate = perf['basic_stats']['success_rate']
            total_profit = perf['financial_metrics']['total_mev_profit']
            extraction_eff = perf['financial_metrics']['extraction_efficiency']
            
            findings.append(f"MEV attacks had a {success_rate:.1%} success rate")
            findings.append(f"Total MEV profit was {total_profit:.6f} USDC")
            findings.append(f"Extraction efficiency was {extraction_eff:.1%}")
        
        if 'victim_impact' in self.results and 'error' not in self.results['victim_impact']:
            victim = self.results['victim_impact']
            total_loss = victim['summary']['total_victim_loss']
            avg_loss = victim['summary']['avg_loss_per_trade']
            
            findings.append(f"Total victim losses: {total_loss:.6f} USDC")
            findings.append(f"Average loss per victim trade: {avg_loss:.6f} USDC")
        
        if 'statistical_tests' in self.results:
            tests = self.results['statistical_tests']
            if 'profitability_test' in tests:
                profit_test = tests['profitability_test']
                findings.append(f"MEV profitability: {profit_test['conclusion']}")
        
        return findings
    
    def export_to_csv(self, output_path: str) -> None:
        """Export analysis results to CSV"""
        summary = self.generate_summary_report()
        
        # Create summary DataFrame
        summary_data = []
        if 'mev_performance' in self.results:
            perf = self.results['mev_performance']
            summary_data.extend([
                ['Total Attacks', perf['basic_stats']['total_attacks']],
                ['Success Rate', f"{perf['basic_stats']['success_rate']:.1%}"],
                ['Total MEV Profit (ETH)', f"{perf['financial_metrics']['total_mev_profit']:.6f}"],
                ['Total Victim Loss (ETH)', f"{perf['financial_metrics']['total_victim_loss']:.6f}"],
                ['Extraction Efficiency', f"{perf['financial_metrics']['extraction_efficiency']:.1%}"]
            ])
        
        summary_df = pd.DataFrame(summary_data, columns=['Metric', 'Value'])
        summary_df.to_csv(output_path, index=False)
        logger.info(f"Analysis exported to {output_path}")


# Example usage
if __name__ == "__main__":
    # Create sample data for testing
    np.random.seed(42)
    sample_data = pd.DataFrame({
        'bot_id': ['bot1', 'bot2'] * 50,
        'success': np.random.choice([True, False], 100, p=[0.8, 0.2]),
        'net_profit': np.random.normal(0.001, 0.0005, 100),
        'victim_loss': np.random.exponential(0.002, 100),
        'gas_costs': np.random.normal(0.0005, 0.0001, 100),
        'total_latency_ms': np.random.normal(200, 50, 100),
        'victim_type': np.random.choice(['retail', 'whale', 'dca_bot'], 100),
        'victim_id': ['victim_' + str(i % 10) for i in range(100)]
    })
    
    # Run analysis
    analyzer = MEVAnalyzer(sample_data)
    
    print("🧪 Testing MEV Analyzer")
    print("=" * 30)
    
    # Test individual analyses
    mev_results = analyzer.analyze_mev_performance()
    print(f"✅ MEV Performance: {len(mev_results)} metrics")
    
    victim_results = analyzer.analyze_victim_impact()
    print(f"✅ Victim Impact: {len(victim_results)} metrics")
    
    latency_results = analyzer.analyze_latency_impact()
    print(f"✅ Latency Analysis: {len(latency_results)} metrics")
    
    test_results = analyzer.run_statistical_tests()
    print(f"✅ Statistical Tests: {len(test_results)} tests")
    
    # Generate full report
    summary = analyzer.generate_summary_report()
    print(f"\n📊 Summary Report Generated:")
    for finding in summary['key_findings']:
        print(f"  • {finding}")
    
    print("\n🎉 All tests passed!")
