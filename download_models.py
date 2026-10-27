"""Baixa os modelos ONNX do OpenCV Zoo (executado no build)."""
import os, urllib.request
B = "https://github.com/opencv/opencv_zoo/raw/main/models/"
M = {"yunet.onnx": B + "face_detection_yunet/face_detection_yunet_2023mar.onnx",
     "sface.onnx": B + "face_recognition_sface/face_recognition_sface_2021dec.onnx"}
def run():
    os.makedirs("models", exist_ok=True)
    for n, u in M.items():
        p = os.path.join("models", n)
        if not os.path.exists(p) or os.path.getsize(p) < 10000:
            print("baixando", n); urllib.request.urlretrieve(u, p)
if __name__ == "__main__": run()
