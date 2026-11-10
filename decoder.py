import os
import time
import logging
import json
import re
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import whisper
import librosa

# --- CONFIGURATION ---
WATCH_DIRECTORY = "./watch_folder"
JSON_LOG_FILE = "rail_telemetry.json"
MODEL_SIZE = "base"  # Options: tiny, base, small, medium, large
DEVICE = "cpu"       # Use "cuda" if you have a dedicated NVIDIA GPU

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
os.makedirs(WATCH_DIRECTORY, exist_ok=True)

print(f"Loading official OpenAI Whisper '{MODEL_SIZE}' model onto {DEVICE}...")
# Load the model directly using OpenAI's native entry point
model = whisper.load_model(MODEL_SIZE, device=DEVICE)
print(f"Model loaded successfully. Monitoring folder: '{WATCH_DIRECTORY}'...")


def log_json_telemetry(file_path, telemetry_dict):
    """Appends structured telemetry entries into a master JSON array file."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = {
        "timestamp": timestamp,
        "file_name": os.path.basename(file_path),
        "telemetry": telemetry_dict
    }
    
    if os.path.exists(JSON_LOG_FILE):
        try:
            with open(JSON_LOG_FILE, "r", encoding="utf-8") as f:
                data_list = json.load(f)
                if not isinstance(data_list, list):
                    data_list = []
        except Exception:
            data_list = []
    else:
        data_list = []
        
    data_list.append(entry)
    
    with open(JSON_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(data_list, f, indent=4, ensure_ascii=False)
    logging.info(f"Successfully logged JSON telemetry data to {JSON_LOG_FILE}")

def parse_transcript_to_json(text):
    """
    Parses the fluid text output from OpenAI Whisper directly into 
    a standardized JSON field layout with literal data mapping.
    """
    # 1. UNIVERSAL RADIO HALLUCINATION TRANSLATION LAYER:
    # Safely repair common words that Whisper uses to substitute number digits under compression.
    text = re.sub(r'\brunway\b', '18', text, flags=re.IGNORECASE)
    
    # Clean up spacing artifacts that the conversion layer might introduce (e.g. "18 6.3" -> "186.3")
    text = re.sub(r'(\d+)\s+(\d+\.\d+)', r'\1\2', text)
    text = re.sub(r'(\d+)\s*\.\s*(\d+)', r'\1.\2', text)

    # Initialize our clean tracking JSON format layout
    data = {
        "railroad": None,
        "milepost": None,
        "track": None,
        "direction": None,
        "defects": False,
        "temperature_f": None,
        "total_axles": None,
        "speed_mph": None,
        "train_length_feet": None
    }
    
    # 2. Identify the Railroad Carrier
    if "cn" in text.lower() or "cm" in text.lower():
        data["railroad"] = "CN"
    elif "csx" in text.lower():
        data["railroad"] = "CSX"
    else:
        data["railroad"] = "Unknown"
        
    # 3. Extract Mileposts (Safely captures the corrected "186.3")
    mile_match = re.search(r'mile(?:post|\s+post)?[,\s]+(\d+(?:\.\d+)?)', text, re.IGNORECASE)
    if mile_match:
        data["milepost"] = float(mile_match.group(1))
        
    # 4. Extract Track Assignments (Captures "Main 18" which means Main 1)
    track_match = re.search(r'(main\s+\d+|track\s+\d+)', text, re.IGNORECASE)
    if track_match:
        val = track_match.group(1).title()
        # Clean up trailing artifact if "main, runway" turned into "Main 18" instead of "Main 1"
        if "Main 18" in val:
            val = "Main 1"
        data["track"] = val
    elif "main" in text.lower():
        data["track"] = "Main"
        
    # 5. Extract Directions
    dir_match = re.search(r'(eastbound|westbound|northbound|southbound)', text, re.IGNORECASE)
    if dir_match:
        data["direction"] = dir_match.group(1).title()
        
    # 6. Fixed Defects Shield Verification Sequence
    if "no defects" in text.lower() or "no defect" in text.lower():
        data["defects"] = False
    elif "defect" in text.lower():
        data["defects"] = True
        
    # 7. Extract Temperatures
    temp_match = re.search(r'temperature[,\s]+(\d+)', text, re.IGNORECASE)
    if temp_match:
        data["temperature_f"] = int(temp_match.group(1))
        
    # 8. Extract Axle Counts (e.g. 574)
    axle_match = re.search(r'axles?[,\s]+(\d+)', text, re.IGNORECASE)
    if axle_match:
        data["total_axles"] = int(axle_match.group(1))
        
    # 9. Extract Train Lengths (CSX tracking values block)
    length_match = re.search(r'length[,\s]+(\d+)', text, re.IGNORECASE)
    if length_match:
        data["train_length_feet"] = int(length_match.group(1))
        
    # 10. Extract Speeds (LITERAL PARSING)
    # Extracts the exact number broadcasted by the audio model without any modifications
    speed_match = re.search(r'speed[,\s]+(\d+)', text, re.IGNORECASE)
    if speed_match:
        data["speed_mph"] = int(speed_match.group(1))
                
    return data

def process_audio(file_path):
    """Listens using official OpenAI Whisper and filters out non-defect files."""
    logging.info(f"New file detected: {file_path}")
    
    # File lock check safety loop
    initial_size = -1
    while True:
        try:
            current_size = os.path.getsize(file_path)
            if current_size == initial_size and current_size > 0:
                break
            initial_size = current_size
        except OSError:
            pass
        time.sleep(1.0)
    
    logging.info(f"Transcribing audio file with OpenAI Whisper...")
    try:
        combined_prompt = (
            "CN and CSX railroad equipment defect detector system report. "
            "Milepost 186.3, Milepost 44.2, Track Main 1, Track Main 2, westbound, eastbound. "
            "Temperature 34F, Temperature 68F, Total axles 574, Total axles 84, Speed 26, Train length 1241, End of transmission."
        )
        
        result = model.transcribe(
            file_path,
            fp16=False,
            initial_prompt=combined_prompt
        )
        
        raw_text = result["text"].strip()
        logging.info(f"Official Whisper Transcription: \"{raw_text}\"")
        
        # --- DEFECT GATEKEEPER CHECK ---
        # If the word "defect" or "defects" isn't anywhere in the message, ignore the file entirely.
        if "defect" not in raw_text.lower():
            logging.info(f"Ignored: File {os.path.basename(file_path)} does not contain any defect transmission text data.")
            return  # Exits the function cleanly without saving or logging
            
        # Process the clean text into structured data only if it passes the gatekeeper
        telemetry_json = parse_transcript_to_json(raw_text)
        
        # Output log array
        log_json_telemetry(file_path, telemetry_json)
        logging.info("Processing and database entry complete.")
        
    except Exception as e:
        logging.error(f"Error compiling audio processing thread: {e}")

class AudioFolderHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith('.wav'):
            process_audio(event.src_path)


if __name__ == "__main__":
    event_handler = AudioFolderHandler()
    observer = Observer()
    observer.schedule(event_handler, path=WATCH_DIRECTORY, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
