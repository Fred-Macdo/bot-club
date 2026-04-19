import asyncio
import yaml
import os
import sys
import argparse
from pathlib import Path
from pymongo import AsyncMongoClient
from datetime import datetime, timezone

# Import the strategy models - adjust path for Docker environment
try:
    from src.models.strategy import StrategyCreate, StrategyConfig, Condition, Indicator, RiskManagement
    from src.utils.mongo_helpers import PyObjectId
except ImportError:
    # Fallback for different path structures
    sys.path.append('/app/backend/src')
    from .src.models.strategy import StrategyCreate, StrategyConfig, Condition, Indicator, RiskManagement
    from .src.utils.mongo_helpers import PyObjectId

def parse_yaml_to_strategy(yaml_data: dict) -> StrategyCreate:
    """Parse YAML data into a StrategyCreate model with proper validation"""
    
    # Parse indicators
    indicators = []
    for indicator_data in yaml_data.get('indicators', []):
        indicators.append(Indicator(
            name=indicator_data['name'],
            params=indicator_data.get('params', {})
        ))
    
    # Parse entry conditions
    entry_conditions = []
    for condition_data in yaml_data.get('entry_conditions', []):
        entry_conditions.append(Condition(
            indicator=condition_data['indicator'],
            comparison=condition_data['comparison'],
            value=condition_data['value']
        ))
    
    # Parse exit conditions
    exit_conditions = []
    for condition_data in yaml_data.get('exit_conditions', []):
        exit_conditions.append(Condition(
            indicator=condition_data['indicator'],
            comparison=condition_data['comparison'],
            value=condition_data['value']
        ))
    
    # Parse risk management
    risk_mgmt_data = yaml_data.get('risk_management', {})
    risk_management = RiskManagement(
        position_sizing_method=risk_mgmt_data.get('position_sizing_method', 'risk_based'),
        risk_per_trade=risk_mgmt_data.get('risk_per_trade', 0.02),
        stop_loss=risk_mgmt_data.get('stop_loss', 0.05),
        take_profit=risk_mgmt_data.get('take_profit', 0.10),
        max_position_size=risk_mgmt_data.get('max_position_size', 10000.0),
        atr_multiplier=risk_mgmt_data.get('atr_multiplier', 2.0)
    )
    
    # Create strategy config
    config = StrategyConfig(
        symbols=yaml_data.get('symbols', []),
        timeframe=yaml_data.get('timeframe', '1d'),
        start_date=yaml_data.get('start_date', '2024-01-01'),
        end_date=yaml_data.get('end_date', '2024-12-31'),
        entry_conditions=entry_conditions,
        exit_conditions=exit_conditions,
        risk_management=risk_management,
        indicators=indicators
    )
    
    # Create and return the strategy
    return StrategyCreate(
        name=yaml_data['name'],
        description=yaml_data.get('description', ''),
        config=config
    )

async def load_default_data(yaml_dir: str, db_uri: str, db_name: str):
    """Load default strategies from YAML files into MongoDB"""
    print(f"Connecting to MongoDB at: {db_uri}")
    print(f"Database: {db_name}")
    print(f"YAML directory: {yaml_dir}")
    
    client = AsyncMongoClient(db_uri)
    db = client[db_name]
    
    try:
        # Clear existing default strategies
        delete_result = await db.default_strategies.delete_many({})
        print(f"Cleared {delete_result.deleted_count} existing default strategies")
        
        # Get the data directory path
        data_dir = Path(yaml_dir)
        
        if not data_dir.exists():
            print(f"Error: Directory {data_dir} does not exist")
            return 0
        
        # Find all YAML files in the directory
        yaml_files = [f for f in os.listdir(data_dir) if f.endswith(('.yaml', '.yml'))]
        
        if not yaml_files:
            print(f"No YAML files found in {data_dir}")
            return 0
        
        print(f"Found {len(yaml_files)} YAML files: {yaml_files}")
        
        loaded_count = 0
        for filename in yaml_files:
            yaml_path = data_dir / filename
            try:
                print(f"Processing {filename}...")
                
                with open(yaml_path, 'r', encoding='utf-8') as file:
                    strategy_data = yaml.safe_load(file)
                
                if not strategy_data or 'name' not in strategy_data:
                    print(f"Warning: Invalid strategy data in {filename}, skipping")
                    continue
                
                # Parse and validate using Pydantic models
                strategy = parse_yaml_to_strategy(strategy_data)
                
                # Create the default strategy document
                default_strategy_doc = {
                    "_id": PyObjectId(),
                    "name": strategy.name,
                    "description": strategy.description,
                    "yaml_config": strategy_data,  # Keep original YAML for reference
                    "strategy_config": strategy.config.dict(),  # Validated config
                    "created_at": datetime.now(tz=timezone.utc),
                    "updated_at": datetime.now(tz=timezone.utc)
                }
                
                result = await db.default_strategies.insert_one(default_strategy_doc)
                print(f"✓ Loaded strategy: '{strategy.name}' with ID: {result.inserted_id}")
                loaded_count += 1
                
            except Exception as e:
                print(f"✗ Error loading {filename}: {e}")
                continue
        
        print(f"\nSuccessfully loaded {loaded_count} default strategies into database")
        return loaded_count
        
    except Exception as e:
        print(f"Database operation failed: {e}")
        raise
    finally:
        client.close()

def main():
    """Main function with argument parsing"""
    parser = argparse.ArgumentParser(description='Load default strategy YAML files into MongoDB')
    parser.add_argument(
        '--yaml-dir', 
        type=str, 
        default='/app/backend/data/strategy_examples/',
        help='Directory containing YAML strategy files (default: /app/backend/data/strategy_examples)'
    )
    parser.add_argument(
        '--db-uri', 
        type=str, 
        default='mongodb://mongo:27017',
        help='MongoDB connection URI (default: mongodb://mongo:27017)'
    )
    parser.add_argument(
        '--db-name', 
        type=str, 
        default='bot_club_db',
        help='Database name (default: bot_club_db)'
    )
    parser.add_argument(
        '--verbose', 
        action='store_true',
        help='Enable verbose output'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        print("Arguments:")
        print(f"  YAML Directory: {args.yaml_dir}")
        print(f"  Database URI: {args.db_uri}")
        print(f"  Database Name: {args.db_name}")
        print()
    
    try:
        loaded_count = asyncio.run(load_default_data(args.yaml_dir, args.db_uri, args.db_name))
        
        if loaded_count > 0:
            print(f"\n🎉 Successfully loaded {loaded_count} strategies!")
            sys.exit(0)
        else:
            print("\n⚠️  No strategies were loaded")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ Failed to load default data: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()