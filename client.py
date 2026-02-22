import socket
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
import os
import hashlib
from typing import Dict, List, Optional
import queue
import subprocess

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
                    
                    # Mettre à jour la liste des utilisateurs
                    users_list = response.content.get("users", [])
                    for user in users_list:
                        self.users[user["username"]] = user
                    
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
        self.setup_main_interface()
        self.root.title(f"LAN Messenger - Connecté en tant que {self.username}")
    
    def show_login_error(self, error: str):
        self.progress.stop()
        self.progress.pack_forget()
        self.connect_btn.config(state='normal')
        messagebox.showerror("Erreur de connexion", error)
    
    def setup_main_interface(self):
        # Panneau principal
        main_panel = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_panel.pack(fill=tk.BOTH, expand=True)
        
        # Panneau gauche
        left_panel = ttk.Frame(main_panel, width=250)
        main_panel.add(left_panel, weight=1)
        
        self.notebook = ttk.Notebook(left_panel)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Onglet Utilisateurs
        self.users_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.users_frame, text="Utilisateurs")
        self.setup_users_tab()
        
        # Onglet Groupes
        self.groups_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.groups_frame, text="Groupes")
        self.setup_groups_tab()
        
        # Panneau droit
        right_panel = ttk.Frame(main_panel)
        main_panel.add(right_panel, weight=3)
        self.setup_conversation_panel(right_panel)
    
    def setup_users_tab(self):
        search_frame = ttk.Frame(self.users_frame)
        search_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(search_frame, text="Rechercher:").pack(side=tk.LEFT)
        self.search_entry = ttk.Entry(search_frame)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.search_entry.bind('<KeyRelease>', self.filter_users)
        
        canvas_frame = ttk.Frame(self.users_frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.users_canvas = tk.Canvas(canvas_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.users_canvas.yview)
        self.users_canvas.configure(yscrollcommand=scrollbar.set)
        
        self.users_inner = ttk.Frame(self.users_canvas)
        self.users_window = self.users_canvas.create_window((0, 0), window=self.users_inner, anchor='nw')
        
        self.users_inner.bind('<Configure>', self.on_users_frame_configure)
        self.users_canvas.bind('<Configure>', self.on_canvas_configure)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.users_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        legend_frame = ttk.Frame(self.users_frame)
        legend_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(legend_frame, text="● En ligne", foreground=self.colors['online']).pack(side=tk.LEFT, padx=5)
        ttk.Label(legend_frame, text="● Hors ligne", foreground=self.colors['offline']).pack(side=tk.LEFT, padx=5)
    
    def setup_groups_tab(self):
        create_btn = ttk.Button(
            self.groups_frame,
            text="Créer un groupe",
            command=self.show_create_group_dialog
        )
        create_btn.pack(fill=tk.X, padx=5, pady=5)
        
        self.groups_listbox = tk.Listbox(
            self.groups_frame,
            bg='white',
            selectmode=tk.SINGLE
        )
        self.groups_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.groups_listbox.bind('<<ListboxSelect>>', self.on_group_selected)
    
    def setup_conversation_panel(self, parent):
        self.header_frame = ttk.Frame(parent)
        self.header_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.contact_label = ttk.Label(
            self.header_frame,
            text="Sélectionnez un contact",
            font=('Helvetica', 14, 'bold')
        )
        self.contact_label.pack(side=tk.LEFT)
        
        self.messages_frame = ttk.Frame(parent)
        self.messages_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.messages_canvas = tk.Canvas(self.messages_frame, bg='white', highlightthickness=0)
        messages_scrollbar = ttk.Scrollbar(self.messages_frame, orient=tk.VERTICAL, command=self.messages_canvas.yview)
        self.messages_canvas.configure(yscrollcommand=messages_scrollbar.set)
        
        self.messages_inner = ttk.Frame(self.messages_canvas)
        self.messages_window = self.messages_canvas.create_window((0, 0), window=self.messages_inner, anchor='nw')
        
        self.messages_inner.bind('<Configure>', self.on_messages_configure)
        self.messages_canvas.bind('<Configure>', self.on_messages_canvas_configure)
        
        messages_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.messages_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        input_frame = ttk.Frame(parent)
        input_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.message_entry = tk.Text(input_frame, height=3, wrap=tk.WORD)
        self.message_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.message_entry.bind('<Return>', self.on_enter_pressed)
        self.message_entry.bind('<KeyRelease>', self.on_typing)
        
        button_frame = ttk.Frame(input_frame)
        button_frame.pack(side=tk.RIGHT, padx=5)
        
        self.send_btn = ttk.Button(
            button_frame,
            text="Envoyer",
            command=self.send_message,
            state='disabled'
        )
        self.send_btn.pack(pady=2)
        
        self.file_btn = ttk.Button(
            button_frame,
            text="Fichier",
            command=self.send_file,
            state='disabled'
        )
        self.file_btn.pack(pady=2)
        
        self.status_frame = ttk.Frame(parent)
        self.status_frame.pack(fill=tk.X, padx=10, pady=2)
        
        self.status_label = ttk.Label(self.status_frame, text="")
        self.status_label.pack(side=tk.LEFT)
        
        self.file_progress = ttk.Progressbar(
            self.status_frame,
            mode='determinate',
            length=200
        )
    
    def on_users_frame_configure(self, event):
        self.users_canvas.configure(scrollregion=self.users_canvas.bbox('all'))
    
    def on_canvas_configure(self, event):
        self.users_canvas.itemconfig(self.users_window, width=event.width)
    
    def on_messages_configure(self, event):
        self.messages_canvas.configure(scrollregion=self.messages_canvas.bbox('all'))
    
    def on_messages_canvas_configure(self, event):
        self.messages_canvas.itemconfig(self.messages_window, width=event.width)
    
    def filter_users(self, event=None):
        search_term = self.search_entry.get().lower()
        
        for widget in self.users_inner.winfo_children():
            widget.destroy()
        
        for username, info in sorted(self.users.items()):
            if username != self.username:
                if not search_term or search_term in username.lower():
                    self.add_user_to_list(username, info)
    
    def add_user_to_list(self, username: str, info: dict):
        user_frame = ttk.Frame(self.users_inner)
        user_frame.pack(fill=tk.X, padx=2, pady=1)
        
        if username in self.unread_messages:
            indicator = tk.Label(
                user_frame,
                text="●",
                fg=self.colors['unread'],
                font=('Helvetica', 10, 'bold')
            )
            indicator.pack(side=tk.LEFT, padx=2)
        
        status_color = self.colors['online'] if info.get('status') == 'online' else self.colors['offline']
        status_label = tk.Label(
            user_frame,
            text="●",
            fg=status_color,
            font=('Helvetica', 10)
        )
        status_label.pack(side=tk.LEFT, padx=2)
        
        name_label = tk.Label(
            user_frame,
            text=username,
            font=('Helvetica', 10),
            anchor='w'
        )
        name_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        if info.get('status') == 'offline' and info.get('last_seen'):
            try:
                last_seen = datetime.fromisoformat(info['last_seen'])
                time_diff = datetime.now() - last_seen
                if time_diff.days > 0:
                    last_text = f"il y a {time_diff.days}j"
                elif time_diff.seconds > 3600:
                    last_text = f"il y a {time_diff.seconds//3600}h"
                else:
                    last_text = f"il y a {time_diff.seconds//60}min"
                
                last_label = tk.Label(
                    user_frame,
                    text=last_text,
                    font=('Helvetica', 8),
                    fg='gray'
                )
                last_label.pack(side=tk.RIGHT, padx=5)
            except:
                pass
        
        for widget in [user_frame, name_label, status_label]:
            widget.bind('<Button-1>', lambda e, u=username: self.select_user(u))
    
    def select_user(self, username: str):
        self.current_conversation = username
        
        status = self.users.get(username, {}).get('status', 'offline')
        status_text = "en ligne" if status == 'online' else "hors ligne"
        self.contact_label.config(
            text=f"{username} ({status_text})",
            foreground=self.colors['online'] if status == 'online' else self.colors['offline']
        )
        
        self.send_btn.config(state='normal')
        self.file_btn.config(state='normal')
        
        if username in self.unread_messages:
            self.unread_messages.remove(username)
            self.filter_users()
        
        self.load_conversation(username)
        self.request_history(username)
    
    def on_group_selected(self, event):
        selection = self.groups_listbox.curselection()
        if selection:
            group_name = self.groups_listbox.get(selection[0])
            group_id = None
            for gid, info in self.groups.items():
                if info['name'] == group_name:
                    group_id = gid
                    break
            
            if group_id:
                self.current_conversation = group_id
                self.contact_label.config(text=f"Groupe: {group_name}")
                self.send_btn.config(state='normal')
                self.file_btn.config(state='normal')
                self.load_conversation(group_id)
                self.request_history(group_id)
    
    def load_conversation(self, target: str):
        for widget in self.messages_inner.winfo_children():
            widget.destroy()
        
        if target in self.conversations:
            for msg in self.conversations[target]:
                self.display_message(msg)
        
        self.messages_canvas.yview_moveto(1.0)
    
    def display_message(self, msg: dict):
        msg_frame = ttk.Frame(self.messages_inner)
        msg_frame.pack(fill=tk.X, padx=10, pady=2)
        
        is_sender = msg['sender'] == self.username
        alignment = 'e' if is_sender else 'w'
        
        bubble_frame = ttk.Frame(msg_frame)
        bubble_frame.pack(anchor=alignment)
        
        header = ttk.Frame(bubble_frame)
        header.pack(fill=tk.X)
        
        sender_label = tk.Label(
            header,
            text="Moi" if is_sender else msg['sender'],
            font=('Helvetica', 8, 'bold'),
            fg='#666'
        )
        sender_label.pack(side=tk.LEFT, padx=5)
        
        try:
            timestamp = datetime.fromisoformat(msg['timestamp']).strftime('%H:%M')
        except:
            timestamp = ""
        
        time_label = tk.Label(
            header,
            text=timestamp,
            font=('Helvetica', 8),
            fg='#999'
        )
        time_label.pack(side=tk.RIGHT, padx=5)
        
        content_frame = tk.Frame(
            bubble_frame,
            bg='#e3f2fd' if is_sender else '#f5f5f5',
            padx=10,
            pady=5
        )
        content_frame.pack(fill=tk.X, padx=5)
        
        if msg.get('message_type') == 'text':
            content_label = tk.Label(
                content_frame,
                text=msg['content'],
                bg=content_frame['bg'],
                wraplength=400,
                justify=tk.LEFT
            )
            content_label.pack()
        elif msg.get('message_type') == 'file':
            file_link = tk.Label(
                content_frame,
                text=f"📁 {msg['content']}",
                bg=content_frame['bg'],
                fg='blue',
                cursor='hand2'
            )
            file_link.pack()
            file_link.bind('<Button-1>', lambda e, p=msg.get('file_path'): self.open_file(p))
    
    def send_message(self):
        if not self.current_conversation:
            return
        
        content = self.message_entry.get('1.0', tk.END).strip()
        if not content:
            return
        
        msg_type = MessageType.PRIVATE_MESSAGE
        if self.current_conversation.startswith('group_'):
            msg_type = MessageType.GROUP_MESSAGE
        
        message = Message(
            type=msg_type,
            sender=self.username,
            recipient=self.current_conversation,
            content=content
        )
        
        try:
            self.socket.send(Protocol.pack_message(message))
            self.message_entry.delete('1.0', tk.END)
            
            chat_msg = {
                'sender': self.username,
                'recipient': self.current_conversation,
                'content': content,
                'message_type': 'text',
                'timestamp': datetime.now().isoformat(),
                'delivered': False,
                'read': False
            }
            
            if self.current_conversation not in self.conversations:
                self.conversations[self.current_conversation] = []
            self.conversations[self.current_conversation].append(chat_msg)
            self.display_message(chat_msg)
            self.messages_canvas.yview_moveto(1.0)
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible d'envoyer le message: {e}")
    
    def on_enter_pressed(self, event):
        if not event.state & 0x1:
            self.send_message()
            return 'break'
    
    def on_typing(self, event):
        if not self.current_conversation or self.current_conversation.startswith('group_'):
            return
        
        if self.typing_timeout:
            self.root.after_cancel(self.typing_timeout)
        
        try:
            notification = Message(
                type=MessageType.TYPING_NOTIFICATION,
                sender=self.username,
                recipient=self.current_conversation
            )
            self.socket.send(Protocol.pack_message(notification))
        except:
            pass
        
        self.typing_timeout = self.root.after(3000, self.stop_typing_notification)
    
    def stop_typing_notification(self):
        self.typing_timeout = None
    
    def send_file(self):
        if not self.current_conversation:
            return
        
        filepath = filedialog.askopenfilename()
        if not filepath:
            return
        
        filename = os.path.basename(filepath)
        filesize = os.path.getsize(filepath)
        
        if not messagebox.askyesno(
            "Confirmation",
            f"Envoyer '{filename}' ({filesize/1024:.1f} KB) ?"
        ):
            return
        
        file_id = hashlib.md5(f"{self.username}{filename}{datetime.now()}".encode()).hexdigest()
        
        transfer_msg = Message(
            type=MessageType.FILE_TRANSFER_REQUEST,
            sender=self.username,
            recipient=self.current_conversation,
            content={
                "file_id": file_id,
                "filename": filename,
                "filesize": filesize,
                "is_directory": False
            }
        )
        
        try:
            self.socket.send(Protocol.pack_message(transfer_msg))
            self.status_label.config(text=f"Envoi de {filename}...")
            self.file_progress.pack(side=tk.RIGHT, padx=5)
            
            threading.Thread(
                target=self.send_file_thread,
                args=(file_id, filepath, filename, filesize),
                daemon=True
            ).start()
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible d'envoyer le fichier: {e}")
    
    def send_file_thread(self, file_id: str, filepath: str, filename: str, filesize: int):
        try:
            chunk_size = 8192
            total_chunks = (filesize + chunk_size - 1) // chunk_size
            chunk_number = 0
            
            with open(filepath, 'rb') as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    
                    chunk_msg = Message(
                        type=MessageType.FILE_CHUNK,
                        sender=self.username,
                        recipient=self.current_conversation,
                        content={
                            "file_id": file_id,
                            "chunk_number": chunk_number,
                            "data": chunk.hex(),
                            "total_chunks": total_chunks
                        }
                    )
                    self.socket.send(Protocol.pack_message(chunk_msg))
                    
                    chunk_number += 1
                    progress = (chunk_number / total_chunks) * 100
                    self.root.after(0, lambda p=progress: self.file_progress.config(value=p))
                    
            self.root.after(0, self.file_transfer_complete)
            
        except Exception as e:
            self.root.after(0, lambda: self.status_label.config(text=f"Erreur: {e}"))
    
    def file_transfer_complete(self):
        self.file_progress.pack_forget()
        self.status_label.config(text="Fichier envoyé")
        self.root.after(3000, lambda: self.status_label.config(text=""))
    
    def open_file(self, filepath: str):
        if filepath and os.path.exists(filepath):
            try:
                if os.name == 'nt':
                    os.startfile(filepath)
                else:
                    subprocess.run(['xdg-open', filepath])
            except Exception as e:
                messagebox.showerror("Erreur", f"Impossible d'ouvrir le fichier: {e}")
        else:
            messagebox.showinfo("Info", "Le fichier n'existe pas")
    
    def show_create_group_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Créer un groupe")
        dialog.geometry("400x500")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Nom du groupe:").pack(pady=5)
        name_entry = ttk.Entry(dialog, width=40)
        name_entry.pack(pady=5)
        
        ttk.Label(dialog, text="Membres:").pack(pady=5)
        
        list_frame = ttk.Frame(dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        members_list = tk.Listbox(
            list_frame,
            selectmode=tk.MULTIPLE,
            yscrollcommand=scrollbar.set
        )
        members_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar.config(command=members_list.yview)
        
        for username in self.users:
            if username != self.username:
                members_list.insert(tk.END, username)
        
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, pady=10)
        
        def create_group():
            name = name_entry.get().strip()
            if not name:
                messagebox.showerror("Erreur", "Veuillez entrer un nom de groupe")
                return
            
            selected_indices = members_list.curselection()
            selected_members = [members_list.get(i) for i in selected_indices]
            
            if not selected_members:
                messagebox.showerror("Erreur", "Sélectionnez au moins un membre")
                return
            
            create_msg = Message(
                type=MessageType.CREATE_GROUP,
                sender=self.username,
                content={
                    "name": name,
                    "members": selected_members
                }
            )
            
            try:
                self.socket.send(Protocol.pack_message(create_msg))
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Erreur", f"Impossible de créer le groupe: {e}")
        
        ttk.Button(button_frame, text="Annuler", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Créer", command=create_group).pack(side=tk.RIGHT, padx=5)
    
    def request_history(self, target: str):
        history_msg = Message(
            type=MessageType.HISTORY_REQUEST,
            sender=self.username,
            content={
                "target": target,
                "limit": 100
            }
        )
        
        try:
            self.socket.send(Protocol.pack_message(history_msg))
        except Exception:
            pass
    
    def receive_messages(self):
        while self.running and self.connected:
            try:
                message = Protocol.unpack_message(self.socket)
                if message:
                    self.message_queue.put(message)
                else:
                    break
            except Exception as e:
                print(f"Erreur de réception: {e}")
                break
        
        self.connected = False
        self.root.after(0, self.handle_disconnection)
    
    def process_message_queue(self):
        try:
            while True:
                message = self.message_queue.get_nowait()
                self.handle_received_message(message)
        except queue.Empty:
            pass
        finally:
            if self.running:
                self.root.after(100, self.process_message_queue)
    
    def handle_received_message(self, message: Message):
        handlers = {
            MessageType.PRIVATE_MESSAGE: self.handle_private_message,
            MessageType.GROUP_MESSAGE: self.handle_group_message,
            MessageType.USER_STATUS: self.handle_user_status,
            MessageType.GROUP_LIST: self.handle_group_list,
            MessageType.GROUP_CREATED: self.handle_group_created,
            MessageType.HISTORY_RESPONSE: self.handle_history_response,
            MessageType.FILE_TRANSFER_REQUEST: self.handle_file_request,
            MessageType.FILE_TRANSFER_COMPLETE: self.handle_file_complete,
            MessageType.MESSAGE_DELIVERED: self.handle_message_delivered,
            MessageType.TYPING_NOTIFICATION: self.handle_typing_notification,
            MessageType.PING: self.handle_ping
        }
        
        handler = handlers.get(message.type)
        if handler:
            handler(message)
    
    def handle_private_message(self, message: Message):
        chat_msg = {
            'sender': message.sender,
            'recipient': message.recipient,
            'content': message.content,
            'message_type': 'text',
            'timestamp': message.timestamp or datetime.now().isoformat(),
            'message_id': message.message_id,
            'delivered': True,
            'read': False
        }
        
        conversation_key = message.sender
        if conversation_key not in self.conversations:
            self.conversations[conversation_key] = []
        self.conversations[conversation_key].append(chat_msg)
        
        if self.current_conversation == message.sender:
            self.display_message(chat_msg)
            self.messages_canvas.yview_moveto(1.0)
            self.mark_message_read(message.message_id, message.sender)
        else:
            self.unread_messages.add(message.sender)
            self.filter_users()
            self.root.bell()
    
    def handle_group_message(self, message: Message):
        chat_msg = {
            'sender': message.sender,
            'recipient': message.recipient,
            'content': message.content,
            'message_type': 'text',
            'timestamp': message.timestamp or datetime.now().isoformat(),
            'message_id': message.message_id
        }
        
        conversation_key = message.recipient
        if conversation_key not in self.conversations:
            self.conversations[conversation_key] = []
        self.conversations[conversation_key].append(chat_msg)
        
        if self.current_conversation == message.recipient:
            self.display_message(chat_msg)
            self.messages_canvas.yview_moveto(1.0)
        else:
            self.root.bell()
    
    def handle_user_status(self, message: Message):
        username = message.content['username']
        status = message.content['status']
        last_seen = message.content.get('last_seen')
        
        if username in self.users:
            self.users[username]['status'] = status
            if last_seen:
                self.users[username]['last_seen'] = last_seen
        else:
            self.users[username] = {'username': username, 'status': status, 'last_seen': last_seen}
        
        self.filter_users()
        
        if self.current_conversation == username:
            status_text = "en ligne" if status == 'online' else "hors ligne"
            self.contact_label.config(
                text=f"{username} ({status_text})",
                foreground=self.colors['online'] if status == 'online' else self.colors['offline']
            )
    
    def handle_group_list(self, message: Message):
        groups = message.content.get('groups', [])
        
        for group in groups:
            self.groups[group['group_id']] = group
        
        self.groups_listbox.delete(0, tk.END)
        for group in groups:
            self.groups_listbox.insert(tk.END, group['name'])
    
    def handle_group_created(self, message: Message):
        group_info = message.content
        self.groups[group_info['group_id']] = group_info
        self.groups_listbox.insert(tk.END, group_info['name'])
        messagebox.showinfo("Succès", f"Groupe '{group_info['name']}' créé")
    
    def handle_history_response(self, message: Message):
        target = message.content['target']
        messages = message.content['messages']
        
        if target not in self.conversations:
            self.conversations[target] = []
        
        for msg in messages:
            if msg not in self.conversations[target]:
                self.conversations[target].append(msg)
        
        self.conversations[target].sort(key=lambda x: x['timestamp'])
        
        if self.current_conversation == target:
            self.load_conversation(target)
    
    def handle_file_request(self, message: Message):
        file_info = message.content
        sender = message.sender
        
        response = messagebox.askyesno(
            "Transfert de fichier",
            f"{sender} veut vous envoyer '{file_info['filename']}' ({file_info['filesize']/1024:.1f} KB).\nAccepter ?"
        )
        
        if response:
            save_path = filedialog.asksaveasfilename(
                initialfile=file_info['filename'],
                title="Enregistrer le fichier"
            )
            
            if save_path:
                transfer = FileTransfer(
                    file_id=file_info['file_id'],
                    sender=sender,
                    recipient=self.username,
                    filename=file_info['filename'],
                    filesize=file_info['filesize'],
                    filepath=save_path
                )
                self.file_transfers[file_info['file_id']] = transfer
                
                accept_msg = Message(
                    type=MessageType.FILE_TRANSFER_ACCEPT,
                    sender=self.username,
                    recipient=sender,
                    content={"file_id": file_info['file_id']}
                )
                self.socket.send(Protocol.pack_message(accept_msg))
                
                self.status_label.config(text=f"Réception de {file_info['filename']}...")
                self.file_progress.pack(side=tk.RIGHT, padx=5)
        else:
            reject_msg = Message(
                type=MessageType.FILE_TRANSFER_REJECT,
                sender=self.username,
                recipient=sender,
                content={"file_id": file_info['file_id']}
            )
            self.socket.send(Protocol.pack_message(reject_msg))
    
    def handle_file_complete(self, message: Message):
        file_info = message.content
        self.file_progress.pack_forget()
        self.status_label.config(text="Fichier reçu")
        
        chat_msg = {
            'sender': message.sender,
            'recipient': self.username,
            'content': f"Fichier: {file_info['filename']}",
            'message_type': 'file',
            'file_path': file_info['filepath'],
            'timestamp': datetime.now().isoformat()
        }
        
        conversation_key = message.sender
        if conversation_key not in self.conversations:
            self.conversations[conversation_key] = []
        self.conversations[conversation_key].append(chat_msg)
        
        if self.current_conversation == message.sender:
            self.display_message(chat_msg)
        
        self.root.after(3000, lambda: self.status_label.config(text=""))
    
    def handle_message_delivered(self, message: Message):
        pass
    
    def handle_typing_notification(self, message: Message):
        sender = message.sender
        if self.current_conversation == sender:
            self.status_label.config(text=f"{sender} est en train d'écrire...")
            self.root.after(3000, lambda: self.status_label.config(text=""))
    
    def handle_ping(self, message: Message):
        pong = Message(
            type=MessageType.PONG,
            sender=self.username
        )
        try:
            self.socket.send(Protocol.pack_message(pong))
        except:
            pass
    
    def mark_message_read(self, message_id: str, sender: str):
        read_msg = Message(
            type=MessageType.MESSAGE_READ,
            sender=self.username,
            recipient=sender,
            content={"message_id": message_id}
        )
        try:
            self.socket.send(Protocol.pack_message(read_msg))
        except:
            pass
    
    def handle_disconnection(self):
        if self.connected:
            self.connected = False
            messagebox.showinfo("Déconnecté", "Connexion au serveur perdue")
            self.root.quit()
    
    def run(self):
        self.root.mainloop()
    
    def cleanup(self):
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass

if __name__ == "__main__":
    client = ChatClient()
    try:
        client.run()
    finally:
        client.cleanup()