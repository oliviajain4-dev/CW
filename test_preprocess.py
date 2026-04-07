# test_preprocess.py
import torch
import open_clip
from PIL import Image
import os

model, _, preprocess = open_clip.create_model_and_transforms(
    'hf-hub:Marqo/marqo-fashionSigLIP'
)
tokenizer = open_clip.get_tokenizer('hf-hub:Marqo/marqo-fashionSigLIP')
model.eval()

top_labels    = ["t-shirt","blouse","shirt","hoodie","knit sweater",
                 "crop top","tank top","turtleneck","long sleeve shirt","sweatshirt"]
bottom_labels = ["jeans","slacks","long skirt","mini skirt","pleated skirt",
                 "dress","wide pants","shorts","midi skirt","leggings"]
outer_labels  = ["padding jacket","coat","jacket","cardigan","blazer",
                 "trench coat","leather jacket","denim jacket","bomber jacket","no outer"]

def analyze(image):
    tensor = preprocess(image).unsqueeze(0)
    result = {}
    with torch.no_grad():
        image_features = model.encode_image(tensor)
        for part, labels in [("상의", top_labels),
                              ("하의", bottom_labels),
                              ("아우터", outer_labels)]:
            text  = tokenizer(labels)
            feats = model.encode_text(text)
            probs = (image_features @ feats.T).softmax(dim=-1)
            pred  = labels[probs.argmax()]
            prob  = probs.max().item()
            if part == "아우터":
                result[part] = f"{pred} ({prob:.2%})" if pred != "no outer" else "없음"
            else:
                result[part] = f"{pred} ({prob:.2%})"
    return result

# 전처리 방법 3가지 비교
def compare_preprocess(image_path):
    print(f"\n── {os.path.basename(image_path)} ──")

    # 원본
    original = Image.open(image_path).convert("RGB")

    # 방법 1: 원본 그대로
    result1 = analyze(original)
    print(f"\n[원본]")
    for k, v in result1.items(): print(f"  {k}: {v}")

    # 방법 2: 224x224 리사이즈
    resized = original.resize((224, 224), Image.LANCZOS)
    result2 = analyze(resized)
    print(f"\n[224x224 리사이즈]")
    for k, v in result2.items(): print(f"  {k}: {v}")

    # 방법 3: 정사각형 크롭 후 리사이즈
    w, h = original.size
    s = min(w, h)
    left = (w - s) // 2
    top  = (h - s) // 2
    cropped = original.crop((left, top, left+s, top+s)).resize((224, 224), Image.LANCZOS)
    result3 = analyze(cropped)
    print(f"\n[정사각형 크롭 + 리사이즈]")
    for k, v in result3.items(): print(f"  {k}: {v}")

if __name__ == "__main__":
    image_folder = "images"
    image_files  = [f for f in os.listdir(image_folder)
                    if f.endswith((".jpg",".jpeg",".png"))][:3]  # 3장만 테스트

    for img_file in image_files:
        compare_preprocess(os.path.join(image_folder, img_file))