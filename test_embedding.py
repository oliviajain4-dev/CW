# test_embedding.py
import torch
import open_clip
from PIL import Image
import os

model, _, preprocess = open_clip.create_model_and_transforms(
    'hf-hub:Marqo/marqo-fashionSigLIP'
)
model.eval()

def get_embedding(image_path):
    """이미지 임베딩 추출"""
    w, h = Image.open(image_path).size
    s = min(w, h)
    image = Image.open(image_path).convert("RGB")
    image = image.crop(((w-s)//2, (h-s)//2, (w-s)//2+s, (h-s)//2+s))
    image = image.resize((224, 224), Image.LANCZOS)
    tensor = preprocess(image).unsqueeze(0)

    with torch.no_grad():
        embedding = model.encode_image(tensor)
        embedding = embedding / embedding.norm(dim=-1, keepdim=True)  # 정규화
    return embedding

def cosine_similarity(emb1, emb2):
    """두 임베딩 유사도 계산 (1에 가까울수록 비슷)"""
    return (emb1 * emb2).sum().item()

if __name__ == "__main__":
    image_folder = "images"
    image_files  = [f for f in os.listdir(image_folder)
                    if f.endswith((".jpg", ".jpeg", ".png"))]

    print("임베딩 추출 중...")
    embeddings = {}
    for img_file in image_files:
        img_path = os.path.join(image_folder, img_file)
        embeddings[img_file] = get_embedding(img_path)
        print(f"  {img_file} 완료")

    print(f"\n── 유사도 행렬 ──")
    print(f"{'':20}", end="")
    for f in image_files:
        print(f"{f[:10]:12}", end="")
    print()

    for f1 in image_files:
        print(f"{f1[:20]:20}", end="")
        for f2 in image_files:
            sim = cosine_similarity(embeddings[f1], embeddings[f2])
            print(f"{sim:.2f}      ", end="")
        print()

    print("\n── 가장 비슷한 옷 TOP 3 ──")
    pairs = []
    files = list(image_files)
    for i in range(len(files)):
        for j in range(i+1, len(files)):
            sim = cosine_similarity(embeddings[files[i]], embeddings[files[j]])
            pairs.append((sim, files[i], files[j]))

    pairs.sort(reverse=True)
    for sim, f1, f2 in pairs[:3]:
        print(f"  {f1} ↔ {f2} : {sim:.3f}")

    print("\n── 가장 다른 옷 TOP 3 ──")
    for sim, f1, f2 in pairs[-3:]:
        print(f"  {f1} ↔ {f2} : {sim:.3f}")