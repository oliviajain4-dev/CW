import torch
from PIL import Image
import open_clip
import os

# 모델 로드
model, _, preprocess = open_clip.create_model_and_transforms(
    'hf-hub:Marqo/marqo-fashionSigLIP'
)
tokenizer = open_clip.get_tokenizer('hf-hub:Marqo/marqo-fashionSigLIP')
model.eval()

# 라벨 정의
top_labels = [
    "t-shirt", "blouse", "shirt", "hoodie",
    "knit sweater", "crop top", "tank top",
    "turtleneck", "long sleeve shirt", "sweatshirt"
]

bottom_labels = [
    "jeans", "slacks", "long skirt", "mini skirt",
    "pleated skirt", "dress", "wide pants",
    "shorts", "midi skirt", "leggings"
]

outer_labels = [
    "padding jacket", "coat", "jacket",
    "cardigan", "blazer", "trench coat",
    "leather jacket", "denim jacket",
    "bomber jacket", "no outer"
]

def analyze_outfit(image_path):
    image = preprocess(Image.open(image_path)).unsqueeze(0)
    print(f"\n이미지: {image_path}")

    with torch.no_grad():
        image_features = model.encode_image(image)

        for part, labels in [("상의", top_labels), 
                              ("하의", bottom_labels), 
                              ("아우터", outer_labels)]:
            text = tokenizer(labels)
            text_features = model.encode_text(text)
            probs = (image_features @ text_features.T).softmax(dim=-1)
            result = labels[probs.argmax()]
            prob = probs.max().item()

            if part == "아우터":
                if result != "no outer" and prob > 0.5:
                    print(f"아우터: {result} ({prob:.2%})")
                else:
                    print("아우터: 없음")
            else:
                print(f"{part}: {result} ({prob:.2%})")

# 이미지 폴더 분석
image_folder = "images"

if not os.path.exists(image_folder):
    os.makedirs(image_folder)
    print("images 폴더 만들었어요! 사진 넣고 다시 실행해줘요.")
else:
    image_files = [f for f in os.listdir(image_folder)
                   if f.endswith((".jpg", ".jpeg", ".png"))]
    if not image_files:
        print("images 폴더에 사진을 넣어줘요!")
    else:
        for img_file in image_files:
            analyze_outfit(os.path.join(image_folder, img_file))