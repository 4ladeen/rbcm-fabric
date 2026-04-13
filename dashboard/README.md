# RBCM Dashboard — Backend API

An Express.js backend that bridges the Hyperledger Fabric test network and the monitoring UI.  
It exposes three REST endpoints consumed by the frontend.

## Prerequisites

| Tool                | Version |
|---------------------|---------|
| Node.js             | ≥ 18    |
| Hyperledger Fabric  | 2.x test-network running |
| Docker              | accessible to the process running the server |

## Configuration

Two path constants in `server.js` must match your local Fabric deployment:

```js
const certPath   = path.resolve(process.env.HOME,
  'new/fabric-samples/test-network/organizations/peerOrganizations/org1.example.com/users/User1@org1.example.com/msp/signcerts/cert.pem');
const keyStorePath = path.resolve(process.env.HOME,
  'new/fabric-samples/test-network/organizations/peerOrganizations/org1.example.com/users/User1@org1.example.com/msp/keystore');
```

Update these to point to your actual certificate and key material before starting the server.

> ⚠️ **Never commit wallet files or private key material** to source control.  
> The `wallet/` directory is listed in `.gitignore`. Regenerate wallet identities locally using `enrollAdmin`/`registerUser` scripts.

## Quickstart

```bash
cd dashboard/backend
npm install
node server.js
# → Backend running on port 4000
```

## API Endpoints

### `GET /api/assets`

Returns all assets currently stored on the `mychannel` ledger (`basic` chaincode).

```json
[
  { "ID": "asset1", "Color": "blue", "Size": 5, "Owner": "Tomoko", "AppraisedValue": 300 }
]
```

### `POST /api/asset`

Creates a new asset on the ledger.

**Request body:**

```json
{ "id": "asset7", "color": "red", "size": 10, "owner": "Alice", "value": 500 }
```

### `GET /api/stats`

Returns system metrics and the list of running Fabric nodes (filtered to `peer0.org*` and `orderer` containers).

```json
{
  "cpu": "12.34",
  "ramUsed": "3.21",
  "ramTotal": "15.55",
  "nodeCount": 3,
  "peers": [
    { "id": "peer0.org1.example.com", "name": "Org1 Peer", "type": "Node", "score": "96.7" }
  ]
}
```

## Dependencies

| Package              | Purpose                                  |
|----------------------|------------------------------------------|
| `express`            | HTTP server                              |
| `cors`               | Cross-origin headers for frontend        |
| `fabric-network`     | Fabric Gateway SDK (wallet, contracts)   |
| `js-yaml`            | Parses the `connection-org1.yaml` CCP    |
| `systeminformation`  | CPU / RAM metrics                        |
| `dockerode`          | (declared, not yet used)                 |
