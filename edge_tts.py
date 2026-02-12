import asyncio
import re
import edge_tts

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------
INPUT_FILE = "input.md"       # Your markdown file
OUTPUT_FILE = "output.mp3"    # Resulting audio file
VOICE = "en-US-ChristopherNeural"  # Options: en-US-GuyNeural, en-US-MichelleNeural, etc.
# ---------------------------------------------------------

def clean_markdown(text):
    """
    Removes markdown syntax (bold, links, headers) so the audio 
    sounds like a natural article/book rather than code.
    """
    # 1. Remove Code Blocks (``` ... ```) - usually bad to listen to
    #    (flags=re.DOTALL makes . match newlines too)
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    
    # 2. Remove Inline Code (`...`)
    text = re.sub(r'`([^`]*)`', r'\1', text)
    
    # 3. Remove Images (![alt](url)) - replaces with nothing
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    
    # 4. Fix Links [text](url) -> keeps only "text"
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # 5. Remove Headers (## Title) -> keeps "Title"
    text = re.sub(r'#+\s?', '', text)
    
    # 6. Remove Bold/Italic (**text** or *text*)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text) # Bold
    text = re.sub(r'\*([^*]+)\*', r'\1', text)     # Italic
    
    # 7. Remove Blockquotes (>)
    text = re.sub(r'^>\s?', '', text, flags=re.MULTILINE)
    
    # 8. Collapse multiple newlines/spaces into single pauses
    text = re.sub(r'\n+', '\n', text)
    
    return text.strip()

async def main():
    print(f"Reading {INPUT_FILE}...")
    try:
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            raw_text = f.read()
    except FileNotFoundError:
        print(f"Error: Could not find '{INPUT_FILE}'. Make sure the file exists.")
        return

    print("Cleaning Markdown formatting...")
    clean_text = clean_markdown(raw_text)

    if not clean_text:
        print("Error: The file appears to be empty after cleaning.")
        return

    print(f"Generating Audio using {VOICE}...")
    print("This may take a moment depending on text length...")
    
    # Communicate with Microsoft Edge TTS Service
    communicate = edge_tts.Communicate(clean_text, VOICE)
    
    # Save to MP3
    await communicate.save(OUTPUT_FILE)
    
    print(f"Done! Audio saved as: {OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(main())
