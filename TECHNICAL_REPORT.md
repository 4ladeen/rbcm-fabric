[//]: # (SPDX-License-Identifier: CC-BY-4.0)

# `rbcm-fabric` — Comprehensive Technical Report

> **Prepared for:** maintainers of `4ladeen/rbcm-fabric`  
> **Ref analysed:** `main`  
> **Date:** 2026-04-12

---

## Table of Contents

1. [Architecture Map](#1-architecture-map)
2. [Entrypoints and Startup Commands](#2-entrypoints-and-startup-commands)
3. [Dependency / Tooling Matrix](#3-dependency--tooling-matrix)
4. [Custom Code vs. Upstream Fabric Samples](#4-custom-code-vs-upstream-fabric-samples)
5. [Operational Runbook](#5-operational-runbook)
6. [Top 10 Technical Risks and Refactor Priorities](#6-top-10-technical-risks-and-refactor-priorities)

---

## 1. Architecture Map

### Overview

The repository is a **polyglot monorepo** that layers two custom components on top of a near-verbatim clone of [`hyperledger/fabric-samples`](https://github.com/hyperledger/fabric-samples).

```
┌─────────────────────────────────────────────────────────────────────────┐
│  browser / curl                                                          │
│       │                              ┌─────────────────────────────┐    │
│       ▼                              │  rbcm-engine (Python/Flask) │    │
│  dashboard/frontend (static HTML/JS) │  POST /update_score          │    │
│       │                              │  In-memory score store       │    │
│       ▼                              └──────────▲──────────────────┘    │
│  dashboard/backend  (Node.js / Express :4000)   │  HTTP                 │
│    GET  /api/assets   ─────────────────────────►│                       │
│    POST /api/asset    ─────────────────────────►│                       │
│    GET  /api/stats    → docker ps (local shell) │                       │
│         │                                       │                       │
│         │ fabric-network SDK (grpcs)             │                       │
│         ▼                                       │                       │
│  ┌──────────────────────────────────────────┐   │                       │
│  │  Hyperledger Fabric Test Network          │   │                       │
│  │  (Docker Compose / test-network/)         │   │                       │
│  │                                           │   │                       │
│  │  peer0.org1  ──┐                          │   │                       │
│  │  peer0.org2  ──┼── mychannel              │   │                       │
│  │  orderer     ──┘   chaincode: basic        │   │                       │
│  │                    (asset-transfer-basic)  │   │                       │
│  └──────────────────────────────────────────┘   │                       │
│                                                  │                       │
│  off_chain_data/ (Go / TypeScript / Java apps)   │                       │
│    Listens for block events via Fabric Gateway ──┘                       │
└─────────────────────────────────────────────────────────────────────────┘
```

### Component Breakdown

| Layer | Directory | Technology | Role |
|---|---|---|---|
| **On-chain (chaincode)** | `asset-transfer-basic/chaincode-{go,ts,js,java}` | Go / TS / JS / Java | Reference asset CRUD chaincode |
| | `asset-transfer-private-data/chaincode-go` | Go | Private data collections |
| | `asset-transfer-events/chaincode-go` | Go | Event emission |
| | `auction-simple/chaincode-go` | Go | Blind auction logic |
| | `auction-dutch/chaincode-go` | Go | Dutch auction with auditor |
| | `token-erc-20/chaincode-{go,js}` | Go / JS | Fungible token (ERC-20 model) |
| | `token-erc-721/chaincode-{go,js}` | Go / JS | NFT (ERC-721 model) |
| | `token-erc-1155/chaincode-go` | Go | Multi-token (ERC-1155 model) |
| | `token-utxo/chaincode-go` | Go | UTXO token model |
| | `high-throughput/chaincode-go` | Go | Delta-accumulation pattern |
| | `asset-transfer-abac/chaincode-go` | Go | Attribute-based access control |
| | `asset-transfer-sbe/chaincode-{ts,java}` | TS / Java | State-based endorsement |
| | `asset-transfer-ledger-queries/chaincode-{go,js,ts}` | Go / JS / TS | Range & CouchDB queries |
| | `asset-transfer-secured-agreement/chaincode-go` | Go | Secure multi-party transfer |
| **Off-chain services** | `off_chain_data/application-{go,ts,java}` | Go / TS / Java | Block-event listener → local store |
| | `dashboard/backend/server.js` | Node.js | REST bridge to Fabric + system stats |
| | `rbcm-engine/reputation_engine.py` | Python / Flask | WANLoc reputation scoring API |
| **Dashboard / UI** | `dashboard/frontend/` | (empty) | Planned browser UI (gap — see §6) |
| **Network infra** | `test-network/` | Shell / Docker Compose | Local 2-org Fabric network |
| | `test-network-k8s/` | Shell / Kubernetes YAML | K8s-based Fabric network |
| | `test-network-nano-bash/` | Shell / Fabric binaries | Minimal binary-only Fabric network |
| | `full-stack-asset-transfer-guide/` | Shell / TS / K8s | End-to-end workshop scaffold |
| **HSM** | `hardware-security-module/` | Go / TS | PKCS#11 / SoftHSM identity samples |
| **Token SDK** | `token-sdk/` | Go | Zero-knowledge UTXO token SDK |
| **CI** | `.github/workflows/` | GitHub Actions YAML | Multi-matrix lint + integration tests |

### Data Flow Summary

```
Client App / Dashboard
  │
  │ (1) submit/evaluate transaction via fabric-network SDK or Fabric Gateway API
  ▼
Fabric Peer (endorser)
  │  (2) chaincode invoked in peer container (Docker)
  ▼
World State (LevelDB / CouchDB)
  │  (3) block committed to ledger
  ▼
Block Events streamed via Fabric Gateway
  │  (4) off_chain_data app subscribes and writes store.log
  ▼
Off-chain Store (file / external DB — implementation-defined)

Separately:
Dashboard backend  ──HTTP──►  rbcm-engine  (reputation score update)
Dashboard backend  ──shell─►  `docker ps`  (node health stats)
```

---

## 2. Entrypoints and Startup Commands

### Network Bootstrap (`test-network/`)

```bash
# Bring up 2-org network + channel (TLS via Fabric CA, CouchDB state DB)
cd test-network
./network.sh up createChannel -ca -s couchdb

# Deploy a chaincode (e.g. asset-transfer-basic in Go)
./network.sh deployCC -ccn basic -ccp ../asset-transfer-basic/chaincode-go -ccl go

# Add Org3
cd addOrg3 && ./addOrg3.sh up -ca -s couchdb

# Tear down
./network.sh down
```

Key config file: `test-network/network.config` (image tags, channel name, DB, etc.)

### Kubernetes Network (`test-network-k8s/`)

```bash
cd test-network-k8s
./network/network.sh up          # provision K8s namespace + Fabric CAs
./scripts/test_network.sh up     # start peers/orderer
./scripts/channel.sh create      # create channel
./scripts/chaincode.sh deploy    # package and deploy chaincode
```

### Nano-Bash Network (`test-network-nano-bash/`)

```bash
cd test-network-nano-bash
./generate_artifacts.sh           # generate crypto/genesis
./orderer1.sh &                   # start orderer
./peer1.sh &                      # start peers
./join_channel.sh                 # join channel
./install\&approve\&commit_chaincode_peer1.sh   # deploy chaincode
```

### Custom RBCM Engine (`rbcm-engine/`)

```bash
# Direct (requires Flask installed)
cd rbcm-engine
pip install flask
python reputation_engine.py      # listens on 0.0.0.0:5000

# Via Docker
docker build -t rbcm-engine .
docker run -p 5000:5000 rbcm-engine

# API usage
curl -X POST http://localhost:5000/update_score \
  -H "Content-Type: application/json" \
  -d '{"node_id": "peer0.org1", "success": true, "distance": 2}'
```

### Dashboard Backend (`dashboard/backend/`)

```bash
cd dashboard/backend
npm install
node server.js                   # listens on :4000

# Endpoints:
#   GET  http://localhost:4000/api/assets    - query all ledger assets
#   POST http://localhost:4000/api/asset     - create asset on ledger
#   GET  http://localhost:4000/api/stats     - CPU/RAM + Docker node health
```

**Pre-condition:** wallet identity must be set up; `server.js` auto-provisions it
from a hard-coded path `~/new/fabric-samples/test-network/organizations/...` (see §6, Risk #2).

### Sample Chaincode Applications

| Module | Language | Command |
|---|---|---|
| `asset-transfer-basic/application-gateway-go` | Go | `go run .` |
| `asset-transfer-basic/application-gateway-typescript` | TypeScript | `npm install && npm start` |
| `asset-transfer-basic/application-gateway-javascript` | JavaScript | `npm install && npm start` |
| `asset-transfer-basic/application-gateway-java` | Java | `./gradlew run` or `mvn compile exec:java` |
| `off_chain_data/application-go` | Go | `go run . listen` |
| `off_chain_data/application-typescript` | TypeScript | `npm install && npm start listen` |
| `high-throughput/application-go` | Go | `go run . …` |

### CI Entrypoints (`.github/workflows/`)

| Workflow | Trigger | Script |
|---|---|---|
| `test-network-basic.yaml` | push/PR to main | `ci/scripts/run-test-network-basic.sh` |
| `test-network-events.yaml` | push/PR | `ci/scripts/run-test-network-events.sh` |
| `test-network-private.yaml` | push/PR | `ci/scripts/run-test-network-private.sh` |
| `test-network-off-chain.yaml` | push/PR | `ci/scripts/run-test-network-off-chain.sh` |
| `test-network-hsm.yaml` | push/PR | `ci/scripts/run-test-network-hsm.sh` |
| `lint.yaml` | push/PR | `ci/scripts/lint.sh` |
| `test-network-k8s.yaml` | push/PR | K8s cluster setup + chaincode tests |
| `test-fsat.yaml` | push/PR | Full-stack asset transfer workshop |

Linters invoked: `ci/scripts/lint-{go,java,javascript,typescript,shell}.sh`

---

## 3. Dependency / Tooling Matrix

### By Directory

| Directory | Language | Key Manifest | Build Tool | Test Framework | Linter |
|---|---|---|---|---|---|
| `rbcm-engine/` | Python 3.9+ | *(none — inline `pip install flask`)* | pip / Docker | *(none)* | *(none)* |
| `dashboard/backend/` | Node.js (CommonJS) | `package.json` | npm | *(none)* | *(none)* |
| `dashboard/frontend/` | *(empty)* | `package.json` (root) lists bootstrap/react-bootstrap | — | — | — |
| `test-network/` | Bash | `network.config` | Shell | `ci/scripts/run-test-network-*.sh` | shellcheck |
| `test-network-k8s/` | Bash / YAML | Kubernetes manifests in `kube/` | kubectl / kind | `ci/scripts/run-k8s-test-network-*.sh` | shellcheck |
| `test-network-nano-bash/` | Bash | — | Shell | — | shellcheck |
| `asset-transfer-basic/chaincode-go` | Go 1.23 | `go.mod` | `go build` | `go test` | golangci-lint |
| `asset-transfer-basic/application-gateway-typescript` | TypeScript | `package.json` | `tsc` | — | ESLint |
| `asset-transfer-basic/application-gateway-java` | Java 11 | `build.gradle` / `pom.xml` | Gradle / Maven | — | checkstyle |
| `off_chain_data/application-go` | Go 1.23 | `go.mod` | `go build` | — | golangci-lint |
| `off_chain_data/application-typescript` | TypeScript | `package.json` | `tsc` | — | ESLint |
| `off_chain_data/application-java` | Java 11 | `settings.gradle` | Gradle | — | — |
| `high-throughput/chaincode-go` | Go | `go.mod` | `go build` | `go test` | golangci-lint |
| `token-sdk/` | Go | `go.mod` (multiple) | `go build` | — | golangci-lint |
| `hardware-security-module/application-go` | Go | `go.mod` | `go build` | — | golangci-lint |
| `full-stack-asset-transfer-guide/` | TS / Shell / K8s | `package.json` files | npm / kubectl | — | ESLint |

### Runtime Versions (from CI action `test-network-setup`)

| Tool | Version |
|---|---|
| Go | 1.23 |
| Node.js | 20.x |
| JDK | 11.x (Temurin) |
| Fabric | 2.5.13 |
| Fabric CA | 1.5.15 |
| Docker | host-provided (ubuntu-22.04) |

### Key Go Dependencies (representative — `asset-transfer-basic/chaincode-go`)

- `github.com/hyperledger/fabric-contract-api-go` — chaincode contract API
- `github.com/hyperledger/fabric-protos-go-apiv2` — protobuf bindings

### Key Node.js Dependencies (`dashboard/backend/`)

- `fabric-network@^2.2.14` — legacy (pre-Gateway) Fabric SDK
- `express@^5.2.1`
- `systeminformation@^5.28.3` — CPU/RAM metrics
- `dockerode@^4.0.9` — Docker daemon API (imported but not actively used in server.js)
- `js-yaml@^4.1.1` — CCP parsing
- `cors@^2.8.5`

### Root `package.json`

Three UI-only dependencies present at the repo root (oddly placed):
- `bootstrap@^5.3.8`
- `react-bootstrap@^2.10.10`
- `react-icons@^5.5.0`

These are not wired to any build pipeline (no React app, no bundler config) — they appear to be placeholder dependencies for an unfinished frontend.

---

## 4. Custom Code vs. Upstream Fabric Samples

### Custom / Repo-Specific Code

| Directory | Classification | Evidence |
|---|---|---|
| `rbcm-engine/` | **100% custom** | Unique WANLoc reputation math (`reputation_engine.py`); not present in upstream `hyperledger/fabric-samples` |
| `dashboard/backend/server.js` | **Largely custom** | Hard-coded paths to local machine, custom node-stats endpoint with Docker ps integration, custom wallet setup; no equivalent in upstream samples |
| `dashboard/backend/connection-org1.yaml` | **Custom (instance config)** | Contains live TLS certificates, CA URLs for a specific local network instance |
| `dashboard/backend/wallet/appUser.id` | **Custom (DANGER — live credentials)** | Live X.509 certificate + private key for `user1@org1.example.com`; should never be committed |
| `package.json` (root) | **Custom** | Non-standard placement of React/Bootstrap deps with no wiring |
| `rbcm-engine/venv/` | **Committed artifact** | Python virtualenv committed to version control; should be excluded via `.gitignore` |

### Upstream Hyperledger Fabric Samples (near-verbatim)

All of the following directories match the structure and content of [`hyperledger/fabric-samples`](https://github.com/hyperledger/fabric-samples) at the `main` branch with no material customisation:

| Directory | Upstream counterpart |
|---|---|
| `asset-transfer-basic/` | `hyperledger/fabric-samples/asset-transfer-basic` |
| `asset-transfer-private-data/` | `hyperledger/fabric-samples/asset-transfer-private-data` |
| `asset-transfer-events/` | `hyperledger/fabric-samples/asset-transfer-events` |
| `asset-transfer-abac/` | `hyperledger/fabric-samples/asset-transfer-abac` |
| `asset-transfer-sbe/` | `hyperledger/fabric-samples/asset-transfer-sbe` |
| `asset-transfer-ledger-queries/` | `hyperledger/fabric-samples/asset-transfer-ledger-queries` |
| `asset-transfer-secured-agreement/` | `hyperledger/fabric-samples/asset-transfer-secured-agreement` |
| `auction-simple/` | `hyperledger/fabric-samples/auction-simple` |
| `auction-dutch/` | `hyperledger/fabric-samples/auction-dutch` |
| `token-erc-20/` | `hyperledger/fabric-samples/token-erc-20` |
| `token-erc-721/` | `hyperledger/fabric-samples/token-erc-721` |
| `token-erc-1155/` | `hyperledger/fabric-samples/token-erc-1155` |
| `token-utxo/` | `hyperledger/fabric-samples/token-utxo` |
| `token-sdk/` | `hyperledger/fabric-samples/token-sdk` |
| `high-throughput/` | `hyperledger/fabric-samples/high-throughput` |
| `off_chain_data/` | `hyperledger/fabric-samples/off_chain_data` |
| `hardware-security-module/` | `hyperledger/fabric-samples/hardware-security-module` |
| `test-network/` | `hyperledger/fabric-samples/test-network` |
| `test-network-k8s/` | `hyperledger/fabric-samples/test-network-k8s` |
| `test-network-nano-bash/` | `hyperledger/fabric-samples/test-network-nano-bash` |
| `full-stack-asset-transfer-guide/` | `hyperledger/fabric-samples/full-stack-asset-transfer-guide` |
| `test-application/` | `hyperledger/fabric-samples/test-application` |
| `ci/` | `hyperledger/fabric-samples/ci` |
| `.github/` | `hyperledger/fabric-samples/.github` |
| governance files (`CODEOWNERS`, `CONTRIBUTING.md`, `SECURITY.md`, etc.) | `hyperledger/fabric-samples` |

**Key implication:** the majority of the repo (~95% by file count) is upstream sample code. The true custom surface is concentrated in `rbcm-engine/` and `dashboard/backend/`.

---

## 5. Operational Runbook

### Local Development Prerequisites

| Tool | Version | Install command |
|---|---|---|
| Docker Desktop or Docker Engine | 24+ | [docs.docker.com](https://docs.docker.com/get-docker/) |
| Docker Compose | v2 (plugin) | Bundled with Docker Desktop; `sudo apt install docker-compose-plugin` on Linux |
| Go | 1.23+ | `brew install go` / [go.dev/dl](https://go.dev/dl/) |
| Node.js | 20.x LTS | `nvm install 20` |
| JDK | 11 (Temurin) | `sdk install java 11.0.22-tem` (sdkman) |
| Fabric binaries + images | 2.5.13 / CA 1.5.15 | `./install-fabric.sh docker binary` (from samples root) |
| Python | 3.9+ | `brew install python` / `sudo apt install python3` |
| kubectl (optional, K8s path) | 1.28+ | [kubernetes.io](https://kubernetes.io/docs/tasks/tools/) |
| kind or k3s (optional, K8s path) | any recent | `brew install kind` |

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `CHANNEL_NAME` | `mychannel` | Channel to create/join |
| `CC_SRC_LANGUAGE` | `go` | Chaincode language (`go`, `javascript`, `typescript`, `java`) |
| `CC_NAME` | `basic` | Chaincode name on channel |
| `CC_SRC_PATH` | `../asset-transfer-basic/chaincode-go` | Path to chaincode source |
| `CRYPTO` | `cryptogen` | Certificate generation method (`cryptogen` or `ca`) |
| `DATABASE` | `leveldb` | Peer state database (`leveldb` or `couchdb`) |
| `ORDERER_TYPE` | `raft` | Consensus type (`raft` or `bft`) |
| `CONTAINER_CLI` | `docker` | Container CLI (`docker` or `podman`) |
| `FABRIC_CFG_PATH` | auto-set | Path to Fabric configuration |
| `HOME` | shell default | Used to resolve cert paths in `dashboard/backend/server.js` (hardcoded sub-path `~/new/fabric-samples/…`) |

### Network Bootstrapping Steps

```bash
# 1. Install Fabric binaries + Docker images
cd fabric-samples   # repo root
curl -sSL https://bit.ly/2ysbOFE | bash -s -- 2.5.13 1.5.15
# or
./install-fabric.sh docker binary 2.5.13

# 2. Bring up test network
cd test-network
./network.sh up createChannel -ca -s couchdb

# 3. Deploy basic chaincode
./network.sh deployCC -ccn basic \
  -ccp ../asset-transfer-basic/chaincode-go \
  -ccl go -ccv 1 -ccs 1

# 4. Verify with peer CLI
export PATH=${PWD}/../bin:$PATH
export FABRIC_CFG_PATH=${PWD}/../config/
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID="Org1MSP"
export CORE_PEER_TLS_ROOTCERT_FILE=${PWD}/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=${PWD}/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp
export CORE_PEER_ADDRESS=localhost:7051

peer chaincode query -C mychannel -n basic -c '{"Args":["GetAllAssets"]}'
```

### Starting the Dashboard Backend

```bash
# Ensure test network is up and chaincode deployed (see above)
cd dashboard/backend
npm install
node server.js
# Backend available at http://localhost:4000
```

> **Warning:** the cert path in `server.js` is hard-coded to
> `~/new/fabric-samples/test-network/organizations/…`.
> You must either edit this path or symlink your network directory accordingly.

### Starting the RBCM Engine

```bash
cd rbcm-engine
python -m venv venv && source venv/bin/activate
pip install flask
python reputation_engine.py
# API at http://localhost:5000
```

### Running Tests

```bash
# Go unit tests (example: asset-transfer-basic)
cd asset-transfer-basic/chaincode-go
go test ./...

# Lint all languages
./ci/scripts/lint.sh

# Full integration test (requires Docker + Fabric binaries)
cd test-network
../ci/scripts/run-test-network-basic.sh

# CI matrix (GitHub Actions) — runs automatically on push/PR to main
# Workflows: .github/workflows/test-network-basic.yaml etc.
```

### Common Failure Points

| Failure | Cause | Fix |
|---|---|---|
| `Peer binary and configuration files not found` | Fabric binaries not installed | Run `./install-fabric.sh binary 2.5.13` from repo root |
| `Error: Cannot find module 'pkcs11js'` | Missing C compilers for HSM sample | `sudo apt install build-essential python3` |
| `Error setting up wallet` in dashboard | Hard-coded cert path doesn't match local layout | Edit `certPath` / `keyStorePath` in `server.js` |
| `docker: command not found` | Docker not installed | Install Docker Engine |
| `DOCKER_IMAGE_VERSION mismatch` | Local peer binary version ≠ Docker image version | `docker pull hyperledger/fabric-peer:2.5.13` |
| Chaincode container fails to start | Port conflict or old containers remaining | `./network.sh down` then `docker rm -f $(docker ps -aq)` |
| `reputation_engine.py` scores reset on restart | In-memory store, no persistence | Planned fix: persist scores to file or Redis (see Risk #5) |

---

## 6. Top 10 Technical Risks and Refactor Priorities

### Risk 1 — Live Private Key Committed to Repository

| | |
|---|---|
| **Severity** | 🔴 Critical |
| **File** | `dashboard/backend/wallet/appUser.id` |
| **Evidence** | File contains a PEM-encoded X.509 certificate and PKCS#8 private key for `user1@org1.example.com`, committed in plaintext to the public repository. |
| **Rationale** | Anyone with read access can extract the private key and impersonate the enrolled identity on any network using the same CA. Even if this is a test CA, normalising credential commits is a dangerous pattern. |
| **Remediation** | 1. Add `dashboard/backend/wallet/` to `.gitignore` immediately. 2. Rotate the enrolled identity via `fabric-ca-client reenroll`. 3. Use `git filter-repo` or BFG Repo Cleaner to purge the key from history. 4. Generate the wallet at runtime (the `setupWallet()` function in `server.js` already handles this if certs are in the expected path). |

---

### Risk 2 — Hard-Coded Developer Machine Paths

| | |
|---|---|
| **Severity** | 🔴 High |
| **File** | `dashboard/backend/server.js` lines 17–18 |
| **Evidence** | `certPath = path.resolve(process.env.HOME, 'new/fabric-samples/test-network/organizations/…')` — assumes the Fabric network lives at `~/new/fabric-samples/`. |
| **Rationale** | The backend will fail for any other user or machine, making the dashboard non-portable and useless in CI or any shared environment. |
| **Remediation** | Replace the hard-coded path with an environment variable, e.g. `FABRIC_SAMPLES_PATH`, defaulting to a sensible relative path. Example: `const certPath = path.resolve(process.env.FABRIC_SAMPLES_PATH || path.join(__dirname, '../../..', 'test-network'), 'organizations/…');` |

---

### Risk 3 — Python Virtualenv Committed to Source Control

| | |
|---|---|
| **Severity** | 🟠 High |
| **File** | `rbcm-engine/venv/` (~50 MB of compiled Python packages) |
| **Evidence** | The directory `rbcm-engine/venv/` is fully tracked by Git (confirmed by `find` output showing `.pyc` files and dist-info directories). |
| **Rationale** | Virtualenvs are environment-specific, non-portable, and bloat the repository significantly. They contain binary `.pyc` files and platform-specific build artifacts. |
| **Remediation** | 1. Add `rbcm-engine/venv/` (or repo-wide `/venv/`) to `.gitignore`. 2. Remove it from Git history: `git rm -r --cached rbcm-engine/venv/`. 3. Add a `requirements.txt` documenting the `flask` dependency. |

---

### Risk 4 — No `requirements.txt` for `rbcm-engine`

| | |
|---|---|
| **Severity** | 🟠 High |
| **File** | `rbcm-engine/` (absence) |
| **Evidence** | `Dockerfile` runs `pip install flask` but there is no `requirements.txt` or `pyproject.toml` pinning versions. |
| **Rationale** | Without pinned dependencies, any future `pip install` may pull incompatible versions (e.g. Flask 3.x breaking changes vs 2.x). Dockerfile and local dev have no reproducibility guarantee. |
| **Remediation** | `pip freeze > rbcm-engine/requirements.txt`, add `COPY requirements.txt .` + `RUN pip install -r requirements.txt` in the Dockerfile, pin Flask to a specific minor version (e.g. `flask==3.0.*`). |

---

### Risk 5 — In-Memory Score Store in RBCM Engine

| | |
|---|---|
| **Severity** | 🟠 High |
| **File** | `rbcm-engine/reputation_engine.py` |
| **Evidence** | `scores = {}` is a module-level Python dict. All reputation scores are lost on process restart or container redeploy. |
| **Rationale** | The RBCM Engine is the core value-add of this repo. Ephemeral state makes it unsuitable for any production or long-running deployment. A restart wipes all accumulated reputation data. |
| **Remediation** | Persist scores to a simple key-value store. Minimal fix: write/read a JSON file (`scores.json`) on every update. Better: use Redis or SQLite. For Fabric-native persistence, scores could be written back as chaincode state via a separate transaction. |

---

### Risk 6 — Dashboard Frontend Is Empty

| | |
|---|---|
| **Severity** | 🟡 Medium |
| **File** | `dashboard/frontend/` (empty directory) |
| **Evidence** | `ls dashboard/frontend/` returns nothing; root `package.json` declares React/Bootstrap deps but has no `src/`, `public/`, or bundler config. |
| **Rationale** | The repo advertises a dashboard UI but the frontend is completely absent. The root `package.json` React deps are orphaned. |
| **Remediation** | Either: (a) scaffold a minimal React app (`npx create-react-app dashboard/frontend`) wired to the backend API, or (b) build a plain HTML/JS static UI with the already-imported Bootstrap. Move the root `package.json` deps into the frontend sub-package. |

---

### Risk 7 — `fabric-network` SDK Version Is Deprecated

| | |
|---|---|
| **Severity** | 🟡 Medium |
| **File** | `dashboard/backend/package.json` |
| **Evidence** | `"fabric-network": "^2.2.14"` — the legacy `fabric-network` (v2) SDK was superseded by the Fabric Gateway client API (`@hyperledger/fabric-gateway`) in Fabric v2.4+. All other sample applications in this repo already use the new Gateway API. |
| **Rationale** | The old SDK has known limitations (event service, connection profile handling) and will receive no new features or security backports. |
| **Remediation** | Migrate `dashboard/backend/server.js` to use `@hyperledger/fabric-gateway` (Node.js implementation). Reference: `asset-transfer-basic/application-gateway-typescript/src/app.ts` in this same repo. |

---

### Risk 8 — No Test Coverage for Custom Components

| | |
|---|---|
| **Severity** | 🟡 Medium |
| **Files** | `rbcm-engine/reputation_engine.py`, `dashboard/backend/server.js` |
| **Evidence** | `dashboard/backend/package.json` scripts: `"test": "echo \"Error: no test specified\" && exit 1"`. No test files exist in `rbcm-engine/`. |
| **Rationale** | The WANLoc reputation algorithm contains non-trivial floating-point math that is easy to regress. The dashboard backend interacts with Fabric and Docker and has multiple error paths. Without tests, changes are high-risk. |
| **Remediation** | For `rbcm-engine/`: add `pytest` tests for score clamping, reward/penalty formulas, and edge cases (distance=0, repeated failures). For dashboard backend: add `jest` or `supertest` integration tests with a mocked `fabric-network` and mocked `exec`. |

---

### Risk 9 — Embedded TLS Certificate in Connection Profile

| | |
|---|---|
| **Severity** | 🟡 Medium |
| **File** | `dashboard/backend/connection-org1.yaml` |
| **Evidence** | The file contains inline PEM-encoded TLS CA certificates for `org1.example.com` and `ca.org1.example.com`. These are tied to the specific local test network instance that was running during development. |
| **Rationale** | The embedded cert will expire (notAfter: 2040-12-25 from the certificate data), and rotating the network means the connection profile becomes stale. Storing instance-specific runtime config in source control conflates code with environment state. |
| **Remediation** | Treat `connection-org1.yaml` as a generated artefact. Exclude it from source control (`.gitignore`) and generate it at runtime using `test-network/organizations/ccp-generate.sh` which is already present in the repo. |

---

### Risk 10 — Monorepo Structure Mixes Upstream Samples and Custom Platform Code

| | |
|---|---|
| **Severity** | 🟡 Medium / Architectural |
| **Scope** | Entire repository |
| **Evidence** | ~95% of the repo is a direct copy of `hyperledger/fabric-samples`. Custom components (`rbcm-engine`, `dashboard`) are buried at the same level as 20+ sample directories. |
| **Rationale** | This structure creates maintenance challenges: upstream security patches and new samples must be manually backported (no upstream remote is configured), reviewers cannot easily distinguish custom code from boilerplate, and CI runs full sample test suites even when only dashboard code changes. |
| **Remediation** | Choose one of: (a) **submodule approach** — keep `hyperledger/fabric-samples` as a git submodule and place custom code in a top-level `platform/` or `rbcm/` directory; (b) **separate repos** — move `rbcm-engine` and `dashboard` to their own repositories and reference the test network as a dev dependency; (c) **sparse checkout** — keep only the sample directories actively used in the custom platform and prune the rest. In all cases, configure an upstream remote for `hyperledger/fabric-samples` to simplify future patch merges: `git remote add upstream https://github.com/hyperledger/fabric-samples`. |

---

## Appendix: Gap Summary

| Topic | Gap |
|---|---|
| Frontend implementation | `dashboard/frontend/` is empty; no HTML, JS, or React files present |
| RBCM Engine persistence | Scores are in-memory only |
| RBCM Engine documentation | No README in `rbcm-engine/` explaining WANLoc algorithm, API contract, or deployment model |
| Dashboard documentation | No README in `dashboard/` |
| Integration between rbcm-engine and Fabric | No evidence of the reputation engine receiving data from Fabric block events; appears to be manually called via HTTP |
| Upstream sync policy | No `upstream` remote or documented process for merging updates from `hyperledger/fabric-samples` |
| Production deployment | No Helm chart, docker-compose for the full custom stack (rbcm-engine + dashboard backend), or environment-specific config management |
