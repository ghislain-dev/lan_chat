import json
import struct
import os
from enum import Enum
from dataclasses import dataclass, asdict
from typing import Optional, Any, Dict, List

class MessageType(Enum):
    LOGIN = "login"
    LOGIN_RESPONSE = "login_response"
    LOGOUT = "logout"
    USER_LIST = "user_list"
    USER_STATUS = "user_status"
    PRIVATE_MESSAGE = "private_message"
    GROUP_MESSAGE = "group_message"
    MESSAGE_RESPONSE = "message_response"
    CREATE_GROUP = "create_group"
    GROUP_CREATED = "group_created"
    GROUP_LIST = "group_list"
    ADD_TO_GROUP = "add_to_group"
    FILE_TRANSFER_REQUEST = "file_transfer_request"
    FILE_TRANSFER_ACCEPT = "file_transfer_accept"
    FILE_TRANSFER_REJECT = "file_transfer_reject"
    FILE_CHUNK = "file_chunk"
    FILE_TRANSFER_COMPLETE = "file_transfer_complete"
    HISTORY_REQUEST = "history_request"
    HISTORY_RESPONSE = "history_response"
    TYPING_NOTIFICATION = "typing_notification"
    MESSAGE_DELIVERED = "message_delivered"
    MESSAGE_READ = "message_read"
    ERROR = "error"
    PING = "ping"
    PONG = "pong"

@dataclass
class Message:
    type: MessageType
    sender: str
    recipient: Optional[str] = None
    content: Any = None
    timestamp: Optional[str] = None
    message_id: Optional[str] = None
    
    def to_json(self) -> bytes:
        data = {
            "type": self.type.value,
            "sender": self.sender,
            "recipient": self.recipient,
            "content": self.content,
            "timestamp": self.timestamp,
            "message_id": self.message_id
        }
        json_str = json.dumps(data, ensure_ascii=False)
        return json_str.encode('utf-8')
    
    @classmethod
    def from_json(cls, data: bytes):
        json_str = data.decode('utf-8')
        data_dict = json.loads(json_str)
        data_dict["type"] = MessageType(data_dict["type"])
        return cls(**data_dict)

class Protocol:
    HEADER_SIZE = 4
    
    @staticmethod
    def pack_message(message: Message) -> bytes:
        message_data = message.to_json()
        message_length = len(message_data)
        header = struct.pack('!I', message_length)
        return header + message_data
    
    @staticmethod
    def unpack_message(socket) -> Optional[Message]:
        try:
            header = socket.recv(Protocol.HEADER_SIZE)
            if not header:
                return None
            
            message_length = struct.unpack('!I', header)[0]
            
            message_data = b''
            remaining = message_length
            while remaining > 0:
                chunk = socket.recv(min(remaining, 4096))
                if not chunk:
                    return None
                message_data += chunk
                remaining -= len(chunk)
            
            return Message.from_json(message_data)
        except Exception as e:
            print(f"Erreur unpack_message: {e}")
            return None

@dataclass
class FileTransfer:
    file_id: str
    sender: str
    recipient: str
    filename: str
    filesize: int
    filepath: str
    chunk_size: int = 8192
    is_directory: bool = False
    total_chunks: int = 0
    chunks_received: int = 0