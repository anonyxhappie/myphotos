import sys
import torch
from facenet_pytorch import MTCNN
from PIL import Image

device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
mtcnn = MTCNN(keep_all=True, device=device)

path = "/Users/akshay/Desktop/code/myphotos/backend/myphotos.db" # using just any path to see if it loads
image_path = "/Users/akshay/Desktop/code/myphotos/test_data/some_image" # Need actual image path

