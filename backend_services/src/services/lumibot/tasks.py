from celery import Celery
from typing import Dict, Any
from models.backtest import BacktestParams

# Import the function that does the actual work
from .lumibot_stock_strategy import run_strategy as run_lumibot_strategy

# Define the Celery app instance
# The first argument is the name of the current module.
# 'broker' is the URL to your Redis server.
# 'backend' is also Redis, used to store results.
celery_app = Celery(
    'tasks',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0'
)

# Tell Celery how to handle Pydantic models
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],  # Ignore other content
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

@celery_app.task
def run_backtest_task(strategy_config: Dict[str, Any], api_keys: Dict[str, Any], backtest_params_dict: Dict[str, Any]):
    """
    Celery task wrapper for running the Lumibot backtest.
    We pass dictionaries instead of Pydantic models because it's more reliable for serialization.
    """
    try:
        # Re-create the Pydantic model from the dictionary inside the task
        backtest_params = BacktestParams(**backtest_params_dict)
        
        # Call the original function
        # Note: run_lumibot_strategy doesn't return anything, it runs the backtest.
        # For a real result, you'd modify run_strategy to return a results dictionary.
        run_lumibot_strategy(
            strategy_config=strategy_config,
            api_keys=api_keys,
            mode='backtest',
            backtest_params=backtest_params
        )
        # Let's assume for now it returns a success message.
        # In a real scenario, you'd save results to a file/db and return the path or ID.
        return {"status": "Completed Successfully", "parameters": backtest_params_dict}
    except Exception as e:
        # Log the exception and return an error state
        # You can use Celery's logging for this
        print(f"Backtest failed: {e}")
        return {"status": "Failed", "error": str(e)}
