import socket
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from datetime import datetime
import os
import hashlib
from typing import Dict, List, Optional
import queue

from protocol import Protocol, Message, MessageType, FileTransfer

class ChatClient:
    def __init__(self, host='localhost', port=8888):
        self.host = host
        self.port = port
        self.socket = None
        self.username = None
        self.connected = False
        
        # Gestion des messages
        self.message_queue = queue.Queue()
        self.users: Dict[str, dict] = {}  # username -> info
        self.groups: Dict[str, dict] = {}  # group_id -> info
        self.conversations: Dict[str, List[dict]] = {}  # target -> messages
        
        # Transfert de fichiers
        self.file_transfers: Dict[str, FileTransfer] = {}
        self.current_file_transfer = None
        
        # Interface utilisateur
        self.root = tk.Tk()
        self.root.title("LAN Messenger")
        self.root.geometry("1000x700")
        
        # Configuration des styles
        self.setup_styles()
        
        # Créer l'interface
        self.setup_login_screen()
        
        # Thread pour la réception des messages
        self.receive_thread = None
        self.running = True
        
    def setup_styles(self):
        """Configure les styles de l'interface"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Couleurs
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
        """Crée l'écran de connexion"""
        # Frame de login
        self.login_frame = ttk.Frame(self.root)
        self.login_frame.pack(expand=True)
        
        # Titre
        title = ttk.Label(
            self.login_frame,
            text="LAN Messenger",
            font=('Helvetica', 24, 'bold')
        )
        title.pack(pady=20)
        
        # Sous-titre
        subtitle = ttk.Label(
            self.login_frame,
            text="Connexion au serveur",
            font=('Helvetica', 12)
        )
        subtitle.pack(pady=10)
        
        # Frame pour les champs
        input_frame = ttk.Frame(self.login_frame)
        input_frame.pack(pady=20)
        
        # Adresse du serveur
        ttk.Label(input_frame, text="Serveur:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        self.server_entry = ttk.Entry(input_frame, width=30)
        self.server_entry.insert(0, self.host)
        self.server_entry.grid(row=0, column=1, padx=5, pady=5)
        
        # Port
        ttk.Label(input_frame, text="Port:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
        self.port_entry = ttk.Entry(input_frame, width=30)
        self.port_entry.insert(0, str(self.port))
        self.port_entry.grid(row=1, column=1, padx=5, pady=5)
        
        # Pseudo
        ttk.Label(input_frame, text="Pseudo:").grid(row=2, column=0, padx=5, pady=5, sticky='e')
        self.username_entry = ttk.Entry(input_frame, width=30)
        self.username_entry.grid(row=2, column=1, padx=5, pady=5)
        
        # Bouton de connexion
        self.connect_btn = ttk.Button(
            input_frame,
            text="Se connecter",
            command=self.connect_to_server
        )
        self.connect_btn.grid(row=3, column=0, columnspan=2, pady=20)
        
        # Barre de progression (cachée initialement)
        self.progress = ttk.Progressbar(
            self.login_frame,
            mode='indeterminate',
            length=300
        )
        
    def connect_to_server(self):
        """Tente de se connecter au serveur"""
        # Récupérer les valeurs
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
        
        # Désactiver le bouton et montrer la progression
        self.connect_btn.config(state='disabled')
        self.progress.pack(pady=10)
        self.progress.start()
        
        # Lancer la connexion dans un thread
        threading.Thread(
            target=self._connect_thread,
            args=(server, port, username),
            daemon=True
        ).start()
    
    def _connect_thread(self, server: str, port: int, username: str):
        """Thread de connexion"""
        try:
            # Créer la socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((server, port))
            
            # Envoyer la demande de login
            login_msg = Message(
                type=MessageType.LOGIN,
                sender=username,
                content={"username": username}
            )
            self.socket.send(Protocol.pack_message(login_msg))
            
            # Attendre la réponse
            response = Protocol.unpack_message(self.socket)
            
            if response and response.type == MessageType.LOGIN_RESPONSE:
                if response.content.get("success"):
                    self.username = username
                    self.connected = True
                    
                    # Mettre à jour l'interface
                    self.root.after(0, self.show_main_interface)
                    
                    # Démarrer le thread de réception
                    self.receive_thread = threading.Thread(
                        target=self.receive_messages,
                        daemon=True
                    )
                    self.receive_thread.start()
                    
                    # Démarrer le traitement de la file
                    self.root.after(100, self.process_message_queue)
                    
                else:
                    error = response.content.get("error", "Erreur inconnue")
                    self.root.after(0, lambda: self.show_login_error(error))
            else:
                self.root.after(0, lambda: self.show_login_error("Réponse invalide du serveur"))
                
        except Exception as e:
            self.root.after(0, lambda: self.show_login_error(str(e)))
    
    def show_main_interface(self):
        """Affiche l'interface principale"""
        # Détruire l'écran de login
        self.login_frame.destroy()
        
        # Créer l'interface principale
        self.setup_main_interface()
        
        # Mettre à jour le titre
        self.root.title(f"LAN Messenger - Connecté en tant que {self.username}")
        
    def show_login_error(self, error: str):
        """Affiche une erreur de connexion"""
        self.progress.stop()
        self.progress.pack_forget()
        self.connect_btn.config(state='normal')
        messagebox.showerror("Erreur de connexion", error)
    
    def setup_main_interface(self):
        """Configure l'interface principale"""
        # Panneau principal
        main_panel = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_panel.pack(fill=tk.BOTH, expand=True)
        
        # Panneau gauche (liste des utilisateurs et groupes)
        left_panel = ttk.Frame(main_panel, width=250)
        main_panel.add(left_panel, weight=1)
        
        # Notepad pour les onglets
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
        
        # Panneau droit (conversation)
        right_panel = ttk.Frame(main_panel)
        main_panel.add(right_panel, weight=3)
        self.setup_conversation_panel(right_panel)
        
    def setup_users_tab(self):
        """Configure l'onglet des utilisateurs"""
        # Frame de recherche
        search_frame = ttk.Frame(self.users_frame)
        search_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(search_frame, text="Rechercher:").pack(side=tk.LEFT)
        self.search_entry = ttk.Entry(search_frame)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.search_entry.bind('<KeyRelease>', self.filter_users)
        
        # Canvas avec scrollbar pour la liste
        canvas_frame = ttk.Frame(self.users_frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.users_canvas = tk.Canvas(canvas_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.users_canvas.yview)
        self.users_canvas.configure(yscrollcommand=scrollbar.set)
        
        # Frame intérieure pour les utilisateurs
        self.users_inner = ttk.Frame(self.users_canvas)
        self.users_window = self.users_canvas.create_window((0, 0), window=self.users_inner, anchor='nw')
        
        # Configuration du défilement
        self.users_inner.bind('<Configure>', self.on_users_frame_configure)
        self.users_canvas.bind('<Configure>', self.on_canvas_configure)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.users_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Légendes
        legend_frame = ttk.Frame(self.users_frame)
        legend_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(legend_frame, text="● En ligne", foreground=self.colors['online']).pack(side=tk.LEFT, padx=5)
        ttk.Label(legend_frame, text="● Hors ligne", foreground=self.colors['offline']).pack(side=tk.LEFT, padx=5)
        
    def setup_groups_tab(self):
        """Configure l'onglet des groupes"""
        # Bouton de création de groupe
        create_btn = ttk.Button(
            self.groups_frame,
            text="Créer un groupe",
            command=self.show_create_group_dialog
        )
        create_btn.pack(fill=tk.X, padx=5, pady=5)
        
        # Liste des groupes
        self.groups_listbox = tk.Listbox(
            self.groups_frame,
            bg='white',
            selectmode=tk.SINGLE
        )
        self.groups_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.groups_listbox.bind('<<ListboxSelect>>', self.on_group_selected)
        
    def setup_conversation_panel(self, parent):
        """Configure le panneau de conversation"""
        # En-tête avec le nom du contact
        self.header_frame = ttk.Frame(parent)
        self.header_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.contact_label = ttk.Label(
            self.header_frame,
            text="Sélectionnez un contact",
            font=('Helvetica', 14, 'bold')
        )
        self.contact_label.pack(side=tk.LEFT)
        
        # Zone de messages
        self.messages_frame = ttk.Frame(parent)
        self.messages_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Canvas pour les messages avec défilement
        self.messages_canvas = tk.Canvas(self.messages_frame, bg='white', highlightthickness=0)
        messages_scrollbar = ttk.Scrollbar(self.messages_frame, orient=tk.VERTICAL, command=self.messages_canvas.yview)
        self.messages_canvas.configure(yscrollcommand=messages_scrollbar.set)
        
        # Frame intérieure pour les messages
        self.messages_inner = ttk.Frame(self.messages_canvas)
        self.messages_window = self.messages_canvas.create_window((0, 0), window=self.messages_inner, anchor='nw')
        
        self.messages_inner.bind('<Configure>', self.on_messages_configure)
        self.messages_canvas.bind('<Configure>', self.on_messages_canvas_configure)
        
        messages_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.messages_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Zone de saisie
        input_frame = ttk.Frame(parent)
        input_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.message_entry = tk.Text(input_frame, height=3, wrap=tk.WORD)
        self.message_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.message_entry.bind('<Return>', self.on_enter_pressed)
        self.message_entry.bind('<KeyRelease>', self.on_typing)
        
        # Boutons
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
        
        # Zone de statut
        self.status_frame = ttk.Frame(parent)
        self.status_frame.pack(fill=tk.X, padx=10, pady=2)
        
        self.status_label = ttk.Label(self.status_frame, text="")
        self.status_label.pack(side=tk.LEFT)
        
        # Barre de progression pour les fichiers
        self.file_progress = ttk.Progressbar(
            self.status_frame,
            mode='determinate',
            length=200
        )
        
        # Variables de suivi
        self.current_conversation = None
        self.unread_messages = set()
        self.typing_timeout = None
        
    def on_users_frame_configure(self, event):
        """Ajuste la zone de défilement des utilisateurs"""
        self.users_canvas.configure(scrollregion=self.users_canvas.bbox('all'))
        
    def on_canvas_configure(self, event):
        """Redimensionne la fenêtre des utilisateurs"""
        self.users_canvas.itemconfig(self.users_window, width=event.width)
        
    def on_messages_configure(self, event):
        """Ajuste la zone de défilement des messages"""
        self.messages_canvas.configure(scrollregion=self.messages_canvas.bbox('all'))
        
    def on_messages_canvas_configure(self, event):
        """Redimensionne la fenêtre des messages"""
        self.messages_canvas.itemconfig(self.messages_window, width=event.width)
        
    def filter_users(self, event=None):
        """Filtre la liste des utilisateurs"""
        search_term = self.search_entry.get().lower()
        
        # Nettoyer la liste
        for widget in self.users_inner.winfo_children():
            widget.destroy()
        
        # Ajouter les utilisateurs filtrés
        for username, info in sorted(self.users.items()):
            if username != self.username:  # Ne pas s'afficher soi-même
                if not search_term or search_term in username.lower():
                    self.add_user_to_list(username, info)
                    
    def add_user_to_list(self, username: str, info: dict):
        """Ajoute un utilisateur à la liste"""
        # Frame pour l'utilisateur
        user_frame = ttk.Frame(self.users_inner)
        user_frame.pack(fill=tk.X, padx=2, pady=1)
        
        # Indicateur de nouveau message
        if username in self.unread_messages:
            indicator = tk.Label(
                user_frame,
                text="●",
                fg=self.colors['unread'],
                font=('Helvetica', 10, 'bold')
            )
            indicator.pack(side=tk.LEFT, padx=2)
        
        # Statut
        status_color = self.colors['online'] if info.get('status') == 'online' else self.colors['offline']
        status_label = tk.Label(
            user_frame,
            text="●",
            fg=status_color,
            font=('Helvetica', 10)
        )
        status_label.pack(side=tk.LEFT, padx=2)
        
        # Nom d'utilisateur
        name_label = tk.Label(
            user_frame,
            text=username,
            font=('Helvetica', 10),
            anchor='w'
        )
        name_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Dernière connexion (si hors ligne)
        if info.get('status') == 'offline' and info.get('last_seen'):
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
        
        # Rendre cliquable
        for widget in [user_frame, name_label, status_label]:
            widget.bind('<Button-1>', lambda e, u=username: self.select_user(u))
            widget.bind('<Enter>', lambda e, f=user_frame: f.configure(style='Hover.TFrame'))
            widget.bind('<Leave>', lambda e, f=user_frame: f.configure(style=''))
        
    def select_user(self, username: str):
        """Sélectionne un utilisateur pour discuter"""
        self.current_conversation = username
        
        # Mettre à jour l'en-tête
        status = self.users.get(username, {}).get('status', 'offline')
        status_text = "en ligne" if status == 'online' else "hors ligne"
        self.contact_label.config(
            text=f"{username} ({status_text})",
            foreground=self.colors['online'] if status == 'online' else self.colors['offline']
        )
        
        # Activer les boutons
        self.send_btn.config(state='normal')
        self.file_btn.config(state='normal')
        
        # Effacer l'indicateur de nouveau message
        if username in self.unread_messages:
            self.unread_messages.remove(username)
            self.filter_users()
        
        # Charger l'historique
        self.load_conversation(username)
        
        # Demander l'historique au serveur
        self.request_history(username)
        
    def on_group_selected(self, event):
        """Gère la sélection d'un groupe"""
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
                self.load_conversation(group_id)
                self.request_history(group_id)
        
    def load_conversation(self, target: str):
        """Charge une conversation dans la zone de messages"""
        # Nettoyer la zone de messages
        for widget in self.messages_inner.winfo_children():
            widget.destroy()
        
        # Afficher les messages
        if target in self.conversations:
            for msg in self.conversations[target]:
                self.display_message(msg)
        
        # Défiler vers le bas
        self.messages_canvas.yview_moveto(1.0)
        
    def display_message(self, msg: dict):
        """Affiche un message dans la zone de conversation"""
        # Frame pour le message
        msg_frame = ttk.Frame(self.messages_inner)
        msg_frame.pack(fill=tk.X, padx=10, pady=2)
        
        # Alignement selon l'expéditeur
        is_sender = msg['sender'] == self.username
        alignment = 'e' if is_sender else 'w'
        
        # Conteneur du message
        bubble_frame = ttk.Frame(msg_frame)
        bubble_frame.pack(anchor=alignment)
        
        # En-tête (expéditeur et heure)
        header = ttk.Frame(bubble_frame)
        header.pack(fill=tk.X)
        
        sender_label = tk.Label(
            header,
            text="Moi" if is_sender else msg['sender'],
            font=('Helvetica', 8, 'bold'),
            fg='#666'
        )
        sender_label.pack(side=tk.LEFT, padx=5)
        
        time_label = tk.Label(
            header,
            text=datetime.fromisoformat(msg['timestamp']).strftime('%H:%M'),
            font=('Helvetica', 8),
            fg='#999'
        )
        time_label.pack(side=tk.RIGHT, padx=5)
        
        # Contenu du message
        content_frame = tk.Frame(
            bubble_frame,
            bg='#e3f2fd' if is_sender else '#f5f5f5',
            padx=10,
            pady=5
        )
        content_frame.pack(fill=tk.X, padx=5)
        
        if msg['message_type'] == 'text':
            content_label = tk.Label(
                content_frame,
                text=msg['content'],
                bg=content_frame['bg'],
                wraplength=400,
                justify=tk.LEFT
            )
            content_label.pack()
        elif msg['message_type'] == 'file':
            # Afficher un lien vers le fichier
            file_link = tk.Label(
                content_frame,
                text=f"📁 {msg['content']}",
                bg=content_frame['bg'],
                fg='blue',
                cursor='hand2'
            )
            file_link.pack()
            file_link.bind('<Button-1>', lambda e, p=msg['file_path']: self.open_file(p))
        
        # Indicateurs de statut (pour les messages envoyés)
        if is_sender and 'delivered' in msg:
            status_text = "✓" if msg.get('read') else "✓" if msg.get('delivered') else "🕐"
            status_label = tk.Label(
                bubble_frame,
                text=status_text,
                font=('Helvetica', 8),
                fg='#666'
            )
            status_label.pack(anchor='e', padx=5)
        
    def send_message(self):
        """Envoie un message"""
        if not self.current_conversation:
            return
        
        content = self.message_entry.get('1.0', tk.END).strip()
        if not content:
            return
        
        # Créer le message
        msg_type = MessageType.PRIVATE_MESSAGE
        if self.current_conversation.startswith('group_'):
            msg_type = MessageType.GROUP_MESSAGE
        
        message = Message(
            type=msg_type,
            sender=self.username,
            recipient=self.current_conversation,
            content=content
        )
        
        # Envoyer
        try:
            self.socket.send(Protocol.pack_message(message))
            self.message_entry.delete('1.0', tk.END)
            
            # Afficher immédiatement le message
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
        """Gère la pression de la touche Entrée"""
        if not event.state & 0x1:  # Shift non pressé
            self.send_message()
            return 'break'  # Empêche le saut de ligne
            
    def on_typing(self, event):
        """Gère la notification de frappe"""
        if not self.current_conversation or self.current_conversation.startswith('group_'):
            return
        
        # Annuler le précédent timeout
        if self.typing_timeout:
            self.root.after_cancel(self.typing_timeout)
        
        # Envoyer la notification
        try:
            notification = Message(
                type=MessageType.TYPING_NOTIFICATION,
                sender=self.username,
                recipient=self.current_conversation
            )
            self.socket.send(Protocol.pack_message(notification))
        except:
            pass
        
        # Programmer l'arrêt de la notification
        self.typing_timeout = self.root.after(3000, self.stop_typing_notification)
        
    def stop_typing_notification(self):
        """Arrête la notification de frappe"""
        self.typing_timeout = None
        
    def send_file(self):
        """Envoie un fichier"""
        if not self.current_conversation:
            return
        
        # Sélectionner le fichier
        filepath = filedialog.askopenfilename()
        if not filepath:
            return
        
        filename = os.path.basename(filepath)
        filesize = os.path.getsize(filepath)
        
        # Demander confirmation
        if not messagebox.askyesno(
            "Confirmation",
            f"Envoyer '{filename}' ({filesize/1024:.1f} KB) ?"
        ):
            return
        
        # Créer un ID de transfert
        file_id = hashlib.md5(f"{self.username}{filename}{datetime.now()}".encode()).hexdigest()
        
        # Envoyer la demande
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
            
            # Lancer le transfert dans un thread
            threading.Thread(
                target=self.send_file_thread,
                args=(file_id, filepath, filename, filesize),
                daemon=True
            ).start()
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible d'envoyer le fichier: {e}")
            
    def send_file_thread(self, file_id: str, filepath: str, filename: str, filesize: int):
        """Thread d'envoi de fichier"""
        try:
            chunk_size = 8192
            total_chunks = (filesize + chunk_size - 1) // chunk_size
            chunk_number = 0
            
            with open(filepath, 'rb') as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    
                    # Envoyer le chunk
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
                    
                    # Mettre à jour la progression
                    chunk_number += 1
                    progress = (chunk_number / total_chunks) * 100
                    self.root.after(0, lambda p=progress: self.file_progress.config(value=p))
                    
            # Transfert terminé
            self.root.after(0, self.file_transfer_complete)
            
        except Exception as e:
            self.root.after(0, lambda: self.status_label.config(text=f"Erreur: {e}"))
            
    def file_transfer_complete(self):
        """Appelé quand le transfert de fichier est terminé"""
        self.file_progress.pack_forget()
        self.status_label.config(text="Fichier envoyé")
        self.root.after(3000, lambda: self.status_label.config(text=""))
        
    def open_file(self, filepath: str):
        """Ouvre un fichier reçu"""
        import subprocess
        import os
        
        if os.path.exists(filepath):
            try:
                if os.name == 'nt':  # Windows
                    os.startfile(filepath)
                else:  # Linux/Mac
                    subprocess.run(['xdg-open', filepath])
            except Exception as e:
                messagebox.showerror("Erreur", f"Impossible d'ouvrir le fichier: {e}")
        else:
            messagebox.showinfo("Info", "Le fichier n'existe pas")
            
    def show_create_group_dialog(self):
        """Affiche la boîte de dialogue de création de groupe"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Créer un groupe")
        dialog.geometry("400x500")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Nom du groupe
        ttk.Label(dialog, text="Nom du groupe:").pack(pady=5)
        name_entry = ttk.Entry(dialog, width=40)
        name_entry.pack(pady=5)
        
        # Sélection des membres
        ttk.Label(dialog, text="Membres:").pack(pady=5)
        
        # Frame avec scrollbar pour la liste
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
        
        # Ajouter les utilisateurs
        for username in self.users:
            if username != self.username:
                members_list.insert(tk.END, username)
        
        # Boutons
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
            
            # Envoyer la demande au serveur
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
        """Demande l'historique d'une conversation"""
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
        """Thread de réception des messages"""
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
        
        # Déconnexion
        self.connected = False
        self.root.after(0, self.handle_disconnection)
        
    def process_message_queue(self):
        """Traite les messages reçus"""
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
        """Traite un message reçu"""
        if message.type == MessageType.PRIVATE_MESSAGE:
            self.handle_private_message(message)
        elif message.type == MessageType.GROUP_MESSAGE:
            self.handle_group_message(message)
        elif message.type == MessageType.USER_STATUS:
            self.handle_user_status(message)
        elif message.type == MessageType.GROUP_LIST:
            self.handle_group_list(message)
        elif message.type == MessageType.GROUP_CREATED:
            self.handle_group_created(message)
        elif message.type == MessageType.HISTORY_RESPONSE:
            self.handle_history_response(message)
        elif message.type == MessageType.FILE_TRANSFER_REQUEST:
            self.handle_file_request(message)
        elif message.type == MessageType.FILE_TRANSFER_COMPLETE:
            self.handle_file_complete(message)
        elif message.type == MessageType.MESSAGE_DELIVERED:
            self.handle_message_delivered(message)
        elif message.type == MessageType.TYPING_NOTIFICATION:
            self.handle_typing_notification(message)
        elif message.type == MessageType.PING:
            self.handle_ping()
            
    def handle_private_message(self, message: Message):
        """Gère un message privé reçu"""
        # Créer l'objet message
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
        
        # Ajouter à la conversation
        conversation_key = message.sender
        if conversation_key not in self.conversations:
            self.conversations[conversation_key] = []
        self.conversations[conversation_key].append(chat_msg)
        
        # Si c'est la conversation active, afficher le message
        if self.current_conversation == message.sender:
            self.display_message(chat_msg)
            self.messages_canvas.yview_moveto(1.0)
            
            # Marquer comme lu
            self.mark_message_read(message.message_id, message.sender)
        else:
            # Ajouter un indicateur de nouveau message
            self.unread_messages.add(message.sender)
            self.filter_users()
            
            # Notifier l'utilisateur
            self.root.bell()
            
    def handle_group_message(self, message: Message):
        """Gère un message de groupe reçu"""
        # Créer l'objet message
        chat_msg = {
            'sender': message.sender,
            'recipient': message.recipient,
            'content': message.content,
            'message_type': 'text',
            'timestamp': message.timestamp or datetime.now().isoformat(),
            'message_id': message.message_id
        }
        
        # Ajouter à la conversation
        conversation_key = message.recipient
        if conversation_key not in self.conversations:
            self.conversations[conversation_key] = []
        self.conversations[conversation_key].append(chat_msg)
        
        # Si c'est la conversation active, afficher le message
        if self.current_conversation == message.recipient:
            self.display_message(chat_msg)
            self.messages_canvas.yview_moveto(1.0)
        else:
            # Notifier l'utilisateur
            self.root.bell()
            
    def handle_user_status(self, message: Message):
        """Met à jour le statut d'un utilisateur"""
        username = message.content['username']
        status = message.content['status']
        last_seen = message.content.get('last_seen')
        
        if username in self.users:
            self.users[username]['status'] = status
            if last_seen:
                self.users[username]['last_seen'] = last_seen
        
        # Mettre à jour l'affichage
        self.filter_users()
        
        # Mettre à jour l'en-tête si c'est la conversation active
        if self.current_conversation == username:
            status_text = "en ligne" if status == 'online' else "hors ligne"
            self.contact_label.config(
                text=f"{username} ({status_text})",
                foreground=self.colors['online'] if status == 'online' else self.colors['offline']
            )
            
    def handle_group_list(self, message: Message):
        """Met à jour la liste des groupes"""
        groups = message.content.get('groups', [])
        
        # Mettre à jour le dictionnaire
        for group in groups:
            self.groups[group['group_id']] = group
        
        # Mettre à jour la liste
        self.groups_listbox.delete(0, tk.END)
        for group in groups:
            self.groups_listbox.insert(tk.END, group['name'])
            
    def handle_group_created(self, message: Message):
        """Gère la confirmation de création de groupe"""
        group_info = message.content
        self.groups[group_info['group_id']] = group_info
        
        # Ajouter à la liste
        self.groups_listbox.insert(tk.END, group_info['name'])
        
        messagebox.showinfo("Succès", f"Groupe '{group_info['name']}' créé")
        
    def handle_history_response(self, message: Message):
        """Gère la réponse d'historique"""
        target = message.content['target']
        messages = message.content['messages']
        
        if target not in self.conversations:
            self.conversations[target] = []
        
        # Ajouter les messages
        for msg in messages:
            if msg not in self.conversations[target]:
                self.conversations[target].append(msg)
        
        # Trier par timestamp
        self.conversations[target].sort(key=lambda x: x['timestamp'])
        
        # Recharger si c'est la conversation active
        if self.current_conversation == target:
            self.load_conversation(target)
            
    def handle_file_request(self, message: Message):
        """Gère une demande de réception de fichier"""
        file_info = message.content
        sender = message.sender
        
        # Demander à l'utilisateur
        response = messagebox.askyesno(
            "Transfert de fichier",
            f"{sender} veut vous envoyer '{file_info['filename']}' ({file_info['filesize']/1024:.1f} KB).\nAccepter ?"
        )
        
        if response:
            # Choisir l'emplacement de sauvegarde
            save_path = filedialog.asksaveasfilename(
                initialfile=file_info['filename'],
                title="Enregistrer le fichier"
            )
            
            if save_path:
                # Préparer le transfert
                transfer = FileTransfer(
                    file_id=file_info['file_id'],
                    sender=sender,
                    recipient=self.username,
                    filename=file_info['filename'],
                    filesize=file_info['filesize'],
                    filepath=save_path
                )
                self.file_transfers[file_info['file_id']] = transfer
                
                # Accepter le transfert
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
            # Refuser
            reject_msg = Message(
                type=MessageType.FILE_TRANSFER_REJECT,
                sender=self.username,
                recipient=sender,
                content={"file_id": file_info['file_id']}
            )
            self.socket.send(Protocol.pack_message(reject_msg))
            
    def handle_file_complete(self, message: Message):
        """Gère la fin d'un transfert de fichier"""
        file_info = message.content
        self.file_progress.pack_forget()
        self.status_label.config(text="Fichier reçu")
        
        # Ajouter le message à la conversation
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
        """Gère l'accusé de réception"""
        message_id = message.content.get('message_id')
        # Mettre à jour le statut du message dans l'interface
        # (simplifié - à implémenter complètement)
        
    def handle_typing_notification(self, message: Message):
        """Gère la notification de frappe"""
        sender = message.sender
        if self.current_conversation == sender:
            self.status_label.config(text=f"{sender} est en train d'écrire...")
            # Effacer après 3 secondes
            self.root.after(3000, lambda: self.status_label.config(text=""))
            
    def handle_ping(self):
        """Répond au ping du serveur"""
        pong = Message(
            type=MessageType.PONG,
            sender=self.username
        )
        try:
            self.socket.send(Protocol.pack_message(pong))
        except:
            pass
            
    def mark_message_read(self, message_id: str, sender: str):
        """Marque un message comme lu"""
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
        """Gère la déconnexion"""
        if self.connected:
            self.connected = False
            messagebox.showinfo("Déconnecté", "Connexion au serveur perdue")
            self.root.quit()
            
    def run(self):
        """Lance l'application"""
        self.root.mainloop()
        
    def cleanup(self):
        """Nettoie les ressources"""
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