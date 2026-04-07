# test_rembg.py
from rembg import remove
from PIL import Image

# 원본 이미지
original = Image.open("images/Cardigan.png")
original.save("original.png")

# 배경 제거
removed = remove(original)
removed.save("removed.png")

print("배경제거 완료! removed.png 확인해줘요")