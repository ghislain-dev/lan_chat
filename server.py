import socket
import threading
from datetime import datetime
import json
import os
import hashlib
import queue
import time
from typing import Dict, Optional

from protocol import Protocol, Message, MessageType, FileTransfer
from models import User, Message as ChatMessage, Group
from database import Database

class Server:
    def __init__(self, host='0.0.0.0', port=8888):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        self.clients: Dict[str, User] = {}
        self.client_sockets: Dict[str, socket.socket] = {}
        self.connections: Dict[socket.socket, str] = {}
        self.groups: Dict[str, Group] = {}
        
        self.clients_lock = threading.Lock()
        self.groups_lock = threading.Lock()
        
        self.db = Database()
        self.file_transfers: Dict[str, FileTransfer] = {}
        self.file_transfer_lock = threading.Lock()
        
        self.message_queue = queue.Queue()
        self.running = True
        
        # Créer le dossier de stockage des fichiers
        os.makedirs("storage", exist_ok=True)
    
    def start(self):
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            print(f"Serveur démarré sur {self.host}:{self.port}")
            
            threading.Thread(target=self.process_message_queue, daemon=True).start()
            threading.Thread(target=self.ping_clients, daemon=True).start()
            
            while self.running:
                try:
                    client_socket, address = self.server_socket.accept()
                    print(f"Nouvelle connexion de {address}")
                    
                    threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, address),
                        daemon=True
                    ).start()
                    
                except Exception as e:
                    print(f"Erreur lors de l'acceptation de connexion: {e}")
                    
        except Exception as e:
            print(f"Erreur lors du démarrage du serveur: {e}")
        finally:
            self.stop()
    
    def stop(self):
        self.running = False
        for username in list(self.clients.keys()):
            self.disconnect_client(username)
        
        if self.server_socket:
            self.server_socket.close()
        print("Serveur arrêté")
    
    def handle_client(self, client_socket: socket.socket, address: tuple):
        try:
            message = Protocol.unpack_message(client_socket)
            if not message or message.type != MessageType.LOGIN:
                client_socket.close()
                return
            
            username = message.content.get("username")
            
            with self.clients_lock:
                if username in self.clients:
                    response = Message(
                        type=MessageType.LOGIN_RESPONSE,
                        sender="server",
                        content={"success": False, "error": "Pseudo déjà utilisé"}
                    )
                    client_socket.send(Protocol.pack_message(response))
                    client_socket.close()
                    return
                
                user = User(
                    username=username,
                    connection_id=str(address),
                    status="online",
                    last_seen=datetime.now(),
                    address=address
                )
                user.socket = client_socket
                
                self.clients[username] = user
                self.client_sockets[username] = client_socket
                self.connections[client_socket] = username
                
                self.db.add_user(username)
                self.db.update_user_status(username, "online")
            
            print(f"Utilisateur {username} connecté depuis {address}")
            
            response = Message(
                type=MessageType.LOGIN_RESPONSE,
                sender="server",
                content={
                    "success": True,
                    "username": username,
                    "users": self.get_users_list()
                }
            )
            client_socket.send(Protocol.pack_message(response))
            
            self.send_offline_messages(username)
            self.send_groups_list(username)
            self.broadcast_user_status(username, "online")
            
            while self.running:
                try:
                    message = Protocol.unpack_message(client_socket)
                    if not message:
                        break
                    
                    self.message_queue.put((username, message))
                    
                except Exception as e:
                    print(f"Erreur lors de la réception du message de {username}: {e}")
                    break
                    
        except Exception as e:
            print(f"Erreur avec le client {address}: {e}")
        finally:
            self.disconnect_client(username)
    
    def process_message_queue(self):
        while self.running:
            try:
                username, message = self.message_queue.get(timeout=1)
                self.handle_message(username, message)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Erreur dans le traitement de la file: {e}")
    
    def handle_message(self, sender: str, message: Message):
        print(f"Message reçu de {sender}: {message.type}")
        
        handlers = {
            MessageType.PRIVATE_MESSAGE: self.handle_private_message,
            MessageType.GROUP_MESSAGE: self.handle_group_message,
            MessageType.CREATE_GROUP: self.handle_create_group,
            MessageType.FILE_TRANSFER_REQUEST: self.handle_file_transfer_request,
            MessageType.FILE_CHUNK: self.handle_file_chunk,
            MessageType.HISTORY_REQUEST: self.handle_history_request,
            MessageType.TYPING_NOTIFICATION: self.handle_typing_notification,
            MessageType.MESSAGE_READ: self.handle_message_read,
            MessageType.PONG: self.handle_pong
        }
        
        handler = handlers.get(message.type)
        if handler:
            handler(sender, message)
    
    def handle_private_message(self, sender: str, message: Message):
        recipient = message.recipient
        content = message.content
        
        chat_message = ChatMessage(
            sender=sender,
            recipient=recipient,
            content=content,
            message_type="text"
        )
        
        self.db.save_message(chat_message)
        
        with self.clients_lock:
            if recipient in self.clients:
                response = Message(
                    type=MessageType.PRIVATE_MESSAGE,
                    sender=sender,
                    recipient=recipient,
                    content=content,
                    timestamp=chat_message.timestamp.isoformat(),
                    message_id=chat_message.message_id
                )
                try:
                    self.client_sockets[recipient].send(Protocol.pack_message(response))
                    
                    ack = Message(
                        type=MessageType.MESSAGE_DELIVERED,
                        sender="server",
                        recipient=sender,
                        content={"message_id": chat_message.message_id}
                    )
                    self.client_sockets[sender].send(Protocol.pack_message(ack))
                    
                except Exception as e:
                    print(f"Erreur lors de l'envoi à {recipient}: {e}")
            else:
                self.db.add_offline_message(recipient, chat_message)
                print(f"Message pour {recipient} stocké (hors ligne)")
    
    def handle_group_message(self, sender: str, message: Message):
        group_id = message.recipient
        content = message.content
        
        with self.groups_lock:
            if group_id not in self.groups:
                return
            
            group = self.groups[group_id]
            
            chat_message = ChatMessage(
                sender=sender,
                recipient=group_id,
                content=content,
                message_type="text"
            )
            
            self.db.save_message(chat_message)
            
            for member in group.members:
                if member != sender and member in self.clients:
                    response = Message(
                        type=MessageType.GROUP_MESSAGE,
                        sender=sender,
                        recipient=group_id,
                        content=content,
                        timestamp=chat_message.timestamp.isoformat(),
                        message_id=chat_message.message_id
                    )
                    try:
                        self.client_sockets[member].send(Protocol.pack_message(response))
                    except Exception:
                        pass
    
    def handle_create_group(self, sender: str, message: Message):
        group_data = message.content
        group_name = group_data.get("name")
        members = group_data.get("members", [])
        
        if sender not in members:
            members.append(sender)
        
        group = Group(
            name=group_name,
            created_by=sender,
            members=members
        )
        
        with self.groups_lock:
            self.groups[group.group_id] = group
        
        self.db.create_group(group)
        
        response = Message(
            type=MessageType.GROUP_CREATED,
            sender="server",
            recipient=sender,
            content={
                "group_id": group.group_id,
                "name": group.name,
                "members": members
            }
        )
        self.client_sockets[sender].send(Protocol.pack_message(response))
        
        for member in members:
            if member != sender and member in self.clients:
                notification = Message(
                    type=MessageType.GROUP_LIST,
                    sender="server",
                    recipient=member,
                    content={"groups": [group.to_dict()]}
                )
                self.client_sockets[member].send(Protocol.pack_message(notification))
    
    def handle_file_transfer_request(self, sender: str, message: Message):
        file_info = message.content
        recipient = message.recipient
        
        file_transfer = FileTransfer(
            file_id=file_info["file_id"],
            sender=sender,
            recipient=recipient,
            filename=file_info["filename"],
            filesize=file_info["filesize"],
            filepath=f"storage/{file_info['file_id']}_{file_info['filename']}",
            is_directory=file_info.get("is_directory", False)
        )
        
        with self.file_transfer_lock:
            self.file_transfers[file_info["file_id"]] = file_transfer
        
        with self.clients_lock:
            if recipient in self.clients:
                request = Message(
                    type=MessageType.FILE_TRANSFER_REQUEST,
                    sender=sender,
                    recipient=recipient,
                    content=file_info
                )
                self.client_sockets[recipient].send(Protocol.pack_message(request))
            else:
                chat_message = ChatMessage(
                    sender=sender,
                    recipient=recipient,
                    content=f"Fichier: {file_info['filename']}",
                    message_type="file",
                    file_path=file_transfer.filepath
                )
                self.db.add_offline_message(recipient, chat_message)
    
    def handle_file_chunk(self, sender: str, message: Message):
        chunk_data = message.content
        file_id = chunk_data["file_id"]
        chunk = bytes.fromhex(chunk_data["data"])
        chunk_number = chunk_data["chunk_number"]
        total_chunks = chunk_data.get("total_chunks", 0)
        
        with self.file_transfer_lock:
            if file_id not in self.file_transfers:
                return
            
            transfer = self.file_transfers[file_id]
            transfer.total_chunks = total_chunks
            
            os.makedirs(os.path.dirname(transfer.filepath), exist_ok=True)
            with open(transfer.filepath, 'ab') as f:
                f.write(chunk)
            
            transfer.chunks_received += 1
            
            if transfer.chunks_received >= total_chunks:
                complete_msg = Message(
                    type=MessageType.FILE_TRANSFER_COMPLETE,
                    sender=sender,
                    recipient=transfer.recipient,
                    content={
                        "file_id": file_id,
                        "filename": transfer.filename,
                        "filepath": transfer.filepath
                    }
                )
                
                with self.clients_lock:
                    if transfer.recipient in self.clients:
                        self.client_sockets[transfer.recipient].send(
                            Protocol.pack_message(complete_msg)
                        )
                
                chat_message = ChatMessage(
                    sender=sender,
                    recipient=transfer.recipient,
                    content=f"Fichier: {transfer.filename}",
                    message_type="file",
                    file_path=transfer.filepath
                )
                self.db.save_message(chat_message)
                
                del self.file_transfers[file_id]
    
    def handle_history_request(self, sender: str, message: Message):
        target = message.content.get("target")
        limit = message.content.get("limit", 100)
        
        if target.startswith("group_"):
            messages = self.db.get_conversation_history(target, target, limit)
        else:
            messages = self.db.get_conversation_history(sender, target, limit)
        
        response = Message(
            type=MessageType.HISTORY_RESPONSE,
            sender="server",
            recipient=sender,
            content={
                "target": target,
                "messages": [msg.to_dict() for msg in messages]
            }
        )
        self.client_sockets[sender].send(Protocol.pack_message(response))
    
    def handle_typing_notification(self, sender: str, message: Message):
        recipient = message.recipient
        
        with self.clients_lock:
            if recipient in self.clients:
                notification = Message(
                    type=MessageType.TYPING_NOTIFICATION,
                    sender=sender,
                    recipient=recipient
                )
                self.client_sockets[recipient].send(Protocol.pack_message(notification))
    
    def handle_message_read(self, sender: str, message: Message):
        message_id = message.content.get("message_id")
        
        with self.clients_lock:
            # Note: Ici on devrait mettre à jour la BD, simplifié pour l'exemple
            pass
    
    def handle_pong(self, sender: str, message: Message):
        with self.clients_lock:
            if sender in self.clients:
                self.clients[sender].last_seen = datetime.now()
    
    def send_offline_messages(self, username: str):
        offline_messages = self.db.get_offline_messages(username)
        
        for msg in offline_messages:
            message = Message(
                type=MessageType.PRIVATE_MESSAGE,
                sender=msg.sender,
                recipient=username,
                content=msg.content,
                timestamp=msg.timestamp.isoformat(),
                message_id=msg.message_id
            )
            self.client_sockets[username].send(Protocol.pack_message(message))
    
    def send_groups_list(self, username: str):
        groups = self.db.get_user_groups(username)
        
        if groups:
            response = Message(
                type=MessageType.GROUP_LIST,
                sender="server",
                recipient=username,
                content={"groups": [g.to_dict() for g in groups]}
            )
            self.client_sockets[username].send(Protocol.pack_message(response))
    
    def broadcast_user_status(self, username: str, status: str):
        status_message = Message(
            type=MessageType.USER_STATUS,
            sender="server",
            content={
                "username": username,
                "status": status,
                "last_seen": datetime.now().isoformat()
            }
        )
        
        with self.clients_lock:
            for client_username, client_socket in self.client_sockets.items():
                if client_username != username:
                    try:
                        client_socket.send(Protocol.pack_message(status_message))
                    except Exception:
                        pass
    
    def get_users_list(self) -> list:
        users = []
        for username, user in self.clients.items():
            users.append({
                "username": username,
                "status": "online",
                "last_seen": user.last_seen.isoformat() if user.last_seen else None
            })
        return users
    
    def disconnect_client(self, username: str):
        if not username:
            return
        
        print(f"Déconnexion de {username}")
        
        with self.clients_lock:
            if username in self.clients:
                self.db.update_user_status(username, "offline")
                
                if username in self.client_sockets:
                    try:
                        self.client_sockets[username].close()
                    except:
                        pass
                    del self.client_sockets[username]
                
                if username in self.clients:
                    del self.clients[username]
        
        self.broadcast_user_status(username, "offline")
    
    def ping_clients(self):
        while self.running:
            time.sleep(30)
            
            with self.clients_lock:
                current_time = datetime.now()
                for username, user in list(self.clients.items()):
                    try:
                        ping = Message(
                            type=MessageType.PING,
                            sender="server"
                        )
                        self.client_sockets[username].send(Protocol.pack_message(ping))
                        
                        if (current_time - user.last_seen).seconds > 60:
                            self.disconnect_client(username)
                            
                    except Exception:
                        self.disconnect_client(username)

if __name__ == "__main__":
    server = Server()
    try:
        server.start()
    except KeyboardInterrupt:
        print("\nArrêt du serveur...")
        server.stop()