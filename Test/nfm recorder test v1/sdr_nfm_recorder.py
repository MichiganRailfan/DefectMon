import os
import sys

# Force Python 3.8+ to search the current folder for DLL dependencies
if sys.platform == 'win32':
    os.add_dll_directory(os.path.dirname(os.path.abspath(__file__)))

import time
import wave
import numpy as np
import scipy.signal as signal
import sounddevice as sd
from rtlsdr import RtlSdr

# ==================== CONFIGURATION ====================
CENTER_FREQ = 162.400e6     # Frequency to tune to (e.g., 162.400 MHz NOAA Weather)
SAMPLE_RATE = 2.4e6         # SDR sample rate (2.4 MSPS)
DECIMATION_1 = 50           # First stage downsampling (2.4M / 50 = 48 kHz IQ rate)
DECIMATION_2 = 1            # Second stage downsampling (48k / 1 = 48 kHz Audio rate)

# NFM parameters
MAX_DEVIATION = 5000        # Maximum frequency deviation for NFM (Typically 2.5 - 5 kHz)

# Squelch & Recording Configurations
SQUELCH_THRESHOLD = -45.0   # RSSI dB threshold. Adjust this based on your noise floor!
SQUELCH_TAIL_SEC = 1.5      # How long to keep recording after signal drops below squelch
OUTPUT_DIR = "recordings"   # Directory to save WAV recordings

# Audio setup
AUDIO_RATE = int((SAMPLE_RATE / DECIMATION_1) / DECIMATION_2)  # Should equal 48000 Hz
# =======================================================

class NFMReceiver:
    def __init__(self):
        self.sdr = None
        self.is_recording = False
        self.wav_file = None
        self.last_above_squelch = 0
        
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)

        # Pre-calculate lowpass filters for performance
        # Filter 1: Downsamples 2.4 MHz IQ data to 48 kHz IQ data
        self.b_iq, self.a_iq = signal.butter(4, (AUDIO_RATE / 2) / (SAMPLE_RATE / 2), btype='low')
        # Persistent state memory for filtering streaming chunks
        self.zi_iq_r = signal.lfilter_zi(self.b_iq, self.a_iq)
        self.zi_iq_i = signal.lfilter_zi(self.b_iq, self.a_iq)
        
        # State tracker to compute frequency discriminators smoothly
        self.prev_phase = 0.0

    def init_sdr(self):
        print("[*] Initializing RTL-SDR...")
        self.sdr = RtlSdr()
        self.sdr.sample_rate = SAMPLE_RATE
        self.sdr.center_freq = CENTER_FREQ
        self.sdr.gain = 'auto'

    def start_recording(self):
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = os.path.join(OUTPUT_DIR, f"nfm_{int(CENTER_FREQ/1e6)}MHz_{timestamp}.wav")
        print(f"\n[+] Squelch broken! Starting recording: {filename}")
        
        self.wav_file = wave.open(filename, 'wb')
        self.wav_file.setnchannels(1)
        self.wav_file.setsampwidth(2) # 16-bit PCM
        self.wav_file.setframerate(AUDIO_RATE)
        self.is_recording = True

    def stop_recording(self):
        if self.is_recording and self.wav_file:
            print("\n[-] Squelch closed. Transmission ended. Recording saved.")
            self.wav_file.close()
            self.wav_file = None
            self.is_recording = False

    def process_audio(self, iq_samples):
        # 1. Downsample the wideband IQ raw data to Narrowband 48 kHz IQ channel
        # Separate real and imaginary for filtering
        real_filt, self.zi_iq_r = signal.lfilter(self.b_iq, self.a_iq, iq_samples.real, zi=self.zi_iq_r)
        imag_filt, self.zi_iq_i = signal.lfilter(self.b_iq, self.a_iq, iq_samples.imag, zi=self.zi_iq_i)
        iq_decimated = (real_filt + 1j * imag_filt)[::DECIMATION_1]

        # 2. Calculate Received Signal Strength Indicator (RSSI) in dB
        # Used directly to trigger our squelch break engine
        mean_power = np.mean(np.abs(iq_decimated)**2)
        rssi = 10 * np.log10(mean_power + 1e-10)

        # 3. FM Demodulation (Extract instantaneous phase differentiations)
        phases = np.angle(iq_decimated)
        # Unwrap phases to eliminate +/- PI jumping anomalies
        delta_phase = np.diff(np.unwrap(np.concatenate(([self.prev_phase], phases))))
        self.prev_phase = phases[-1] if len(phases) > 0 else 0.0
        
        # Demodulated output is proportional to frequency deviation
        audio_signal = delta_phase * (AUDIO_RATE / (2 * np.pi * MAX_DEVIATION))
        
        # Apply standard De-emphasis filtering (high frequencies drop off at 6dB/octave in NFM)
        # This acts as a basic lowpass to filter out raw FM hiss
        b_audio, a_audio = signal.butter(1, 3000 / (AUDIO_RATE / 2), btype='low')
        audio_signal = signal.lfilter(b_audio, a_audio, audio_signal)

        # Normalize audio frame volume to comfortably fit within int16 bounds
        audio_signal = np.clip(audio_signal * 10, -1.0, 1.0)
        
        # 4. Squelch Processing System
        current_time = time.time()
        if rssi > SQUELCH_THRESHOLD:
            self.last_above_squelch = current_time
            if not self.is_recording:
                self.start_recording()
        else:
            # If the transmission drops out briefly, wait out the squelch tail before cutting
            if self.is_recording and (current_time - self.last_above_squelch > SQUELCH_TAIL_SEC):
                self.stop_recording()

        # Output audio formatting
        if self.is_recording:
            # Scale to 16-bit PCM and write out to the active file
            audio_pcm = (audio_signal * 32767).astype(np.int16)
            self.wav_file.writeframes(audio_pcm.tobytes())
            print(f"       [REC] RSSI: {rssi:.1f} dB  ", end='\r')
            return audio_signal
        else:
            print(f"[MUTED] RSSI: {rssi:.1f} dB (Threshold: {SQUELCH_THRESHOLD} dB)  ", end='\r')
            return np.zeros_like(audio_signal) # Output silence when squelch is clamped

    def run(self):
        self.init_sdr()
        
        # Size chunks to gather ~100ms of data per loop iteration
        fft_size = 245760 
        
        # Open your speakers stream natively via sounddevice
        with sd.OutputStream(samplerate=AUDIO_RATE, channels=1, dtype='float32') as stream:
            print(f"[*] Stream operational. Listening to {CENTER_FREQ/1e6:.3f} MHz...")
            print("[*] Press Ctrl+C to terminate application safely.\n")
            
            try:
                while True:
                    # Capture high speed digital IQ matrix chunks from dongle
                    samples = self.sdr.read_samples(fft_size)
                    
                    if len(samples) > 0:
                        audio_chunk = self.process_audio(samples)
                        # Play out to local audio hardware dynamically
                        stream.write(audio_chunk.astype(np.float32))
                        
            except KeyboardInterrupt:
                print("\n[*] Exiting receiver loop dynamically...")
            finally:
                self.stop_recording()
                if self.sdr:
                    self.sdr.close()
                    print("[*] SDR device hardware connection closed successfully.")

if __name__ == "__main__":
    receiver = NFMReceiver()
    receiver.run()
