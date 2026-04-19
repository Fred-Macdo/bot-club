"""
WebSocket manager for streaming Celery task logs via Redis Streams.
Refactored to use FastAPI WebSockets instead of aiohttp.
"""

import asyncio
import json
import logging
from typing import Optional
from fastapi import WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from redis.asyncio import Redis
from ..config import REDIS_URL

logger = logging.getLogger(__name__)


def verify_ws_token(token: str) -> Optional[str]:
    """Verify JWT token from WebSocket query param. Returns user_id or None."""
    import os

    secret = os.getenv("JWT_SECRET_KEY")
    if not secret:
        return None
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return payload.get("sub")
    except JWTError:
        return None


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

    async def connect(self, websocket: WebSocket, task_id: str, last_id: str = "0"):
        """Accept WebSocket connection with optional token authentication."""
        # Extract token from query params for auth
        token = websocket.query_params.get("token")
        if token:
            user_id = verify_ws_token(token)
            if not user_id:
                await websocket.close(code=4001, reason="Invalid token")
                return
        else:
            # Allow unauthenticated in dev; log warning
            logger.warning(f"WebSocket connection without token for task={task_id}")

        await self.handle_task_logs(websocket, task_id, last_id=last_id)

    async def handle_task_logs(
        self, websocket: WebSocket, task_id: str, last_id: str = "0"
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
        # FIX: remove :logs suffix to match trading_tasks.py
        stream_key = f"task:{task_id}"

        logger.info(f"WebSocket connected: task={task_id}, last_id={last_id}")

        # Send welcome message
        await self._send_welcome(websocket, task_id)

        try:
            # Phase 1: Catch-up on missed messages (if reconnecting)
            resume_id = "$"
            if last_id != "0" and last_id != "$":
                resume_id = await self._send_catchup_messages(
                    websocket, redis, stream_key, last_id
                )
            elif last_id == "0":
                # Client wants all historical messages
                resume_id = await self._send_all_messages(websocket, redis, stream_key)

            # Phase 2: Stream real-time messages from where history left off
            await self._stream_realtime_messages(
                websocket, redis, stream_key, resume_id
            )

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: task={task_id}")
        except Exception as e:
            logger.error(f"WebSocket error for task {task_id}: {e}", exc_info=True)
            try:
                await websocket.close(code=1011, reason=str(e))
            except Exception:
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
                    "timestamp": asyncio.get_event_loop().time() * 1000,
                },
            }
            await websocket.send_json(welcome)
        except Exception as e:
            logger.error(f"Error sending welcome message: {e}")

    async def _send_redis_message(self, websocket: WebSocket, msg_id: str, data: dict):
        """Helper to parse and send a Redis message to WebSocket"""
        try:
            # Parse the inner JSON data if it exists (from trading_tasks.py)
            payload_data = data
            if "data_json" in data:
                try:
                    payload_data = json.loads(data["data_json"])
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse data_json: {data['data_json']}")
                    payload_data = data  # Fallback

            await websocket.send_json(
                {"id": msg_id, "type": data.get("type", "log"), "data": payload_data}
            )
        except Exception as e:
            logger.error(f"Error sending parsed message: {e}")

    async def _send_catchup_messages(
        self, websocket: WebSocket, redis: Redis, stream_key: str, last_id: str
    ) -> str:
        """
        Send messages client missed during disconnection.
        Reads from Redis Stream starting after last_id.
        Returns the last message ID sent (for seamless real-time resume).
        """
        logger.info(f"Sending catch-up messages after {last_id} from {stream_key}")
        cursor = last_id
        total_sent = 0

        try:
            while True:
                messages = await redis.xread(
                    {stream_key: cursor},
                    count=200,
                    block=0,  # Don't block, return immediately
                )

                if not messages:
                    break

                stream_name, msg_list = messages[0]
                if not msg_list:
                    break

                for msg_id, data in msg_list:
                    await self._send_redis_message(websocket, msg_id, data)
                    cursor = msg_id

                total_sent += len(msg_list)

                # If we got fewer than requested, we've reached the end
                if len(msg_list) < 200:
                    break

            logger.info(f"Sent {total_sent} catch-up messages")

        except Exception as e:
            logger.error(f"Error sending catch-up messages: {e}", exc_info=True)

        return cursor

    async def _send_all_messages(
        self, websocket: WebSocket, redis: Redis, stream_key: str
    ) -> str:
        """
        Send all messages from stream beginning.
        Used when client connects for first time (last_id="0").
        Paginates through the entire stream.
        Returns the last message ID sent (for seamless real-time resume).
        """
        logger.info(f"Sending all historical messages from {stream_key}")
        cursor = "0"
        total_sent = 0

        try:
            while True:
                messages = await redis.xread({stream_key: cursor}, count=200, block=0)

                if not messages:
                    break

                stream_name, msg_list = messages[0]
                if not msg_list:
                    break

                for msg_id, data in msg_list:
                    await self._send_redis_message(websocket, msg_id, data)
                    cursor = msg_id

                total_sent += len(msg_list)

                # If we got fewer than requested, we've reached the end
                if len(msg_list) < 200:
                    break

            logger.info(f"Sent {total_sent} historical messages")

        except Exception as e:
            logger.error(f"Error sending historical messages: {e}", exc_info=True)

        return cursor

    async def _stream_realtime_messages(
        self,
        websocket: WebSocket,
        redis: Redis,
        stream_key: str,
        resume_from: str = "$",
    ):
        """
        Stream new messages as they arrive in Redis Stream.
        Uses blocking XREAD to efficiently wait for new messages.

        Args:
            resume_from: last message ID already sent to the client.
                         Defaults to "$" (only new messages) when no history was sent.
        """
        last_id = resume_from
        logger.info(f"Starting real-time stream for {stream_key} from {last_id}")

        while True:
            try:
                # Block for up to 5 seconds waiting for new messages
                messages = await redis.xread(
                    {stream_key: last_id},
                    count=10,  # Read up to 10 messages at a time
                    block=5000,  # 5 second timeout
                )

                if messages:
                    stream_name, msg_list = messages[0]
                    # logger.debug(f"Received {len(msg_list)} new messages")

                    for msg_id, data in msg_list:
                        await self._send_redis_message(websocket, msg_id, data)

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
            await websocket.send_json(
                {
                    "type": "heartbeat",
                    "data": {"timestamp": asyncio.get_event_loop().time() * 1000},
                }
            )
        except Exception as e:
            logger.debug(f"Error sending heartbeat: {e}")


# Singleton instance
websocket_manager = WebSocketManager()
