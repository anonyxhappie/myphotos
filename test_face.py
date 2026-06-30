import sys
import os
from PIL import Image

sys.path.append(os.getcwd())
os.environ["DATA_DIR"] = "./data"

from backend.services.ml import get_mtcnn, get_resnet
import torch

mtcnn = get_mtcnn()
resnet = get_resnet()

try:
    img = Image.open('test_faces.jpg').convert('RGB')
    boxes, probs = mtcnn.detect(img)
    if boxes is not None:
        aligned = mtcnn.extract(img, boxes, None)
        device = next(resnet.parameters()).device
        emb = resnet(aligned.to(device))
        print("Norms:", torch.norm(emb, dim=1))
except Exception as e:
    print("Error:", e)
