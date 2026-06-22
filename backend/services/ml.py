import logging
from typing import List, Optional
from PIL import Image
import pytesseract
import re
from facenet_pytorch import MTCNN, InceptionResnetV1

import torch
import open_clip

from backend.config import settings
from backend.db.vector import get_clip_table, get_face_table
from backend.db.models import MediaItem, Tag, Face, Person
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

_mtcnn = None
_resnet = None

def get_mtcnn():
    global _mtcnn
    if _mtcnn is None:
        # MTCNN facenet_pytorch adaptive pool fails on MPS for arbitrary sizes, force CPU
        _mtcnn = MTCNN(keep_all=True, device="cpu")
    return _mtcnn

def get_resnet():
    global _resnet
    if _resnet is None:
        device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
        _resnet = InceptionResnetV1(pretrained='vggface2').eval().to(device)
    return _resnet

VOCABULARY = ["dog", "cat", "car", "person", "beach", "mountain", "food", "flower", "tree", "building", "water", "sky", "bird", "night", "sunset", "invoice", "receipt", "document", "screenshot"]

def get_or_create_tag(db: Session, name: str, source: str) -> Tag:
    tag = db.query(Tag).filter(Tag.name == name).first()
    if not tag:
        tag = Tag(name=name, source=source)
        db.add(tag)
        db.flush()
    return tag

def index_unprocessed_items(db: Session, batch_size: int = 100):
    """Find media items that need embeddings or tags and process them."""
    items = db.execute(
        select(MediaItem)
        .where((MediaItem.clip_embedded.is_(False)) | (MediaItem.faces_scanned.is_(False)))
        .where(MediaItem.mime_type.like("image/%"))
        .limit(batch_size)
    ).scalars().all()
    
    if not items:
        return {"processed": 0, "status": "idle"}
        
    clip_table = get_clip_table()
    records = []
    processed_count = 0
    
    faces_found = 0
    labels_found = 0
    
    model, preprocess, tokenizer = get_clip_components()
    device = next(model.parameters()).device
    
    # Precompute vocabulary embeddings
    with torch.no_grad(), torch.cuda.amp.autocast() if device.type == "cuda" else torch.autocast(device.type) if device.type in ["mps", "cpu"] else torch.no_grad():
        text_inputs = tokenizer(VOCABULARY).to(device)
        vocab_features = model.encode_text(text_inputs)
        vocab_features /= vocab_features.norm(dim=-1, keepdim=True)
        
    mtcnn = get_mtcnn()
    
    for item in items:
        try:
            image = Image.open(item.original_path).convert("RGB")
            
            # --- 1. OCR (Text Extraction) ---
            if not item.clip_embedded:
                try:
                    text_data = pytesseract.image_to_string(image)
                    words = set(re.findall(r'\b[A-Za-z]{4,}\b', text_data.lower()))
                    for word in words:
                        tag = get_or_create_tag(db, word, "ai_ocr")
                        if tag not in item.tags:
                            item.tags.append(tag)
                            labels_found += 1
                except Exception as e:
                    logger.warning(f"OCR failed for {item.original_path}: {e}")
                    
            # --- 2. Face Detection ---
            if not item.faces_scanned:
                try:
                    boxes, _ = mtcnn.detect(image)
                    if boxes is not None and len(boxes) > 0:
                        tag = get_or_create_tag(db, "Face", "ai_deepface")
                        if tag not in item.tags:
                            item.tags.append(tag)
                            labels_found += 1
                        
                        # Generate and store embeddings for each face
                        resnet = get_resnet()
                        face_records = []
                        face_table = get_face_table()
                        
                        # Use MTCNN to extract aligned face tensors
                        aligned_faces = mtcnn(image)
                        if aligned_faces is not None:
                            # Get embeddings for all faces at once
                            with torch.no_grad(), torch.cuda.amp.autocast() if device.type == "cuda" else torch.autocast(device.type) if device.type in ["mps", "cpu"] else torch.no_grad():
                                embeddings = resnet(aligned_faces.to(device)).cpu().numpy()
                            
                            for i, (box, embedding) in enumerate(zip(boxes, embeddings)):
                                # 1. Create SQL Face record
                                sql_face = Face(
                                    media_item_id=item.id,
                                    box_x1=float(box[0]),
                                    box_y1=float(box[1]),
                                    box_x2=float(box[2]),
                                    box_y2=float(box[3]),
                                )
                                db.add(sql_face)
                                db.flush() # get ID
                                faces_found += 1
                                
                                # 2. Add to LanceDB records
                                face_records.append({
                                    "media_id": item.id,
                                    "face_id": sql_face.id,
                                    "vector": embedding.tolist()
                                })
                        
                        if face_records:
                            face_table.add(face_records)
                            
                except Exception as e:
                    logger.warning(f"Face detection failed for {item.original_path}: {e}")
                item.faces_scanned = True
                
            # --- 3. Object Classification (Zero-Shot) & Embedding Storage ---
            if not item.clip_embedded:
                image_input = preprocess(image).unsqueeze(0).to(device)
                
                with torch.no_grad(), torch.cuda.amp.autocast() if device.type == "cuda" else torch.autocast(device.type) if device.type in ["mps", "cpu"] else torch.no_grad():
                    image_features = model.encode_image(image_input)
                    image_features /= image_features.norm(dim=-1, keepdim=True)
                    
                    # Compute zero-shot probabilities
                    similarities = (100.0 * image_features @ vocab_features.T).softmax(dim=-1)
                    values, indices = similarities[0].topk(3)
                    
                    for value, index in zip(values, indices):
                        if value.item() > 0.1:
                            label = VOCABULARY[index]
                            tag = get_or_create_tag(db, label.capitalize(), "ai_clip")
                            if tag not in item.tags:
                                item.tags.append(tag)
                                labels_found += 1
                
                vector = image_features.cpu().numpy()[0].tolist()
                records.append({
                    "media_id": item.id,
                    "vector": vector
                })
                item.clip_embedded = True
                
            processed_count += 1
            
        except Exception as e:
            logger.error(f"Failed to process {item.original_path}: {e}")
            
    if records:
        clip_table.add(records)
    
    db.commit()
        
    return {"processed": processed_count, "status": "active", "faces_found": faces_found, "labels_found": labels_found}

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

