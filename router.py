import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# CORS is crucial if your team is hitting this gateway from local React or Vite dev servers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# A shared async client without any proxy configuration. 
# The OS network layer (via your manual VPN) handles the actual routing to AWS.
http_client = httpx.AsyncClient()

@app.api_route("/{target_ip}/{target_port}/{target_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def gateway_handler(request: Request, target_ip: str, target_port: int, target_path: str):
    
    # Reconstruct the target AWS URL. 
    # (Assuming HTTP for internal AWS services. If HTTPS is needed, this can be parameterized).
    aws_url = f"http://{target_ip}:{target_port}/{target_path}"
    
    # Append any query parameters
    query_params = request.url.query
    if query_params:
        aws_url += f"?{query_params}"

    # Extract the payload/body
    body = await request.body()

    # Forward headers, but drop 'host' so httpx sets the correct AWS host
    headers = dict(request.headers)
    headers.pop("host", None) 

    try:
        # The request is made natively; the desktop's VPN catches it and routes it to AWS
        aws_response = await http_client.request(
            method=request.method,
            url=aws_url,
            headers=headers,
            content=body,
            timeout=30.0
        )

        return Response(
            content=aws_response.content,
            status_code=aws_response.status_code,
            headers=dict(aws_response.headers)
        )
        
    except httpx.ConnectTimeout:
        return Response(content="Gateway Error: Connection Timed Out. Is the desktop VPN connected?", status_code=504)
    except httpx.RequestError as exc:
        return Response(content=f"Gateway Error: {str(exc)}", status_code=502)

# Run with: uvicorn filename:app --host 0.0.0.0 --port 8000
