import logging
from typing import List, Optional
from PIL import Image, ImageOps
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
            image = Image.open(item.original_path)
            image = ImageOps.exif_transpose(image).convert("RGB")
            
            # Create a resized thumbnail for the ML models to process
            # This drastically reduces CPU time for OCR, MTCNN, and CLIP preprocessing
            # without reducing accuracy (since the models operate at lower resolutions anyway).
            img_width, img_height = image.size
            max_dim = 1024
            scale_x, scale_y = 1.0, 1.0
            
            if img_width > max_dim or img_height > max_dim:
                resized_img = image.copy()
                resized_img.thumbnail((max_dim, max_dim), Image.Resampling.BILINEAR)
                scale_x = img_width / resized_img.width
                scale_y = img_height / resized_img.height
                ml_input_img = resized_img
            else:
                ml_input_img = image
            
            # --- 1. OCR (Text Extraction) ---
            if not item.clip_embedded:
                try:
                    text_data = pytesseract.image_to_string(ml_input_img)
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
                    boxes, probs = mtcnn.detect(ml_input_img)
                    if boxes is not None and len(boxes) > 0:
                        # Filter by confidence > 0.90
                        valid_indices = [i for i, p in enumerate(probs) if p is not None and p > 0.90]
                        if valid_indices:
                            boxes = boxes[valid_indices]
                            
                            tag = get_or_create_tag(db, "Face", "ai_deepface")
                            if tag not in item.tags:
                                item.tags.append(tag)
                                labels_found += 1
                            
                            # Generate and store embeddings for each face
                            resnet = get_resnet()
                            face_records = []
                            face_table = get_face_table()
                            
                            # Use MTCNN to extract aligned face tensors exactly matching our boxes
                            aligned_faces = mtcnn.extract(ml_input_img, boxes, save_path=None)
                            if aligned_faces is not None:
                                # Get embeddings for all faces at once
                                with torch.no_grad(), torch.cuda.amp.autocast() if device.type == "cuda" else torch.autocast(device.type) if device.type in ["mps", "cpu"] else torch.no_grad():
                                    embeddings = resnet(aligned_faces.to(device)).cpu().numpy()
                                
                                for box, embedding in zip(boxes, embeddings):
                                    # Scale boxes back up to original image dimensions for the database
                                    orig_x1 = max(0, float(box[0]) * scale_x)
                                    orig_y1 = max(0, float(box[1]) * scale_y)
                                    orig_x2 = min(img_width, float(box[2]) * scale_x)
                                    orig_y2 = min(img_height, float(box[3]) * scale_y)

                                    # 1. Create SQL Face record
                                    sql_face = Face(
                                        media_item_id=item.id,
                                        box_x1=orig_x1,
                                        box_y1=orig_y1,
                                        box_x2=orig_x2,
                                        box_y2=orig_y2,
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
                image_input = preprocess(ml_input_img).unsqueeze(0).to(device)
                
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
                clip_table.add([{
                    "media_id": item.id,
                    "vector": vector
                }])
                item.clip_embedded = True
                
            db.commit()
            db.expire_all()
            processed_count += 1
            
        except Exception as e:
            db.rollback()
            db.expire_all()
            logger.error(f"Failed to process {item.original_path}: {e}")
            
    # Run clustering continuously on new faces
    if faces_found > 0:
        try:
            cluster_faces(db)
        except Exception as e:
            logger.error(f"Continuous clustering failed: {e}")
        
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

def cluster_faces(db: Session, eps: float = 0.4, min_samples: int = 2):
    """Intelligently groups new (unassigned) faces into distinct people."""
    from sklearn.cluster import DBSCAN
    import numpy as np
    import re

    face_table = get_face_table()
    if len(face_table) == 0:
        return {"status": "no_faces", "people_created": 0}

    # 1. Get all unassigned faces
    unassigned_faces = db.execute(
        select(Face).where(Face.person_id.is_(None))
    ).scalars().all()
    
    if not unassigned_faces:
        return {"status": "success", "people_created": 0}

    # 2. Try Nearest Neighbor matching for each unassigned face
    unassigned_face_ids = {f.id: f for f in unassigned_faces}
    remaining_unassigned = {}
    
    # We need the vectors for unassigned faces
    # For performance, we can just fetch all vectors into pandas and filter
    df = face_table.to_pandas()
    if df.empty:
        return {"status": "no_faces", "people_created": 0}
        
    df_unassigned = df[df['face_id'].isin(unassigned_face_ids.keys())]
    
    people_created = 0
    
    for _, row in df_unassigned.iterrows():
        face_id = row['face_id']
        vector = row['vector']
        
        # Search for closest match in DB
        results = face_table.search(vector).limit(5).to_list()
        
        assigned = False
        for res in results:
            if res['_distance'] < 0.4 and res['face_id'] != face_id:
                # Is this close match assigned to a person?
                match_sql = db.get(Face, res['face_id'])
                if match_sql and match_sql.person_id:
                    # Found an existing person!
                    sql_face = unassigned_face_ids[face_id]
                    sql_face.person_id = match_sql.person_id
                    assigned = True
                    break
                    
        if not assigned:
            remaining_unassigned[face_id] = vector

    # 3. For any remaining unassigned faces, run DBSCAN
    if remaining_unassigned:
        face_ids = list(remaining_unassigned.keys())
        vectors = np.stack(list(remaining_unassigned.values()))
        
        clustering = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine").fit(vectors)
        labels = clustering.labels_
        
        # Find the highest existing Person number to name new people
        existing_people = db.execute(select(Person.name)).scalars().all()
        highest_num = 0
        for name in existing_people:
            m = re.match(r"^Person (\d+)$", name)
            if m:
                num = int(m.group(1))
                if num > highest_num:
                    highest_num = num
                    
        clusters = {}
        for face_id, label in zip(face_ids, labels):
            if label == -1: # Noise (unclustered face)
                continue
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(face_id)
            
        for label, cluster_face_ids in clusters.items():
            highest_num += 1
            person = Person(name=f"Person {highest_num}")
            db.add(person)
            db.flush()
            people_created += 1
            
            for f_id in cluster_face_ids:
                sql_face = unassigned_face_ids[f_id]
                sql_face.person_id = person.id
                if not person.cover_face_id:
                    person.cover_face_id = sql_face.id
                    
    db.commit()
    return {"status": "success", "people_created": people_created}