def cluster_faces(db: Session, eps: float = 0.5, min_samples: int = 2):
    """Clusters face embeddings using DBSCAN to group faces into distinct people."""
    from sklearn.cluster import DBSCAN
    import numpy as np

    face_table = get_face_table()
    if len(face_table) == 0:
        return {"status": "no_faces", "people_created": 0}

    # Retrieve all face embeddings from LanceDB
    # Use to_pandas to get the data efficiently
    df = face_table.to_pandas()
    if df.empty:
        return {"status": "no_faces", "people_created": 0}

    face_ids = df["face_id"].tolist()
    vectors = np.stack(df["vector"].values)

    # Perform DBSCAN clustering
    # eps and min_samples might need tuning depending on the embedding space
    clustering = DBSCAN(eps=eps, min_samples=min_samples, metric="euclidean").fit(vectors)
    labels = clustering.labels_

    people_created = 0
    # Group face IDs by cluster label
    clusters = {}
    for face_id, label in zip(face_ids, labels):
        if label == -1: # Noise (unclustered face)
            continue
        if label not in clusters:
            clusters[label] = []
        clusters[label].append(face_id)

    # For each cluster, check if any face already belongs to a Person.
    # If not, create a new Person. If yes, merge or use existing.
    for label, cluster_face_ids in clusters.items():
        # Find existing faces in DB
        sql_faces = db.execute(
            select(Face).where(Face.id.in_(cluster_face_ids))
        ).scalars().all()
        
        # Check if any face in this cluster already has a person_id
        existing_person_ids = {f.person_id for f in sql_faces if f.person_id is not None}
        
        person = None
        if existing_person_ids:
            # Simple approach: just use the first existing person ID
            # A more robust approach would merge people or use majority voting
            person_id = list(existing_person_ids)[0]
            person = db.get(Person, person_id)
        
        if not person:
            # Create new person
            person = Person(name=f"Person {label + 1}")
            db.add(person)
            db.flush() # get ID
            people_created += 1

        # Assign all faces in this cluster to the person
        for sql_face in sql_faces:
            sql_face.person_id = person.id
            # Set cover face if not set
            if not person.cover_face_id:
                person.cover_face_id = sql_face.id

    db.commit()
    return {"status": "success", "people_created": people_created}
