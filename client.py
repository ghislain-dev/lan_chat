import socket
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
import os
import hashlib
from typing import Dict, List
import queue

from protocol import Protocol, Message, MessageType, FileTransfer

class ChatClient:
    def __init__(self, host='localhost', port=8888):
        self.host = host
        self.port = port
        self.socket = None
        self.username = None
        self.connected = False
        
        self.message_queue = queue.Queue()
        self.users: Dict[str, dict] = {}
        self.groups: Dict[str, dict] = {}
        self.conversations: Dict[str, List[dict]] = {}
        
        self.file_transfers: Dict[str, FileTransfer] = {}
        self.current_conversation = None
        self.unread_messages = set()
        self.typing_timeout = None
        
        self.root = tk.Tk()
        self.root.title("LAN Messenger")
        self.root.geometry("1000x700")
        
        self.setup_styles()
        self.setup_login_screen()
        
        self.running = True
    
    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        self.colors = {
            'bg': '#f0f0f0',
            'fg': '#333333',
            'online': '#4CAF50',
            'offline': '#9e9e9e',
            'unread': '#2196F3',
            'hover': '#e0e0e0',
            'selected': '#c8e6c9'
        }
    
    def setup_login_screen(self):
        self.login_frame = ttk.Frame(self.root)
        self.login_frame.pack(expand=True)
        
        title = ttk.Label(
            self.login_frame,
            text="LAN Messenger",
            font=('Helvetica', 24, 'bold')
        )
        title.pack(pady=20)
        
        subtitle = ttk.Label(
            self.login_frame,
            text="Connexion au serveur",
            font=('Helvetica', 12)
        )
        subtitle.pack(pady=10)
        
        input_frame = ttk.Frame(self.login_frame)
        input_frame.pack(pady=20)
        
        ttk.Label(input_frame, text="Serveur:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        self.server_entry = ttk.Entry(input_frame, width=30)
        self.server_entry.insert(0, self.host)
        self.server_entry.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(input_frame, text="Port:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
        self.port_entry = ttk.Entry(input_frame, width=30)
        self.port_entry.insert(0, str(self.port))
        self.port_entry.grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Label(input_frame, text="Pseudo:").grid(row=2, column=0, padx=5, pady=5, sticky='e')
        self.username_entry = ttk.Entry(input_frame, width=30)
        self.username_entry.grid(row=2, column=1, padx=5, pady=5)
        
        self.connect_btn = ttk.Button(
            input_frame,
            text="Se connecter",
            command=self.connect_to_server
        )
        self.connect_btn.grid(row=3, column=0, columnspan=2, pady=20)
        
        self.progress = ttk.Progressbar(
            self.login_frame,
            mode='indeterminate',
            length=300
        )
    
    def connect_to_server(self):
        server = self.server_entry.get().strip()
        port_str = self.port_entry.get().strip()
        username = self.username_entry.get().strip()
        
        if not server or not port_str or not username:
            messagebox.showerror("Erreur", "Veuillez remplir tous les champs")
            return
        
        try:
            port = int(port_str)
        except ValueError:
            messagebox.showerror("Erreur", "Le port doit être un nombre")
            return
        
        self.connect_btn.config(state='disabled')
        self.progress.pack(pady=10)
        self.progress.start()
        
        threading.Thread(
            target=self._connect_thread,
            args=(server, port, username),
            daemon=True
        ).start()
    
    def _connect_thread(self, server: str, port: int, username: str):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((server, port))
            
            login_msg = Message(
                type=MessageType.LOGIN,
                sender=username,
                content={"username": username}
            )
            self.socket.send(Protocol.pack_message(login_msg))
            
            response = Protocol.unpack_message(self.socket)
            
            if response and response.type == MessageType.LOGIN_RESPONSE:
                if response.content.get("success"):
                    self.username = username
                    self.connected = True
                    
                    self.root.after(0, self.show_main_interface)
                    
                    self.receive_thread = threading.Thread(
                        target=self.receive_messages,
                        daemon=True
                    )
                    self.receive_thread.start()
                    
                    self.root.after(100, self.process_message_queue)
                    
                else:
                    error = response.content.get("error", "Erreur inconnue")
                    self.root.after(0, lambda: self.show_login_error(error))
            else:
                self.root.after(0, lambda: self.show_login_error("Réponse invalide du serveur"))
                
        except Exception as e:
            self.root.after(0, lambda: self.show_login_error(str(e)))
    
    def show_main_interface(self):
        self.login_frame.destroy()
        self.setup_main