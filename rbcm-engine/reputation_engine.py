import math
import threading
import time
import random
from flask import Flask, request, jsonify
from flask_cors import CORS
import logging

app = Flask(__name__)
CORS(app) # Enable Cross-Origin Resource Sharing for the Dashboard
logging.basicConfig(level=logging.INFO)

# --- STATE MANAGEMENT ---
real_nodes = {}    # Stores data from Real Docker Containers
ghost_nodes = {}   # Stores data for the Virtual Nodes
rogue_mode_active = False

def init_ghost_nodes():
    """Initialize 90 ghost nodes (IDs 11-100) to supplement the 10 Real nodes"""
    for i in range(11, 101):
        node_id = f"node-{i:03d}-virtual"
        # Initialize with realistic "Good" scores (50-70)
        ghost_nodes[node_id] = random.uniform(50.0, 70.0)

init_ghost_nodes()

# --- CORE MATH (The Thesis Logic) ---
def calculate_score(current, success, distance=1):
    # 1. Reliability Density Function (RDF)
    rp_proxy = current / 100.0
    rdf = math.exp(rp_proxy)
    
    if success:
        # 2. Logarithmic Gradient (WanLoc)
        gradient = 1.0 / (1.0 + math.log10(distance + 1.0))
        # Reward Formula
        return current + (5.0 * gradient * (1 + rdf/10.0))
    else:
        # Penalty Formula
        return current - (2.0 * rdf)

# --- VIRTUAL NODE SIMULATION LOOP ---
def simulation_loop():
    global rogue_mode_active
    while True:
        # Pick a random virtual node to update
        if not ghost_nodes: return
        target_id = random.choice(list(ghost_nodes.keys()))
        
        # ROGUE MODE LOGIC: If active, nodes start failing randomly
        if rogue_mode_active:
             # 80% chance of failure when Rogue Mode is on
             success = random.random() > 0.8 
        else:
             # 95% chance of success normally
             success = random.random() > 0.05 
        
        current = ghost_nodes[target_id]
        new_score = calculate_score(current, success)
        
        # Clamp score between 0 and 100
        ghost_nodes[target_id] = max(0.0, min(100.0, new_score))
        
        time.sleep(0.05) # Update ~20 virtual nodes per second

# Start the simulation in background
threading.Thread(target=simulation_loop, daemon=True).start()

# --- API ENDPOINTS ---

@app.route('/update_score', methods=['POST'])
def update_score_real():
    """Called by Real Hyperledger Fabric Orderer"""
    data = request.json
    node_id = str(data.get('node_id', '0'))
    success = data.get('success', False)
    
    current = real_nodes.get(node_id, 50.0)
    new_score = calculate_score(current, success)
    real_nodes[node_id] = max(0.0, min(100.0, new_score))
    
    return jsonify({"new_score": real_nodes[node_id]})

@app.route('/get_network_state', methods=['GET'])
def get_state():
    """Merges Real + Virtual nodes for the Dashboard"""
    full_network = {**real_nodes, **ghost_nodes}
    # Convert to list
    node_list = [{"id": k, "score": float(f"{v:.2f}"), "type": "Virtual" if "virtual" in k else "Physical"} 
                 for k, v in full_network.items()]
    # Sort: Highest score first
    node_list.sort(key=lambda x: x['score'], reverse=True)
    return jsonify(node_list)

@app.route('/god/sybil_attack', methods=['POST'])
def trigger_sybil():
    """Injects 50 malicious fake nodes instantly"""
    for i in range(50):
        fake_id = f"sybil-{random.randint(1000,9999)}-attack"
        ghost_nodes[fake_id] = 50.0 # Start neutral
    return jsonify({"status": "Sybil Attack Started", "count": len(ghost_nodes)})

@app.route('/god/toggle_rogue', methods=['POST'])
def toggle_rogue():
    """Forces virtual nodes to start failing"""
    global rogue_mode_active
    rogue_mode_active = not rogue_mode_active
    status = "Active" if rogue_mode_active else "Inactive"
    return jsonify({"status": f"Rogue Mode {status}"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
