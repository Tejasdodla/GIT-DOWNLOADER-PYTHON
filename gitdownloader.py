import os
import json
import threading
import subprocess
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
import requests
import urllib.parse
import queue  # <-- add this at the top with other imports
import re  # add at top if missing

THEME = {
    'bg_color': "#F1B2B5",      # Background color
    'fg_color': "#3D3D3D",      # Text color
    'accent_color': "#61afef",  # Buttons, progress bar
    'error_color': "#BB0A1E",   # Error/abort button
    'header_bg': "#F5C5C5",     # TreeView headers
    'entry_bg': "#BEBEBE",      # Text entry background
    'tree_bg': "#FFB6C1",       # TreeView background
    'tree_selected': "#FFB6C1"  # Selected row in TreeView
}

JSON_FILE = "repos_list.json"

def load_repos():
    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, "r") as f:
                data = json.load(f)
                # Handle both list and dict format
                if isinstance(data, dict):
                    return data.get("repos", [])
                elif isinstance(data, list):
                    return data
                return []
        except json.JSONDecodeError:
            pass
    
    # Create new JSON with empty repos list
    with open(JSON_FILE, "w") as f:
        json.dump({"repos": []}, f, indent=2)
    return []

def save_repos(repos):
    with open(JSON_FILE, "w") as f:
        json.dump({"repos": repos}, f, indent=2)

def get_repo_size(url):
    """Get actual repo size from GitHub API"""
    try:
        # Extract owner/repo from URL
        path = urllib.parse.urlparse(url).path
        owner_repo = path.strip("/").replace(".git", "")
        
        # Call GitHub API
        api_url = f"https://api.github.com/repos/{owner_repo}"
        response = requests.get(api_url)
        if response.status_code == 200:
            size_kb = response.json().get("size", 0)
            return size_kb / 1024  # Convert to MB
    except Exception as e:
        print(f"Error getting repo size: {e}")
    
    # Fallback to better estimate
    return 50  # Default 50MB estimate

