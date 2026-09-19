import json
import requests
import time
import subprocess
import os

def run_tests():
    # 1. Start the server
    print("Starting server on localhost:8000...")
    # Use venv python to start uvicorn
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    server_process = subprocess.Popen(
        [r"venv\Scripts\python.exe", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for server to start
    time.sleep(10)
    
    try:
        # 2. Get OpenAPI schema to find endpoints
        print("Fetching OpenAPI schema...")
        resp = requests.get("http://127.0.0.1:8000/openapi.json")
        if resp.status_code != 200:
            print("Failed to get OpenAPI schema!")
            return
            
        schema = resp.json()
        paths = schema.get("paths", {})
        
        results = {}
        
        # 3. Test each endpoint
        for path, methods in paths.items():
            for method, details in methods.items():
                tags = details.get("tags", ["Untagged"])
                module_name = tags[0]
                
                if module_name not in results:
                    results[module_name] = {"working": [], "failing": []}
                
                # We will just test the endpoint with a dummy request to see what status code we get.
                # Since we don't have auth/payloads, we expect 401, 403, 404, 405, 422, or 2xx.
                # If we get 500, it means it's failing.
                url = f"http://127.0.0.1:8000{path}"
                
                try:
                    # Replace path variables with dummy values
                    test_url = url.replace("{", "").replace("}", "")
                    
                    if method.lower() == "get":
                        res = requests.get(test_url)
                    elif method.lower() == "post":
                        res = requests.post(test_url, json={})
                    elif method.lower() == "put":
                        res = requests.put(test_url, json={})
                    elif method.lower() == "delete":
                        res = requests.delete(test_url)
                    else:
                        continue
                        
                    status = res.status_code
                    # 500 range indicates an unhandled server error
                    if status >= 500:
                        results[module_name]["failing"].append(f"{method.upper()} {path} (Status: {status})")
                    else:
                        results[module_name]["working"].append(f"{method.upper()} {path} (Status: {status})")
                        
                except Exception as e:
                    results[module_name]["failing"].append(f"{method.upper()} {path} (Error: {str(e)})")
                    
        # 4. Generate report
        print("\n================ SYSTEM TEST REPORT ================")
        for module, data in results.items():
            print(f"\n--- Module: {module} ---")
            print(f"Working ({len(data['working'])}):")
            for item in data["working"][:5]:
                print(f"  - {item}")
            if len(data["working"]) > 5:
                print(f"  - ... and {len(data['working']) - 5} more")
                
            print(f"Failing ({len(data['failing'])}):")
            for item in data["failing"]:
                print(f"  - {item}")
                
        # Write to file
        with open("scratch/test_report.md", "w") as f:
            f.write("# System Test Report\n\n")
            for module, data in results.items():
                f.write(f"## Module: {module}\n")
                f.write(f"**Working:** {len(data['working'])} endpoints\n")
                for item in data['working']:
                    f.write(f"- {item}\n")
                f.write(f"\n**Failing:** {len(data['failing'])} endpoints\n")
                for item in data['failing']:
                    f.write(f"- {item}\n")
                f.write("\n")
                
    finally:
        # Kill the server
        server_process.kill()
        print("Server stopped.")

if __name__ == "__main__":
    run_tests()
