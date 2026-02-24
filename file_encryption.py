import os
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import anyio
from fastapi.responses import StreamingResponse

async def decrypted_streamer_ctr_async(file_path: str, chunk_size=64 * 1024):
    algorithm = algorithms.AES(MASTER_KEY)
    
    # Use anyio to open the file asynchronously
    async with await anyio.open_file(file_path, "rb") as f:
        # 1. Read the nonce (blocking-free)
        nonce = await f.read(16)
        cipher = Cipher(algorithm, modes.CTR(nonce), backend=default_backend())
        decryptor = cipher.decryptor()

        # 2. Yield decrypted chunks
        while chunk := await f.read(chunk_size):
            # Since decryptor.update is CPU-bound, we wrap it in a threadpool
            # to prevent it from blocking the loop for large chunks
            decrypted_chunk = await run_in_threadpool(decryptor.update, chunk)
            yield decrypted_chunk
        
        yield decryptor.finalize()

async def encrypt_and_save_ctr_async(upload_file, dest_path):
    nonce = os.urandom(16)
    algorithm = algorithms.AES(MASTER_KEY)
    cipher = Cipher(algorithm, modes.CTR(nonce), backend=default_backend())
    encryptor = cipher.encryptor()

    async with await anyio.open_file(dest_path, "wb") as f:
        # Write nonce
        await f.write(nonce)
        
        while chunk := await upload_file.read(64 * 1024):
            # Offload CPU-heavy encryption to threadpool
            encrypted_chunk = await run_in_threadpool(encryptor.update, chunk)
            await f.write(encrypted_chunk)
        
        await f.write(encryptor.finalize())


# /usage

@app.get("/download/{file_id}")
async def download_file_ctr(file_id: str):
    file_path = f"storage/{file_id}.enc"
    
    if not os.path.exists(file_path):
        return {"error": "File not found"}

    # Calculate exact decrypted size (Total size - 16 bytes nonce)
    # No GCM tag here, so it's a simple subtraction
    file_size = os.path.getsize(file_path) - 16

    return StreamingResponse(
        decrypted_streamer_ctr(file_path),
        media_type="application/pdf",  # Or detect based on file_id
        headers={
            "Content-Disposition": f"attachment; filename=document.pdf",
            "Content-Length": str(file_size)
        }
    )
