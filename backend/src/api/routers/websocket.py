from fastapi import APIRouter, WebSocket, Query
from services.utils.websocket_manager import websocket_manager

router = APIRouter()

@router.websocket("/ws/task/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str, last_id: str = Query(default="0")):
    await websocket_manager.handle_task_logs(websocket, task_id, last_id)
