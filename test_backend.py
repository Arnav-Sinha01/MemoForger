from vlm_pipeline import VLMPipeline, GenerationConfig, TaskType
from ingestion_engine import DocumentChunk

print("Imports successful!")

config = GenerationConfig(task_type=TaskType.SUMMARY)
pipeline = VLMPipeline()
chunk = DocumentChunk(source_file="test.txt", chunk_index=0, total_chunks=1, text="Test document content.")
print("Testing process_chunk...")
res = pipeline._process_chunk(chunk, config)
print(f"Result: {res}")
