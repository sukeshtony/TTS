import asyncio
import websockets
import json
import time
import argparse

# Default Configuration
WS_URL = "ws://localhost:8000/tts_stream"
CONCURRENT_CONNECTIONS = 1000

TEST_PAYLOAD = {
    "text": "Hello, this is a load test for the new text to speech microservice. We are testing its capacity to handle many connections at once.",
    "voice": "english",
    "type": "regular",
    "id": "load-test-id"
}

async def single_connection(worker_id: int, token: str):
    url = f"{WS_URL}?token={token}"
    try:
        start_time = time.time()
        
        # Connect to the WebSocket
        async with websockets.connect(url, ping_interval=None) as websocket:
            connect_time = time.time() - start_time
            
            # Send TTS request
            await websocket.send(json.dumps(TEST_PAYLOAD))
            
            chunks_received = 0
            first_chunk_time = None
            
            while True:
                response = await websocket.recv()
                data = json.loads(response)
                
                if first_chunk_time is None:
                    first_chunk_time = time.time() - start_time
                
                if "error" in data:
                    print(f"❌ Worker {worker_id}: Error - {data['error']}")
                    break
                    
                if data.get("done"):
                    total_time = time.time() - start_time
                    print(f"✅ Worker {worker_id}: Completed {chunks_received} chunks. "
                          f"(Time to first audio: {first_chunk_time:.3f}s | Total: {total_time:.3f}s)")
                    break
                    
                chunks_received += 1
                
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"❌ Worker {worker_id}: Connection rejected. Is your token valid? (Status: {e.status_code})")
    except Exception as e:
        print(f"❌ Worker {worker_id}: Failed - {e}")

async def main(token: str, connections: int):
    print(f"🚀 Starting {connections} concurrent connections to {WS_URL}...\n")
    start_time = time.time()
    
    # Launch all connections concurrently
    tasks = [single_connection(i, token) for i in range(connections)]
    await asyncio.gather(*tasks)
    
    total_duration = time.time() - start_time
    print(f"\n🏁 Load Test Complete!")
    print(f"Total time to process {connections} simultaneous streams: {total_duration:.3f}s")
    
    # Give the background WebSockets exactly 1 second to cleanly close their connections
    # before Python completely shuts down, preventing the harmless sys.meta_path error.
    print("Cleaning up connections...")
    await asyncio.sleep(1.0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load Test TTS Microservice")
    parser.add_argument("--token", type=str, required=True, help="A valid session token from your Redis database")
    parser.add_argument("--connections", type=int, default=100, help="Number of concurrent connections")
    
    args = parser.parse_args()
    
    # Windows specific fix for asyncio
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    asyncio.run(main(args.token, args.connections))
