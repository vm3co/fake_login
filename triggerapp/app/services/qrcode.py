from qrcodegen import QrCode
from PIL import Image
import io
import base64
import os

class Qrcode:
    def __init__(self, scale=10):
        self.scale = scale  # 圖片放大幾倍
        
    # 把 QR Code 的每個黑點放大 scale 倍（每個點變成 10x10 的黑色區塊）
    def fill_block(self, pixels, x, y, color=(0, 0, 0)):
        block_size = self.scale
        for dx in range(block_size):
            for dy in range(block_size):
                pixels[x * block_size + dx, y * block_size + dy] = color
        
    def output(self, url):
        qr = QrCode.encode_text(url, QrCode.Ecc.LOW)
        size = qr.get_size()
        
        # 創建一個白底黑點的 QR Code 圖片，放大 scale 倍
        img = Image.new("RGB", (size * self.scale, size * self.scale), "white")
        pixels = img.load()
        
        for y in range(size):
            for x in range(size):
                if qr.get_module(x, y):  # QR Code 黑點
                    self.fill_block(pixels, x, y)
        # 轉成 BytesIO 圖片
        img_io = io.BytesIO()
        img.save(img_io, format="PNG")
        img_io.seek(0)
        return img_io

        # # 轉成 base64 並包成 data URI
        # img_base64 = base64.b64encode(img_io.read()).decode("utf-8")
        # return f"data:image/png;base64,{img_base64}"

qrcode = Qrcode()

def main():
    # 測試
    code = Qrcode('https://www.google.com/', "./static/images/qr_code.png")
    code.output()

if __name__ == "__main__":
    main()
