import asyncio
import re
import edge_tts
import json
import os

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------
VOICE = "en-GB-RyanNeural"
CONCURRENT_LIMIT = 8  # Process 8 items at a time
OUTPUT_DIR = "./audio"
# ---------------------------------------------------------

def clean_markdown(text):
    """
    Removes markdown syntax (bold, links, headers) so the audio 
    sounds like a natural article/book rather than code.
    """
    if not text: return ""
    
    # 1. Remove Code Blocks
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    # 2. Remove Inline Code
    text = re.sub(r'`([^`]*)`', r'\1', text)
    # 3. Remove Images
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    # 4. Fix Links
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # 5. Remove Headers
    text = re.sub(r'#+\s?', '', text)
    # 6. Remove Bold/Italic
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    # 7. Remove Blockquotes
    text = re.sub(r'^>\s?', '', text, flags=re.MULTILINE)
    # 8. Collapse multiple newlines
    text = re.sub(r'\n+', '\n', text)
    
    return text.strip()

async def process_section(sem, raw_text, section_name):
    """
    This function processes a single section.
    'async with sem:' ensures we wait for an available slot before proceeding.
    """
    async with sem:
        print(f"Processing: {section_name}...")
        
        clean_text = clean_markdown(raw_text)

        if not clean_text:
            print(f"Skipping {section_name}: Text empty after cleaning.")
            return

        try:
            communicate = edge_tts.Communicate(clean_text, VOICE)
            output_path = os.path.join(OUTPUT_DIR, f"{section_name}.mp3")
            await communicate.save(output_path)
            print(f"Completed: {section_name}")
        except Exception as e:
            print(f"Failed {section_name}: {e}")

async def run_batch(data):
    # Create the directory if it doesn't exist
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # The Semaphore limits concurrent execution to 8
    sem = asyncio.Semaphore(CONCURRENT_LIMIT)
    
    tasks = []
    
    # Create a task for every item in the JSON
    idx = 1
    for key, value in data.items():
        # process_section will wait for the semaphore, so we can create all tasks immediately
        task = asyncio.create_task(process_section(sem, value, f"{idx:02}.{key}"))
        tasks.append(task)
        idx += 1
    
    # Run all tasks. They will automatically respect the limit of 8 at a time.
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    # Load data
    try:
        with open("book.json", "r", encoding="utf-8") as file:
            data = json.loads(file.read())

        print(f"Found {len(data)} sections. Starting batch processing...")
        
        # Start the async event loop ONCE
        asyncio.run(run_batch(data))
        
        print("\nAll processing finished.")
        
    except FileNotFoundError:
        print("Error: book.json not found.")
