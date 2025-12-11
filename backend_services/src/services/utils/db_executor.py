import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Callable, Any

# A thread pool to run synchronous database operations without blocking the event loop
executor = ThreadPoolExecutor(max_workers=20)

async def run_db_operation(sync_function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """
    Runs a synchronous (blocking) database function in a separate thread
    to avoid blocking the main asyncio event loop.
    
    Args:
        sync_function: The synchronous PyMongo method to run (e.g., db.collection.find_one).
        *args: Positional arguments to pass to the function.
        **kwargs: Keyword arguments to pass to the function.
        
    Returns:
        The result of the synchronous function.
    """
    loop = asyncio.get_running_loop()
    
    # Use functools.partial to include args and kwargs
    func_with_args = partial(sync_function, *args, **kwargs)
    
    # run_in_executor returns a future, which we can await
    return await loop.run_in_executor(executor, func_with_args)

