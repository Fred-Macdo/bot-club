"""
WebSocket manager for streaming Celery task logs via Redis Streams.
Refactored to use FastAPI WebSockets instead of aiohttp.
"""
import asyncio
import json
import logging
from typing import Optional
from fastapi import WebSocket, WebSocketDisconnect, Query
from redis.asyncio import Redis
from config import REDIS_URL

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Manages WebSocket connections and streams logs from Redis Streams.
    Each WebSocket connection independently reads from its task's stream.
    """
    
    def __init__(self):
        # No need to track connections - each WebSocket endpoint handles its own
        # No shared Redis client - each connection gets its own
        # Simplified architecture: stateless manager
        pass
    
    async def handle_task_logs(
        self, 
        websocket: WebSocket, 
        task_id: str, 
        last_id: str = "0"
    ):
        """
        Handle WebSocket connection for a specific task's logs.
        Reads from Redis Stream and forwards to client with reconnection support.
        
        Args:
            websocket: FastAPI WebSocket connection
            task_id: Celery task ID
            last_id: Last message ID client received (for reconnection catch-up)
        """
        await websocket.accept()
        
        # Each connection gets its own Redis client
        redis = await Redis.from_url(REDIS_URL, decode_responses=True)
        stream_key = f"task:{task_id}:logs"
        
        logger.info(f"WebSocket connected: task={task_id}, last_id={last_id}")
        
        # Send welcome message
        await self._send_welcome(websocket, task_id)
        
        try:
            # Phase 1: Catch-up on missed messages (if reconnecting)
            if last_id != "0" and last_id != "$":
                await self._send_catchup_messages(
                    websocket, redis, stream_key, last_id
                )
            elif last_id == "0":
                # Client wants all historical messages
                await self._send_all_messages(
                    websocket, redis, stream_key
                )
            
            # Phase 2: Stream real-time messages
            await self._stream_realtime_messages(
                websocket, redis, stream_key
            )
            
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: task={task_id}")
        except Exception as e:
            logger.error(f"WebSocket error for task {task_id}: {e}", exc_info=True)
            try:
                await websocket.close(code=1011, reason=str(e))
            except:
                pass
        finally:
            await redis.close()
            logger.info(f"Redis connection closed for task={task_id}")
    
    async def _send_welcome(self, websocket: WebSocket, task_id: str):
        """Send welcome message to confirm connection."""
        try:
            welcome = {
                "type": "connection",
                "data": {
                    "message": f"Connected to task stream: {task_id}",
                    "task_id": task_id,
                    "timestamp": asyncio.get_event_loop().time() * 1000
                }
            }
            await websocket.send_json(welcome)
        except Exception as e:
            logger.error(f"Error sending welcome message: {e}")
    
    async def _send_catchup_messages(
        self, 
        websocket: WebSocket, 
        redis: Redis, 
        stream_key: str, 
        last_id: str
    ):
        """
        Send messages client missed during disconnection.
        Reads from Redis Stream starting after last_id.
        """
        logger.info(f"Sending catch-up messages after {last_id} from {stream_key}")
        
        try:
            # Read up to 100 missed messages
            messages = await redis.xread(
                {stream_key: last_id}, 
                count=100, 
                block=0  # Don't block, return immediately
            )
            
            if messages:
                stream_name, msg_list = messages[0]
                logger.info(f"Sending {len(msg_list)} catch-up messages")
                
                for msg_id, data in msg_list:
                    await websocket.send_json({
                        "id": msg_id,
                        "type": data.get("type", "log"),
                        "data": data
                    })
            else:
                logger.info("No catch-up messages to send")
                
        except Exception as e:
            logger.error(f"Error sending catch-up messages: {e}", exc_info=True)
    
    async def _send_all_messages(
        self, 
        websocket: WebSocket, 
        redis: Redis, 
        stream_key: str
    ):
        """
        Send all messages from stream beginning.
        Used when client connects for first time (last_id="0").
        """
        logger.info(f"Sending all historical messages from {stream_key}")
        
        try:
            # Read from beginning, up to 100 messages
            messages = await redis.xread(
                {stream_key: "0"}, 
                count=100, 
                block=0
            )
            
            if messages:
                stream_name, msg_list = messages[0]
                logger.info(f"Sending {len(msg_list)} historical messages")
                
                for msg_id, data in msg_list:
                    await websocket.send_json({
                        "id": msg_id,
                        "type": data.get("type", "log"),
                        "data": data
                    })
            else:
                logger.info("No historical messages in stream")
                
        except Exception as e:
            logger.error(f"Error sending historical messages: {e}", exc_info=True)
    
    async def _stream_realtime_messages(
        self, 
        websocket: WebSocket, 
        redis: Redis, 
        stream_key: str
    ):
        """
        Stream new messages as they arrive in Redis Stream.
        Uses blocking XREAD to efficiently wait for new messages.
        """
        # Start reading only new messages ($ means "from now on")
        last_id = "$"
        logger.info(f"Starting real-time stream for {stream_key}")
        
        while True:
            try:
                # Block for up to 5 seconds waiting for new messages
                messages = await redis.xread(
                    {stream_key: last_id},
                    count=10,  # Read up to 10 messages at a time
                    block=5000  # 5 second timeout
                )
                
                if messages:
                    stream_name, msg_list = messages[0]
                    logger.debug(f"Received {len(msg_list)} new messages")
                    
                    for msg_id, data in msg_list:
                        # Forward to WebSocket client
                        await websocket.send_json({
                            "id": msg_id,
                            "type": data.get("type", "log"),
                            "data": data
                        })
                        
                        # Update last_id for next read
                        last_id = msg_id
                else:
                    # No messages received, send heartbeat to keep connection alive
                    await self._send_heartbeat(websocket)
                    
            except asyncio.CancelledError:
                logger.info("Stream task cancelled")
                break
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected during streaming")
                break
            except Exception as e:
                logger.error(f"Error in real-time streaming: {e}", exc_info=True)
                # Wait a bit before retrying
                await asyncio.sleep(1)
    
    async def _send_heartbeat(self, websocket: WebSocket):
        """Send heartbeat to keep connection alive during idle periods."""
        try:
            await websocket.send_json({
                "type": "heartbeat",
                "data": {
                    "timestamp": asyncio.get_event_loop().time() * 1000
                }
            })
        except Exception as e:
            logger.debug(f"Error sending heartbeat: {e}")


# Singleton instance
websocket_manager = WebSocketManager()


