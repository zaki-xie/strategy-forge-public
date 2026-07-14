from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.ws_manager import ws_manager

router = APIRouter(prefix="/ws", tags=["实时推送"])

@router.websocket("/subscribe/{event_type}")
async def websocket_subscribe(websocket: WebSocket, event_type: str):
    conn_id = await ws_manager.connect(event_type, websocket)
    try:
        while True:
            # 这里可以接收客户端消息，目前我们只做等待断开
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(event_type, conn_id)