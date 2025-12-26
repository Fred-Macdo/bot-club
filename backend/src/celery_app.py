from celery import Celery
from .config import REDIS_URL

celery_app = Celery(
    "bot_club_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["src.services.tasks.trading_tasks"]
)

# Configure specialized queues
celery_app.conf.task_routes = {
    'src.services.tasks.trading_tasks.run_live_strategy': {'queue': 'live_trading'},
    'src.services.tasks.trading_tasks.run_paper_strategy': {'queue': 'paper_trading'},
    'src.services.tasks.trading_tasks.run_backtest_task': {'queue': 'backtesting'}
}

# Optional: Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    # Example: Check health of running strategies every minute
    # 'check-strategy-health': {
    #     'task': 'src.services.tasks.trading_tasks.check_strategy_health',
    #     'schedule': 60.0,  # seconds
    # },
}

celery_app.conf.timezone = 'UTC'
