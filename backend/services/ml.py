import logging
from typing import List, Optional
from PIL import Image

import torch
import open_clip

from backend.config import settings
from backend.db.vector import get_clip_table, get_face_table
from backend.db.models import MediaItem
from sqlalchemy.orm import Session
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Singletons for models to avoid reloading
_clip_model = None
_clip_preprocess = None
_clip_tokenizer = None

def get_clip_components():
    """Load and return the CLIP model, preprocessor, and tokenizer."""
    global _clip_model, _clip_preprocess, _clip_tokenizer
    if _clip_model is None:
        logger.info(f"Loading CLIP model: {settings.CLIP_MODEL_NAME} ({settings.CLIP_PRETRAINED})")
        device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Using device: {device}")
        
        model, _, preprocess = open_clip.create_model_and_transforms(
            settings.CLIP_MODEL_NAME, 
            pretrained=settings.CLIP_PRETRAINED,
            device=device
        )
        tokenizer = open_clip.get_tokenizer(settings.CLIP_MODEL_NAME)
        
        _clip_model = model
        _clip_preprocess = preprocess
        _clip_tokenizer = tokenizer
        
    return _clip_model, _clip_preprocess, _clip_tokenizer


def generate_image_embedding(image_path: str) -> Optional[List[float]]:
    """Generate a vector embedding for an image."""
    try:
        model, preprocess, _ = get_clip_components()
        device = next(model.parameters()).device
        
        image = Image.open(image_path).convert("RGB")
        image_input = preprocess(image).unsqueeze(0).to(device)
        
        with torch.no_grad(), torch.cuda.amp.autocast() if device.type == "cuda" else torch.autocast(device.type) if device.type in ["mps", "cpu"] else torch.no_grad():
            image_features = model.encode_image(image_input)
            image_features /= image_features.norm(dim=-1, keepdim=True)
            
        return image_features.cpu().numpy()[0].tolist()
    except Exception as e:
        logger.error(f"Failed to generate embedding for {image_path}: {e}")
        return None

def generate_text_embedding(text: str) -> Optional[List[float]]:
    """Generate a vector embedding for a text query."""
    try:
        model, _, tokenizer = get_clip_components()
        device = next(model.parameters()).device
        
        text_input = tokenizer([text]).to(device)
        
        with torch.no_grad(), torch.cuda.amp.autocast() if device.type == "cuda" else torch.autocast(device.type) if device.type in ["mps", "cpu"] else torch.no_grad():
            text_features = model.encode_text(text_input)
            text_features /= text_features.norm(dim=-1, keepdim=True)
            
        return text_features.cpu().numpy()[0].tolist()
    except Exception as e:
        logger.error(f"Failed to generate text embedding: {e}")
        return None

def index_unprocessed_items(db: Session, batch_size: int = 100):
    """Find media items that need embeddings and process them."""
    # Find items missing CLIP embeddings
    items = db.execute(
        select(MediaItem)
        .where(MediaItem.clip_embedded.is_(False))
        .where(MediaItem.mime_type.like("image/%"))
        .limit(batch_size)
    ).scalars().all()
    
    if not items:
        return {"processed": 0, "status": "idle"}
        
    clip_table = get_clip_table()
    records = []
    processed_count = 0
    
    for item in items:
        # Generate embedding
        vector = generate_image_embedding(item.original_path)
        if vector:
            records.append({
                "media_id": item.id,
                "vector": vector
            })
            item.clip_embedded = True
            processed_count += 1
            
    if records:
        clip_table.add(records)
        db.commit()
        
    return {"processed": processed_count, "status": "active"}

def search_semantic(query: str, limit: int = 50) -> List[str]:
    """Search for media items using a text query."""
    vector = generate_text_embedding(query)
    if not vector:
        return []
        
    clip_table = get_clip_table()
    
    # Empty table check
    if len(clip_table) == 0:
        return []
        
    # Perform vector search
    results = clip_table.search(vector).limit(limit).to_list()
    
    # Return list of media_ids
    return [r["media_id"] for r in results]
