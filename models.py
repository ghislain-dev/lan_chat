from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict
import uuid

@dataclass
class User:
    username: str
    connection_id: str
    status: str = "offline"  # online, offline
    last_seen: datetime = field(default_factory=datetime.now)
    socket = None
    address: Optional[tuple] = None
    
    def to_dict(self):
        return {
            "username": self.username,
            "status": self.status,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None
        }

@dataclass
class Message:
    # Les paramètres sans valeur par défaut doivent venir en premier
    sender: str
    recipient: str
    content: str
    message_type: str  # "text", "file", "image"
    # Ensuite les paramètres avec valeurs par défaut
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
    delivered: bool = False
    read: bool = False
    file_path: Optional[str] = None
    
    def to_dict(self):
        return {
            "message_id": self.message_id,
            "sender": self.sender,
            "recipient": self.recipient,
            "content": self.content,
            "message_type": self.message_type,
            "timestamp": self.timestamp.isoformat(),
            "delivered": self.delivered,
            "read": self.read,
            "file_path": self.file_path
        }

@dataclass
class Group:
    # Les paramètres sans valeur par défaut
    name: str
    created_by: str
    # Ensuite les paramètres avec valeurs par défaut
    group_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    members: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self):
        return {
            "group_id": self.group_id,
            "name": self.name,
            "created_by": self.created_by,
            "members": self.members,
            "created_at": self.created_at.isoformat()
        }

@dataclass
class Conversation:
    # Les paramètres sans valeur par défaut
    participants: List[str]
    # Ensuite les paramètres avec valeurs par défaut
    conversation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    is_group: bool = False
    group_id: Optional[str] = None
    last_message: Optional[Message] = None
    messages: List[Message] = field(default_factory=list)
    
    def add_message(self, message: Message):
        self.messages.append(message)
        self.last_message = message

@dataclass
class OfflineMessage:
    # Les paramètres sans valeur par défaut
    username: str
    message: Message
    # Ensuite les paramètres avec valeurs par défaut
    stored_at: datetime = field(default_factory=datetime.now)