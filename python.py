import socket
import ipaddress
import tkinter as tk
from tkinter import scrolledtext
from threading import Thread
import time
import numpy as np  # Import numpy for wave calculations
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Class for package structure
class Package:
    def __init__(self, data, src_ip, dst_ip):
        self.data = data
        self.src_ip = src_ip
        self.dst_ip = dst_ip

# Class for DNS64 functionality
class DNS64:
    def __init__(self, ipv4_addr, ipv6_addr):
        self.ipv4_addr = ipv4_addr
        self.ipv6_addr = ipv6_addr

    def translate_addr(self, addr):
        ip_obj = ipaddress.ip_address(addr)
        if ip_obj.version == 4:
            return self.ipv6_addr
        elif ip_obj.version == 6:
            return self.ipv4_addr
        else:
            raise ValueError("Invalid address version")

# Client class that connects to the server and sends the package
class Client:
    def __init__(self, host, port, dns64, log_callback, graph_callback, interval=1, packet_count=10):
        self.host = host
        self.port = port
        self.dns64 = dns64
        self.log_callback = log_callback
        self.graph_callback = graph_callback
        self.interval = interval
        self.packet_count = packet_count
        self.is_sending = False
        self.client_socket = None

    def get_local_ip(self):
        try:
            temp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            temp_socket.connect(('8.8.8.8', 80))
            local_ip = temp_socket.getsockname()[0]
            temp_socket.close()
            return local_ip
        except Exception as e:
            self.log_callback(f"Error retrieving local IP: {str(e)}")
            return None

    def connect_to_system(self):
        try:
            if self.client_socket is None:
                self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.log_callback(f"Connecting to {self.host}:{self.port}")
            self.client_socket.connect((self.host, self.port))
            self.log_callback("Connection established")
        except Exception as e:
            self.log_callback(f"Connection failed: {str(e)}")
            self.client_socket = None

    def send_package(self, package, packet_num):
        try:
            if self.client_socket:
                self.log_callback(f"Sending package with IPv4: {package.src_ip}")
                self.client_socket.sendall(package.data)

                # Receive response
                response = self.client_socket.recv(1024)
                self.log_callback(f"Received response from server (IPv6): {response.decode()}")

                # Update the graph with current packet number
                self.graph_callback(packet_num)
            else:
                self.log_callback("No open socket to send the package")
        except Exception as e:
            self.log_callback(f"Error sending package: {str(e)}")

    def start_sending(self):
        self.is_sending = True
        self.connect_to_system()

        if self.client_socket:
            local_ipv4 = self.get_local_ip()
            if local_ipv4:
                for i in range(self.packet_count):
                    if not self.is_sending:
                        self.log_callback("Stopped sending packets.")
                        break

                    package_data = f"{local_ipv4} Packet {i + 1}".encode()
                    package = Package(package_data, local_ipv4, "::1")
                    self.send_package(package, i + 1)
                    self.log_callback(f"Sent packet {i + 1}/{self.packet_count}")
                    time.sleep(self.interval)

            self.is_sending = False
            self.client_socket.close()
            self.client_socket = None
        else:
            self.log_callback("Failed to connect to the server")

    def stop_sending(self):
        self.is_sending = False

# Server class to listen for connections and respond
class Server:
    def __init__(self, host, port, dns64, log_callback, graph_callback):
        self.host = host
        self.port = port
        self.dns64 = dns64
        self.log_callback = log_callback
        self.graph_callback = graph_callback
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.packet_count = 0

    def start_server(self):
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(1)
            self.log_callback(f"Listening for connections on {self.host}:{self.port}")
            
            conn, addr = self.server_socket.accept()
            self.log_callback(f"Connected to {addr}")

            while True:
                data = conn.recv(1024)
                if not data:
                    break

                self.packet_count += 1
                self.log_callback(f"Received data from client: {data.decode()}")

                translated_ipv6 = self.dns64.translate_addr(data.decode().split()[0])
                self.log_callback(f"Translated IPv4 to IPv6: {translated_ipv6}")

                conn.sendall(str(translated_ipv6).encode())
                self.log_callback("Sent IPv6 back to the client")

                self.graph_callback(self.packet_count)

            conn.close()
        except Exception as e:
            self.log_callback(f"Server error: {str(e)}")
        finally:
            self.server_socket.close()

# Tkinter UI for logging and input, with graph plotting
class TunnelUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Tunneling App with Graph")
        
        # Console log area
        self.log_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, width=50, height=20)
        self.log_area.pack(padx=10, pady=10)
        
        # Sender/Receiver Input Frame
        self.input_frame = tk.Frame(root)
        self.input_frame.pack(pady=10)
        
        # Role selection buttons
        self.sender_button = tk.Button(self.input_frame, text="Start as Sender", command=self.start_as_sender)
        self.sender_button.grid(row=0, column=0, padx=5)
        
        self.receiver_button = tk.Button(self.input_frame, text="Start as Receiver", command=self.start_as_receiver)
        self.receiver_button.grid(row=0, column=1, padx=5)
        
        # Create a figure for plotting sender graph
        self.fig_sender, self.ax_sender = plt.subplots(figsize=(5, 3))
        self.canvas_sender = FigureCanvasTkAgg(self.fig_sender, master=root)
        self.canvas_sender.get_tk_widget().pack(padx=10, pady=10)
        self.ax_sender.set_title("Transition of IPv6 to IPv4")
        self.ax_sender.set_xlabel("Packet Number")
        self.ax_sender.set_ylabel("Speed")
        self.sender_packet_numbers = []
        self.sender_wave_values = []  # Store wave values for sender
        self.sender_time = 0  # Time variable for sender wave calculation

        # Create a figure for plotting receiver graph
        self.fig_receiver, self.ax_receiver = plt.subplots(figsize=(5, 3))
        self.canvas_receiver = FigureCanvasTkAgg(self.fig_receiver, master=root)
        self.canvas_receiver.get_tk_widget().pack(padx=10, pady=10)
        self.ax_receiver.set_title("Transition of IPv4 to IPv6")
        self.ax_receiver.set_xlabel("Packet Number")
        self.ax_receiver.set_ylabel("Speed")
        self.receiver_packet_numbers = []
        self.receiver_wave_values = []  # Store wave values for receiver
        self.receiver_time = 0  # Time variable for receiver wave calculation

    def log(self, message):
        self.log_area.insert(tk.END, message + '\n')
        self.log_area.see(tk.END)

    def update_sender_graph(self, packet_num):
        """Update the sender graph to represent speed fluctuations."""
        self.sender_packet_numbers.append(packet_num)

        # Simulate speed changes using a sine function for sender
        self.sender_time += 0.2  # Increment time (faster to simulate speed changes)
        speed_value = 5 + 5 * np.sin(self.sender_time)  # Base speed of 5, fluctuating by ±5

        self.sender_wave_values.append(speed_value)

        # Update the sender graph
        self.ax_sender.clear()
        self.ax_sender.plot(self.sender_packet_numbers, self.sender_wave_values, label="Speed Fluctuation")
        self.ax_sender.set_title("Transition of IPv6 to IPv4")
        self.ax_sender.set_xlabel("Packet Number")
        self.ax_sender.set_ylabel("Speed")
        self.ax_sender.legend()
        self.canvas_sender.draw()

    def update_receiver_graph(self, packet_num):
        """Update the receiver graph
