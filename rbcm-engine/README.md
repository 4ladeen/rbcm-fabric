# RBCM Engine — Reputation-Based Consensus Management

A lightweight Flask microservice that computes and stores real-time **trust scores** for Hyperledger Fabric nodes using the WANLoc gradient model.

## Overview

The engine exposes a single REST endpoint. The dashboard (and any other consumer) posts the outcome of each peer interaction; the engine returns an updated score clamped to `[0, 100]`.

### Scoring algorithm (WANLoc)

| Event   | Formula |
|---------|---------|
| Success | `score += 5 × gradient × (1 + e^(score/100) / 10)` where `gradient = 1 / (1 + log₁₀(distance + 1))` |
| Failure | `score -= 2 × e^(score/100)` |

Scores start at **50** and are bounded between **0** and **100**.

## Quickstart

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python reputation_engine.py
# → Listening on http://0.0.0.0:5000
```

### Docker

```bash
docker build -t rbcm-engine .
docker run -p 5000:5000 rbcm-engine
```

## API

### `POST /update_score`

**Request body (JSON):**

| Field      | Type    | Default | Description                              |
|------------|---------|---------|------------------------------------------|
| `node_id`  | string  | `"0"`   | Unique identifier of the Fabric node     |
| `success`  | boolean | `false` | Whether the interaction succeeded        |
| `distance` | number  | `1`     | Routing distance (hops / latency proxy)  |

**Response (JSON):**

```json
{ "new_score": 62.4 }
```

**Example:**

```bash
curl -s -X POST http://localhost:5000/update_score \
     -H 'Content-Type: application/json' \
     -d '{"node_id": "peer0.org1", "success": true, "distance": 2}'
```

## Notes

- Scores are held in-memory and reset on restart. For persistence, replace the `scores` dict with a Redis or database backend.
- The service is stateless between requests aside from the in-memory store; it is safe to run behind a load-balancer only if session stickiness is enabled.
