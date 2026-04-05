import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pydantic")

from celery import Celery
from .config import REDIS_URL

celery_app = Celery(
    "bot_club_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "src.tasks.trading_tasks",
        "src.tasks.backtest_task"
    ]
)

# Configure specialized queues
celery_app.conf.task_routes = {
    'src.tasks.trading_tasks.run_live_strategy': {'queue': 'live_trading'},
    'src.tasks.trading_tasks.run_paper_strategy': {'queue': 'paper_trading'},
    'src.tasks.backtest_task.run_backtest_task': {'queue': 'backtesting'},
    'src.tasks.trading_tasks.stop_live_strategy': {'queue': 'control'}
}

# RedBeat: dynamic Beat schedules stored in Redis
celery_app.conf.redbeat_redis_url = REDIS_URL
celery_app.conf.beat_scheduler = 'redbeat.RedBeatScheduler'

# Optional: Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    # Example: Check health of running strategies every minute
    # 'check-strategy-health': {
    #     'task': 'services.tasks.trading_tasks.check_strategy_health',
    #     'schedule': 60.0,  # seconds
    # },
}

celery_app.conf.timezone = 'US/Eastern'
