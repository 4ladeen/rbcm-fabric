[//]: # (SPDX-License-Identifier: CC-BY-4.0)

# Deep Technical Analysis — rbcm-fabric

This document is the result of the full file-level deep scan of the `4ladeen/rbcm-fabric` repository. It covers architecture, custom additions, entry points, run commands, and identified risks.

---

## 1. Repository Identity

| Field | Value |
|---|---|
| Upstream | [`hyperledger/fabric-samples`](https://github.com/hyperledger/fabric-samples) |
| Fork owner | `4ladeen` |
| Fork name | `rbcm-fabric` |
| Custom prefix | `rbcm` (Reputation-Based Consensus Mechanism) |
| Base Fabric version | 2.x (images tagged `default` / latest in `network.config`) |

---

## 2. High-Level Architecture

```
                          ┌─────────────────────────────────────┐
                          │          Hyperledger Fabric           │
                          │  peer0.org1  peer0.org2  orderer     │
                          │  channel: mychannel                   │
                          │  chaincode: basic (asset-transfer)    │
                          └──────────────┬──────────────────────-┘
                                         │ Docker logs (block commits)
                                         ▼
                          ┌─────────────────────────────┐
                          │  bridge.sh  (test-network/)  │
                          │  Watches peer0.org1 logs     │
                          │  Fires HTTP POST on commit   │
                          └──────────────┬───────────────┘
                                         │ POST /update_score
                                         ▼
                          ┌─────────────────────────────┐
                          │  rbcm-engine  (Python/Flask) │
                          │  port 5000                   │
                          │  WANLoc reputation math      │
                          └─────────────────────────────┘

                          ┌─────────────────────────────┐
                          │  dashboard/backend  (Node.js) │
                          │  port 4000                   │
                          │  Fabric Gateway + sys stats  │
                          └─────────────────────────────┘
                          ┌─────────────────────────────┐
                          │  dashboard/frontend          │
                          │  (empty — scaffold only)     │
                          └─────────────────────────────┘
```

---

## 3. Custom Additions vs. Upstream

| Path | Status | Description |
|---|---|---|
| `dashboard/` | **Custom** | Node.js/Express backend + frontend skeleton (not in upstream) |
| `dashboard/backend/server.js` | **Custom** | REST API bridging Fabric ledger + system stats |
| `dashboard/backend/connection-org1.yaml` | **Custom** | Hardcoded TLS certs for a specific local test run |
| `dashboard/backend/wallet/appUser.id` | **Custom** | Enrolled identity credential (committed to repo — see §6) |
| `rbcm-engine/` | **Custom** | Python Flask microservice implementing WANLoc reputation scoring |
| `rbcm-engine/reputation_engine.py` | **Custom** | Reputation engine — core logic |
| `rbcm-engine/Dockerfile` | **Custom** | Container definition for the engine |
| `test-network/bridge.sh` | **Custom** | Shell automation that tails peer logs and fires HTTP triggers |
| `test-network/network.config` | **Custom** | Overrides default network parameters (channel, chaincode name, etc.) |
| Everything else | **Upstream** | Standard `fabric-samples` modules (chaincode, test-network, token-sdk, etc.) |

---

## 4. Entry Points and Run Commands

### 4.1 Fabric Test Network

```bash
cd test-network

# Start network + create channel + deploy basic chaincode
./network.sh up createChannel -c mychannel -ca
./network.sh deployCC -ccn basic -ccp ../asset-transfer-basic/chaincode-go -ccl go
```

### 4.2 RBCM Reputation Engine

**Option A — direct (requires Python 3.9+ and Flask):**
```bash
cd rbcm-engine
pip install flask
python reputation_engine.py
# Listening on http://0.0.0.0:5000
```

**Option B — Docker:**
```bash
cd rbcm-engine
docker build -t rbcm-engine .
docker run -p 5000:5000 rbcm-engine
```

**API:**
```
POST /update_score
Content-Type: application/json
Body: {"node_id": "peer0.org1", "success": true, "distance": 1}

Response: {"new_score": 97.42}
```

### 4.3 Automation Bridge

Requires the test network to be running and the reputation engine to be listening on port 5000.

```bash
cd test-network
bash bridge.sh
# Tails peer0.org1.example.com Docker logs
# Fires POST /update_score on every "Committed block" event
```

### 4.4 Dashboard Backend

```bash
cd dashboard/backend
npm install
node server.js
# Listening on http://localhost:4000
```

**API endpoints:**

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/assets` | Returns all assets from the ledger |
| `POST` | `/api/asset` | Creates a new asset (`id`, `color`, `size`, `owner`, `value`) |
| `GET` | `/api/stats` | Returns CPU load, RAM usage, and active peer/orderer list with scores |

### 4.5 Full Start-Up Sequence

```bash
# Terminal 1 — Fabric network
cd test-network && ./network.sh up createChannel -c mychannel -ca
./network.sh deployCC -ccn basic -ccp ../asset-transfer-basic/chaincode-go -ccl go

# Terminal 2 — Reputation engine
cd rbcm-engine && python reputation_engine.py

# Terminal 3 — Automation bridge
cd test-network && bash bridge.sh

# Terminal 4 — Dashboard backend
cd dashboard/backend && node server.js
```

---

## 5. Reputation Engine — WANLoc Math

The scoring algorithm in `rbcm-engine/reputation_engine.py` implements the following formulas:

- **Starting score:** 50.0 (per node, in-memory)
- **RDF (Reliability Distribution Factor):** `e^(score/100)`
- **On success:**
  - Gradient `W = 1 / (1 + log10(distance + 1))`
  - `new_score = score + 5 × W × (1 + RDF/10)`
- **On failure:**
  - `new_score = score − 2 × RDF`
- **Bounds:** Clamped to `[0, 100]`

Scores are held in memory (`scores = {}`) — they reset on process restart.

---

## 6. Risks and Issues

### 🔴 Critical

| # | File | Issue |
|---|---|---|
| 1 | `dashboard/backend/wallet/appUser.id` | **Live X.509 private key committed to version control.** Anyone with repo access can use this identity to interact with the network. Rotate the certificate and remove the file from history. |
| 2 | `dashboard/backend/connection-org1.yaml` | Hardcoded TLS CA certificates issued for a specific test run. They will not work on any other machine and expire 2040-12-25. |

### 🟠 High

| # | File | Issue |
|---|---|---|
| 3 | `dashboard/backend/server.js` (line 97) | Uses `exec('docker ps ...')` with shell interpolation — this is a command injection risk if any external input ever reaches that code path. |
| 4 | `rbcm-engine/reputation_engine.py` | Scores are in-memory only — all history is lost on restart. No persistence layer. |
| 5 | `dashboard/backend/server.js` (lines 113–116) | Node reputation scores are randomised on every `/api/stats` call (`95 + Math.random() * 3`) instead of reading from the reputation engine. The bridge and engine are effectively disconnected from the dashboard. |

### 🟡 Medium

| # | File | Issue |
|---|---|---|
| 6 | `dashboard/frontend/` | Directory is empty — the UI has no implementation. |
| 7 | `test-network/bridge.sh` | Hardcodes `peer0.org1` as the only node being tracked; other nodes are never scored. |
| 8 | `rbcm-engine/Dockerfile` | No `requirements.txt` — only `flask` is installed. If dependencies grow the file will need updating. |
| 9 | `dashboard/backend/server.js` (line 25) | Certificate path is hardcoded to `$HOME/new/fabric-samples/...` — will fail on any machine where the network was not set up in that exact path. |

### 🟢 Low / Informational

| # | File | Issue |
|---|---|---|
| 10 | `rbcm-engine/venv/` | Python virtual environment committed to the repo — increases repo size and should be added to `.gitignore`. |
| 11 | All custom services | No health-check endpoints, no structured logging, no unit tests. |

---

## 7. Upstream Modules (Reference)

The following directories are unchanged from `hyperledger/fabric-samples` and are available for use:

- `asset-transfer-basic` — basic CRUD chaincode (Go, JS, TS, Java) + REST API samples
- `asset-transfer-events` / `asset-transfer-ledger-queries` / `asset-transfer-private-data` / `asset-transfer-sbe` / `asset-transfer-secured-agreement` / `asset-transfer-abac` — advanced chaincode patterns
- `token-erc-20` / `token-erc-721` / `token-erc-1155` / `token-utxo` / `token-sdk` — token samples
- `auction-simple` / `auction-dutch` — auction smart contracts
- `test-network` — Docker Compose network (2 orgs, 1 orderer, CA)
- `test-network-k8s` — Kubernetes version of the test network
- `test-network-nano-bash` — minimal bash-only test network
- `full-stack-asset-transfer-guide` — end-to-end workshop with Microfab
- `off_chain_data` — block event → off-chain DB pattern
- `hardware-security-module` — HSM integration examples
- `high-throughput` — high-throughput chaincode pattern
