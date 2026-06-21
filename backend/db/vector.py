import pyarrow as pa
import lancedb

from backend.config import settings

def get_lancedb() -> lancedb.DBConnection:
    """Get the LanceDB connection."""
    settings.LANCEDB_PATH.mkdir(parents=True, exist_ok=True)
    return lancedb.connect(str(settings.LANCEDB_PATH))

def get_clip_table():
    """Get or create the CLIP image embeddings table."""
    db = get_lancedb()
    # CLIP ViT-B-32 embeddings are 512-dimensional
    schema = pa.schema([
        pa.field("media_id", pa.string()),
        pa.field("vector", pa.list_(pa.float32(), 512)),
    ])
    return db.create_table("clip_embeddings", schema=schema, exist_ok=True)

def get_face_table():
    """Get or create the DeepFace embeddings table."""
    db = get_lancedb()
    # Facenet embeddings are 128-dimensional
    schema = pa.schema([
        pa.field("media_id", pa.string()),
        pa.field("face_id", pa.string()), # Unique ID for the detected face
        pa.field("vector", pa.list_(pa.float32(), 128)),
    ])
    return db.create_table("face_embeddings", schema=schema, exist_ok=True)
