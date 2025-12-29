const express = require('express');
const cors = require('cors');
const { Gateway, Wallets } = require('fabric-network');
const path = require('path');
const fs = require('fs');
const yaml = require('js-yaml');
const si = require('systeminformation');
const { exec } = require('child_process');
const app = express();

app.use(cors());
app.use(express.json());

const PORT = 4000;

// --- FABRIC CONFIGURATION ---
const channelName = 'mychannel';
const chaincodeName = 'basic';
const mspOrg1 = 'Org1MSP';
const walletPath = path.join(__dirname, 'wallet');
const org1UserId = 'appUser';
const ccpPath = path.resolve(__dirname, 'connection-org1.yaml');

// *** FIXED PATH: Points to cert.pem (standard for new Fabric networks) ***
const certPath = path.resolve(process.env.HOME, 'new/fabric-samples/test-network/organizations/peerOrganizations/org1.example.com/users/User1@org1.example.com/msp/signcerts/cert.pem');
const keyStorePath = path.resolve(process.env.HOME, 'new/fabric-samples/test-network/organizations/peerOrganizations/org1.example.com/users/User1@org1.example.com/msp/keystore');

function getPrivateKeyPath() {
    const files = fs.readdirSync(keyStorePath);
    const keyFile = files.find(f => f.endsWith('_sk'));
    return path.join(keyStorePath, keyFile);
}

async function setupWallet() {
    try {
        const wallet = await Wallets.newFileSystemWallet(walletPath);
        const identity = await wallet.get(org1UserId);
        if (!identity) {
            const cert = fs.readFileSync(certPath).toString();
            const key = fs.readFileSync(getPrivateKeyPath()).toString();
            const x509Identity = {
                credentials: { certificate: cert, privateKey: key },
                mspId: mspOrg1,
                type: 'X.509',
            };
            await wallet.put(org1UserId, x509Identity);
        }
        return wallet;
    } catch (error) {
        console.error('Error setting up wallet:', error);
    }
}

// --- API ENDPOINTS ---

app.get('/api/assets', async (req, res) => {
    try {
        const wallet = await setupWallet();
        const gateway = new Gateway();
        const ccp = yaml.load(fs.readFileSync(ccpPath, 'utf8'));
        await gateway.connect(ccp, { wallet, identity: org1UserId, discovery: { enabled: true, asLocalhost: true } });
        const network = await gateway.getNetwork(channelName);
        const contract = network.getContract(chaincodeName);
        const result = await contract.evaluateTransaction('GetAllAssets');
        await gateway.disconnect();
        res.json(JSON.parse(result.toString()));
    } catch (error) {
        console.error(error);
        res.json([]);
    }
});

app.post('/api/asset', async (req, res) => {
    try {
        const { id, color, size, owner, value } = req.body;
        const wallet = await setupWallet();
        const gateway = new Gateway();
        const ccp = yaml.load(fs.readFileSync(ccpPath, 'utf8'));
        await gateway.connect(ccp, { wallet, identity: org1UserId, discovery: { enabled: true, asLocalhost: true } });
        const network = await gateway.getNetwork(channelName);
        const contract = network.getContract(chaincodeName);
        await contract.submitTransaction('CreateAsset', id, color, size, owner, value);
        await gateway.disconnect();
        res.json({ message: `Success` });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// --- SYSTEM STATS (STRICT 3-NODE FILTER) ---
app.get('/api/stats', async (req, res) => {
    try {
        const cpu = await si.currentLoad();
        const mem = await si.mem();
        
        // FILTER: Only show peer0.org1, peer0.org2, and orderer. Ignore 'dev-' containers.
        exec('docker ps --format "{{.Names}}" | grep -E "^peer0.org|^orderer"', (error, stdout, stderr) => {
            let peerList = [];
            
            if (!error && stdout) {
                const rawNames = stdout.trim().split('\n');
                peerList = rawNames.map(name => {
                    let cleanName = name;
                    let type = "Node";
                    
                    if (name.includes('orderer')) {
                        cleanName = "Orderer Authority";
                        type = "Orderer";
                    }
                    else if (name.includes('org1')) cleanName = "Org1 Peer";
                    else if (name.includes('org2')) cleanName = "Org2 Peer";
                    
                    // Scores: Orderer is highest, Peers vary slightly
                    let score = 98.0; 
                    if (type === "Orderer") score = 100.0;
                    else score = 95 + (Math.random() * 3); 

                    return { 
                        id: name,
                        name: cleanName, 
                        type: type,
                        score: score.toFixed(1)
                    };
                });
            }

            res.json({
                cpu: cpu.currentLoad.toFixed(2),
                ramUsed: (mem.active / 1024 / 1024 / 1024).toFixed(2),
                ramTotal: (mem.total / 1024 / 1024 / 1024).toFixed(2),
                nodeCount: peerList.length,
                peers: peerList
            });
        });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.listen(PORT, () => {
    console.log(`✅ Backend running on port ${PORT}`);
});
