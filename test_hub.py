import traceback
import customtkinter as ctk
from verification_hub import open_verification_hub
from vlm_pipeline import GenerationResult

root = ctk.CTk()
results = [GenerationResult(chunk_index=0, source_file='test.txt')]
print('Opening hub...')
try:
    open_verification_hub(root, results, modal=False)
except Exception:
    traceback.print_exc()
