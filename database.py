import sqlite3
import json
from datetime import datetime
from typing import List, Optional, Dict
import threading
from models import User, Message, Group, Conversation, OfflineMessage

class Database:
    def __init__(self, db_path="messenger.db"):
        self.db_path = db_path
        self.lock = threading.Lock()
        self.init_database()
    
    def init_database(self):
        """Initialise les tables de la base de données"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Table des utilisateurs
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    status TEXT DEFAULT 'offline',
                    last_seen TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Table des messages
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    sender TEXT,
                    recipient TEXT,
                    content TEXT,
                    message_type TEXT,
                    timestamp TIMESTAMP,
                    delivered BOOLEAN DEFAULT 0,
                    read BOOLEAN DEFAULT 0,
                    file_path TEXT,
                    FOREIGN KEY (sender) REFERENCES users(username),
                    FOREIGN KEY (recipient) REFERENCES users(username)
                )
            ''')
            
            # Table des groupes
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS groups (
                    group_id TEXT PRIMARY KEY,
                    name TEXT,
                    created_by TEXT,
                    created_at TIMESTAMP,
                    members TEXT,
                    FOREIGN KEY (created_by) REFERENCES users(username)
                )
            ''')
            
            # Table des conversations
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    participants TEXT,
                    is_group BOOLEAN,
                    group_id TEXT,
                    last_message_id TEXT,
                    FOREIGN KEY (group_id) REFERENCES groups(group_id),
                    FOREIGN KEY (last_message_id) REFERENCES messages(message_id)
                )
            ''')
            
            # Table des messages hors ligne
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS offline_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT,
                    message_id TEXT,
                    stored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (username) REFERENCES users(username),
                    FOREIGN KEY (message_id) REFERENCES messages(message_id)
                )
            ''')
            
            conn.commit()
            conn.close()
    
    # Gestion des utilisateurs
    def add_user(self, username: str) -> bool:
        """Ajoute un nouvel utilisateur"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO users (username, status, last_seen) VALUES (?, ?, ?)",
                    (username, "offline", datetime.now().isoformat())
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
            finally:
                conn.close()
    
    def update_user_status(self, username: str, status: str):
        """Met à jour le statut d'un utilisateur"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET status = ?, last_seen = ? WHERE username = ?",
                (status, datetime.now().isoformat(), username)
            )
            conn.commit()
            conn.close()
    
    def get_all_users(self) -> List[Dict]:
        """Récupère tous les utilisateurs"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT username, status, last_seen FROM users ORDER BY username")
            users = [
                {"username": row[0], "status": row[1], "last_seen": row[2]}
                for row in cursor.fetchall()
            ]
            conn.close()
            return users
    
    # Gestion des messages
    def save_message(self, message: Message):
        """Sauvegarde un message"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO messages 
                (message_id, sender, recipient, content, message_type, timestamp, delivered, read, file_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                message.message_id,
                message.sender,
                message.recipient,
                message.content,
                message.message_type,
                message.timestamp.isoformat(),
                message.delivered,
                message.read,
                message.file_path
            ))
            conn.commit()
            conn.close()
    
    def get_conversation_history(self, user1: str, user2: str, limit: int = 100) -> List[Message]:
        """Récupère l'historique d'une conversation entre deux utilisateurs"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM messages 
                WHERE (sender = ? AND recipient = ?) OR (sender = ? AND recipient = ?)
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (user1, user2, user2, user1, limit))
            
            messages = []
            for row in cursor.fetchall():
                msg = Message(
                    message_id=row[0],
                    sender=row[1],
                    recipient=row[2],
                    content=row[3],
                    message_type=row[4],
                    timestamp=datetime.fromisoformat(row[5]),
                    delivered=bool(row[6]),
                    read=bool(row[7]),
                    file_path=row[8]
                )
                messages.append(msg)
            
            conn.close()
            return messages[::-1]  # Retourne dans l'ordre chronologique
    
    # Gestion des messages hors ligne
    def add_offline_message(self, username: str, message: Message):
        """Ajoute un message hors ligne"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO offline_messages (username, message_id) VALUES (?, ?)",
                (username, message.message_id)
            )
            conn.commit()
            conn.close()
    
    def get_offline_messages(self, username: str) -> List[Message]:
        """Récupère les messages hors ligne pour un utilisateur"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT m.* FROM messages m
                JOIN offline_messages om ON m.message_id = om.message_id
                WHERE om.username = ?
                ORDER BY m.timestamp
            ''', (username,))
            
            messages = []
            for row in cursor.fetchall():
                msg = Message(
                    message_id=row[0],
                    sender=row[1],
                    recipient=row[2],
                    content=row[3],
                    message_type=row[4],
                    timestamp=datetime.fromisoformat(row[5]),
                    delivered=bool(row[6]),
                    read=bool(row[7]),
                    file_path=row[8]
                )
                messages.append(msg)
            
            # Supprimer les messages récupérés
            cursor.execute(
                "DELETE FROM offline_messages WHERE username = ?",
                (username,)
            )
            conn.commit()
            conn.close()
            
            return messages
    
    # Gestion des groupes
    def create_group(self, group: Group):
        """Crée un nouveau groupe"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO groups (group_id, name, created_by, created_at, members)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                group.group_id,
                group.name,
                group.created_by,
                group.created_at.isoformat(),
                json.dumps(group.members)
            ))
            conn.commit()
            conn.close()
    
    def get_user_groups(self, username: str) -> List[Group]:
        """Récupère les groupes d'un utilisateur"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM groups")
            
            groups = []
            for row in cursor.fetchall():
                members = json.loads(row[4])
                if username in members:
                    group = Group(
                        group_id=row[0],
                        name=row[1],
                        created_by=row[2],
                        created_at=datetime.fromisoformat(row[3]),
                        members=members
                    )
                    groups.append(group)
            
            conn.close()
            return groups