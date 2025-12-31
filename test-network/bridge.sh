#!/bin/bash

echo "==============================================="
echo "   RBCM AUTOMATION BRIDGE IS ACTIVE"
echo "   Listening for 'Committed block' events..."
echo "==============================================="

# The "2>&1" redirects the logs so this script can actually read them
docker logs -f peer0.org1.example.com --tail 0 2>&1 | while read line; do
    
    # 1. Print the log line to the screen (so you can see the chain working)
    echo "$line"
    
    # 2. Check if the line contains "Committed block"
    if [[ "$line" == *"Committed block"* ]]; then
        
        echo -e "\n✅ \033[1;32mBLOCK COMMIT DETECTED! TRIGGERING REPUTATION ENGINE...\033[0m"
        
        # Fire the trigger
        curl -s -o /dev/null -X POST http://localhost:5000/update_score \
        -H "Content-Type: application/json" \
        -d '{"node_id": "peer0.org1", "success": true, "distance": 1}'
        
        echo -e ">> Signal Sent.\n"
    fi
done
