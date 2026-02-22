import json
import struct
import os
from enum import Enum
from dataclasses import dataclass, asdict
from typing import Optional, Any, Dict, List

class MessageType(Enum):
    # Authentification
    LOGIN = "login"
    LOGIN_RESPONSE = "login_response"
    LOGOUT = "logout"
    
    # Utilisateurs
    USER_LIST = "user_list"
    USER_STATUS = "user_status"
    
    # Messages
    PRIVATE_MESSAGE = "private_message"
    GROUP_MESSAGE = "group_message"
    MESSAGE_RESPONSE = "message_response"
    
    # Groupes
    CREATE_GROUP = "create_group"
    GROUP_CREATED = "group_created"
    GROUP_LIST = "group_list"
    ADD_TO_GROUP = "add_to_group"
    
    # Fichiers
    FILE_TRANSFER_REQUEST = "file_transfer_request"
    FILE_TRANSFER_ACCEPT = "file_transfer_accept"
    FILE_TRANSFER_REJECT = "file_transfer_reject"
    FILE_CHUNK = "file_chunk"
    FILE_TRANSFER_COMPLETE = "file_transfer_complete"
    
    # Historique
    HISTORY_REQUEST = "history_request"
    HISTORY_RESPONSE = "history_response"
    
    # Notifications
    TYPING_NOTIFICATION = "typing_notification"
    MESSAGE_DELIVERED = "message_delivered"
    MESSAGE_READ = "message_read"
    
    # Erreurs
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
    HEADER_SIZE = 4  # 4 bytes pour la taille du message
    
    @staticmethod
    def pack_message(message: Message) -> bytes:
        """Pack un message avec son en-tête de taille"""
        message_data = message.to_json()
        message_length = len(message_data)
        header = struct.pack('!I', message_length)  # Network byte order
        return header + message_data
    
    @staticmethod
    def unpack_message(socket) -> Optional[Message]:
        """Lit et décompresse un message depuis un socket"""
        try:
            # Lire l'en-tête
            header = socket.recv(Protocol.HEADER_SIZE)
            if not header:
                return None
            
            message_length = struct.unpack('!I', header)[0]
            
            # Lire le message
            message_data = b''
            remaining = message_length
            while remaining > 0:
                chunk = socket.recv(min(remaining, 4096))
                if not chunk:
                    return None
                message_data += chunk
                remaining -= len(chunk)
            
            return Message.from_json(message_data)
        except Exception:
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