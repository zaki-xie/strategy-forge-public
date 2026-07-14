import uuid
from typing import Dict
from fastapi import WebSocket

class WSManager:
    def __init__(self):
        # 存储结构：event_type -> {conn_id: WebSocket}
        self.connections: Dict[str, Dict[str, WebSocket]] = {}

    async def connect(self, event_type: str, websocket: WebSocket) -> str:
        """
        接受 WebSocket 连接，返回该连接的唯一 ID
        """
        await websocket.accept()
        conn_id = str(uuid.uuid4())[:8]  # 截短，便于日志显示
        self.connections.setdefault(event_type, {})[conn_id] = websocket
        print(f"WebSocket 连接: event={event_type}, id={conn_id}")
        return conn_id

    def disconnect(self, event_type: str, conn_id: str):
        if event_type in self.connections and conn_id in self.connections[event_type]:
            del self.connections[event_type][conn_id]
            print(f"WebSocket 断开: event={event_type}, id={conn_id}")
            if not self.connections[event_type]:
                del self.connections[event_type]

    async def broadcast(self, event_type: str, data: dict):
        """
        向所有订阅了 event_type 的客户端广播消息
        """
        if event_type not in self.connections:
            return
        message = {"event": event_type, "data": data}
        # 收集需要断开的连接
        closed = []
        for conn_id, ws in self.connections[event_type].items():
            try:
                await ws.send_json(message)
            except Exception:
                closed.append(conn_id)
        # 清理已断开的连接
        for conn_id in closed:
            self.disconnect(event_type, conn_id)

    async def close_all(self):
        """主动关闭所有连接"""
        for event_type, conns in self.connections.items():
            for ws in conns.values():
                try:
                    await ws.close()
                except Exception:
                    pass
        self.connections.clear()
        print("所有 WebSocket 连接已关闭")

# 全局单例
ws_manager = WSManager()