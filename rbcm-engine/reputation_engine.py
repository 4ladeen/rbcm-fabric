import math
from flask import Flask, request, jsonify
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# In-memory score storage
scores = {}

@app.route('/update_score', methods=['POST'])
def update_score():
    data = request.json
    node_id = str(data.get('node_id', '0'))
    success = data.get('success', False)
    distance = data.get('distance', 1)

    # Default start score
    current = scores.get(node_id, 50.0)

    # --- WANLoc MATH ---
    # 1. Reliability (RDF) = e^(score/100)
    rp_proxy = current / 100.0
    rdf = math.exp(rp_proxy)

    if success:
        # 2. Logarithmic Gradient: W = 1 / (1 + log(R+1))
        gradient = 1.0 / (1.0 + math.log10(distance + 1.0))

        # Reward Formula
        new_score = current + (5.0 * gradient * (1 + rdf/10.0))
        app.logger.info(f"Node {node_id} SUCCESS. Gradient: {gradient:.3f}. New Score: {new_score:.2f}")
    else:
        # Penalty Formula
        new_score = current - (2.0 * rdf)
        app.logger.info(f"Node {node_id} FAIL. Penalty applied. New Score: {new_score:.2f}")

    # Clamp between 0-100
    scores[node_id] = max(0.0, min(100.0, new_score))

    return jsonify({"new_score": scores[node_id]})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