def is_repo_intact(path):
    if not os.path.exists(path):
        return False
        
    try:
        # More thorough git repo validation
        result = subprocess.run(
            ["git", "-C", path, "status"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception:
        return False

def validate_git_url(url):
    # Basic validation for git URLs
    url = url.strip()
    if not url.endswith('.git'):
        url += '.git'
    return url

class ModernDownloaderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Git Repository Manager")
        self.geometry("1024x600")
        
        # Configure modern theme with colors from THEME
        self.style = ttk.Style()
        self.style.configure(".", font=('Segoe UI', 10))
        
        self.style.configure("Treeview", 
            background=THEME['tree_bg'], 
            foreground=THEME['fg_color'], 
            fieldbackground=THEME['tree_bg'],
            rowheight=25,
            selectbackground=THEME['tree_selected']
        )
        self.style.configure("Treeview.Heading", 
            background=THEME['header_bg'],
            foreground=THEME['fg_color'], 
            relief="flat"
        )
        self.style.configure("TButton", 
            padding=6, 
            background=THEME['accent_color'],
            foreground=THEME['fg_color']
        )
        self.style.configure("Accent.TButton", 
            background=THEME['error_color'],
            foreground=THEME['fg_color']
        )
        self.style.configure("TLabel", 
            foreground=THEME['fg_color'],
            background=THEME['bg_color']
        )
        self.style.configure("TLabelframe", 
            background=THEME['bg_color'],
            foreground=THEME['fg_color']
        )
        self.style.configure("TLabelframe.Label", 
            foreground=THEME['fg_color'],
            background=THEME['bg_color']
        )
        self.style.configure("TFrame", 
            background=THEME['bg_color']
        )
        self.style.configure("TEntry",
            fieldbackground=THEME['entry_bg'],
            foreground=THEME['fg_color']
        )
        self.style.configure("TProgressbar", 
            background=THEME['accent_color'],
            troughcolor=THEME['header_bg']
        )
        
        self.configure(bg=THEME['bg_color'])
        
        # Initialize variables
        self.repos = load_repos()
        self.download_dir = tk.StringVar(value="F:/")  # Set initial directory
        self.downloading = False
        self.pause_flag = False
        self.repo_data = {}
        self.ui_queue = queue.Queue()  # <-- create a thread-safe queue for UI calls
        self.create_widgets()
        # Start polling the UI queue
        self.after(100, self.process_ui_queue)

    def process_ui_queue(self):
        try:
            while True:
                callback = self.ui_queue.get_nowait()
                callback()  # Execute the queued UI function
        except queue.Empty:
            pass
        self.after(100, self.process_ui_queue)
        
    def create_widgets(self):
        # Main container with padding
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Top control panel
        control_frame = ttk.LabelFrame(main_frame, text="Controls", padding="10")
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Directory selection with better spacing
        dir_frame = ttk.Frame(control_frame)
        dir_frame.pack(fill=tk.X, pady=(5, 10))
        ttk.Label(dir_frame, text="Target Directory:", width=15).pack(side=tk.LEFT)
        ttk.Entry(dir_frame, textvariable=self.download_dir).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(dir_frame, text="Browse", width=10, command=self.choose_folder).pack(side=tk.LEFT)
        
        # Action buttons with consistent sizing
        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        button_configs = [
            ("Add Repository", self.add_link_dialog, "TButton"),
            ("Start All", self.start_download, "TButton"),
            ("Pause", self.pause_download, "TButton"),
            ("Resume", self.resume_download, "TButton"),
            ("Abort", self.abort_download, "Accent.TButton")
        ]
        
        for text, command, style in button_configs:
            ttk.Button(btn_frame, text=text, command=command, style=style, width=15).pack(side=tk.LEFT, padx=2)
        
        # Repository list with better proportions
        list_frame = ttk.LabelFrame(main_frame, text="Repositories", padding="10")
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        # Treeview columns configuration
        columns = {
            "status": ("Status", 150),
            "size": ("Size", 100),
            "progress": ("Progress", 100),
            "speed": ("Speed", 120),
            "eta": ("ETA", 100)
        }
        
        self.tree = ttk.Treeview(list_frame, columns=tuple(columns.keys()), show="headings")
        
        for col, (text, width) in columns.items():
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Status and progress area
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.status_label = ttk.Label(status_frame, text="Ready", anchor=tk.W)
        self.status_label.pack(fill=tk.X)
        
        self.progress = ttk.Progressbar(status_frame, mode='determinate')
        self.progress.pack(fill=tk.X, pady=(5, 0))
        
        self.populate_tree()

    def populate_tree(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for repo in self.repos:
            size = get_repo_size(repo)
            print(f"Repo: {repo}, API Size: {size} MB")  # Add this line
            self.repo_data[repo] = {
                "size": size,
                "progress": 0,
                "downloaded": 0,
                "eta": 0,
                "speed": 0
            }
            # Initialize with status column
            self.tree.insert("", tk.END, iid=repo, values=(
                "Pending",
                f"{size:.1f} MB",
                "0%",
                "0.00 MB/s",
                "-"
            ))

    def choose_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.download_dir.set(folder)

    def add_link_dialog(self):
        new_link = tk.simpledialog.askstring("Add Git Link", "Enter the Git repo URL:")
        if new_link:
            try:
                validated_url = validate_git_url(new_link)
                if validated_url not in self.repos:
                    self.repos.append(validated_url)
                    save_repos(self.repos)
                    self.populate_tree()
                    messagebox.showinfo("Repo Added", "New repo link added successfully.")
                else:
                    messagebox.showwarning("Duplicate", "This repository is already in the list.")
            except Exception as e:
                messagebox.showerror("Error", f"Invalid repository URL: {str(e)}")

    def start_download(self):
        if self.downloading:
            messagebox.showinfo("Info", "Already downloading.")
            return
        if not self.download_dir.get():
            messagebox.showerror("Error", "Select a download directory first.")
            return
        self.pause_flag = False
        self.downloading = True
        threading.Thread(target=self.download_all).start()

    def download_all(self):
        # Schedule the update on the main thread
        self.ui_queue.put(lambda: self.status_label.config(text="Downloading..."))
        for repo in self.repos:
            if not self.downloading:
                break
            if self.pause_flag:
                while self.pause_flag and self.downloading:
                    time.sleep(0.5)
            self.clone_repo(repo)
        self.downloading = False
        # Schedule the final update on the main thread
        self.ui_queue.put(lambda: self.status_label.config(text="Done or Aborted"))

    def clone_repo(self, repo_url):
        try:
            repo_name = repo_url.split("/")[-1].replace(".git", "")
            target_path = os.path.join(self.download_dir.get(), repo_name)
            target_path = os.path.abspath(target_path)

            if is_repo_intact(target_path):
                self.update_status(repo_url, "Already exists", 100, 0, 0)
                return

            self.update_status(repo_url, "Starting...", 0, 0, 0)
            start_time = time.time()
            total_bytes = self.repo_data[repo_url]["size"] * 1024 * 1024  # estimated total in bytes

            process = subprocess.Popen(
                f'git clone --verbose --progress "{repo_url}" "{target_path}"',
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

            progress = 0
            # Regex to capture progress from git output:
            # Expected output example: "Receiving objects:  10% (100/1000), 50 KiB | 5.0 MiB/s"
            progress_re = re.compile(r"Receiving objects:\s+(\d+)%")
            # Read stderr line-by-line
            while True:
                if self.pause_flag or not self.downloading:
                    process.terminate()  # stop the process, then mark paused
                    break

                # Non-blocking read (if no new line, wait a bit)
                line = process.stderr.readline()
                if not line:
                    if process.poll() is not None:
                        break
                    time.sleep(0.2)
                    continue

                m = progress_re.search(line)
                if m:
                    progress = int(m.group(1))
                    elapsed = time.time() - start_time
                    downloaded = total_bytes * progress / 100.0
                    speed = downloaded / elapsed / (1024*1024) if elapsed > 0 else 0  # MB/s
                    eta = (total_bytes - downloaded) / (speed * 1024*1024) if speed > 0 else 0

                    self.update_status(repo_url, "Downloading...", progress, speed, eta)
                    print(f"Repo: {repo_name}, Progress: {progress}%, Speed: {speed:.2f} MB/s, ETA: {eta:.2f} s")

            # Finalize status update
            process.wait()
            if process.returncode == 0:
                self.update_status(repo_url, "Completed", 100, 0, 0)
            elif self.pause_flag or not self.downloading:
                self.update_status(repo_url, "Paused", progress,
                                   self.repo_data[repo_url]["speed"], self.repo_data[repo_url]["eta"])
            else:
                stderr = process.stderr.read()
                stdout = process.stdout.read()
                error_message = (f"Clone failed (Return Code: {process.returncode}):\n"
                                 f"Stdout: {stdout}\nStderr: {stderr}")
                self.ui_queue.put(lambda: messagebox.showerror("Clone Error", error_message))
                self.update_status(repo_url, f"Error: {error_message}", 0, 0, 0)
                print(error_message)

        except Exception as e:
            self.ui_queue.put(lambda: messagebox.showerror("Clone Error", str(e)))
            self.update_status(repo_url, f"Error: {str(e)}", 0, 0, 0)

    def update_status(self, repo_url, status, progress, speed, eta):
        try:
            # Use after() to schedule UI updates from other threads
            self.after(0, self._do_update_status, repo_url, status, progress, speed, eta)
        except Exception as e:
            print(f"Error updating status: {e}")

    def _do_update_status(self, repo_url, status, progress, speed, eta):
        """Actually perform the UI update in the main thread"""
        try:
            size = self.repo_data[repo_url]["size"]
            
            # Improved formatting
            size_str = f"{size:,.1f} MB"
            progress_str = f"{progress:,.1f}%"
            speed_str = f"{speed:,.2f} MB/s" if speed > 0 else "-"
            
            # Format ETA as MM:SS
            if eta > 0:
                minutes = int(eta // 60)
                seconds = int(eta % 60)
                eta_str = f"{minutes:02d}:{seconds:02d}"
            else:
                eta_str = "-"
            
            self.tree.item(repo_url, values=(
                status,
                size_str,
                progress_str,
                speed_str,
                eta_str
            ))
            
            self.update_overall_progress()
            self.tree.see(repo_url)
            
            # Store progress
            self.repo_data[repo_url].update({
                "progress": progress,
                "speed": speed,
                "eta": eta
            })
        except Exception as e:
            print(f"Error in _do_update_status: {e}")

    def update_overall_progress(self):
        if not self.repos:
            return
            
        completed = sum(1 for r in self.repos if self.repo_data[r]["progress"] == 100)
        total_progress = (completed / len(self.repos)) * 100
        self.progress["value"] = total_progress
        
        active_repo = next((r for r in self.repos if 0 < self.repo_data[r]["progress"] < 100), None)
        if active_repo:
            current_progress = self.repo_data[active_repo]["progress"]
            self.status_label.config(
                text=f"Overall: {total_progress:.1f}% - Active: {active_repo} ({current_progress:.1f}%)"
            )

    def pause_download(self):
        self.pause_flag = True
        self.status_label.config(text="Paused")

    def resume_download(self):
        if self.pause_flag:
            self.pause_flag = False
            self.status_label.config(text="Resuming...")

    def abort_download(self):
        self.downloading = False
        self.status_label.config(text="Aborted")
        exit()

if __name__ == "__main__":
    app = ModernDownloaderApp()
    app.mainloop()