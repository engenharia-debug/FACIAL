import base64, os, cv2, numpy as np
D = R = None
def _load():
    global D, R
    if D is None:
        if not os.path.exists("models/sface.onnx"):
            import download_models; download_models.run()
        D = cv2.FaceDetectorYN.create("models/yunet.onnx", "", (320, 320), 0.85, 0.3, 5000)
        R = cv2.FaceRecognizerSF.create("models/sface.onnx", "")
def decode(url):
    try:
        a = np.frombuffer(base64.b64decode(url.split(",")[-1]), np.uint8)
        img = cv2.imdecode(a, cv2.IMREAD_COLOR)
    except Exception: img = None
    if img is None: raise ValueError("Imagem inválida")
    s = 640 / max(img.shape[:2])
    return cv2.resize(img, None, fx=s, fy=s) if s < 1 else img
def embed(img):
    """Detecta o maior rosto e devolve o vetor de 128 dimensões (SFace)."""
    _load(); h, w = img.shape[:2]; D.setInputSize((w, h)); _, f = D.detect(img)
    if f is None or len(f) == 0: raise ValueError("Nenhum rosto detectado. Centralize o rosto e melhore a luz.")
    f = max(f, key=lambda x: x[2] * x[3])
    return R.feature(R.alignCrop(img, f)).flatten().astype(np.float32)
def score(a, b): return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
def thumb(img):
    h, w = img.shape[:2]; s = min(h, w); y, x = (h - s) // 2, (w - s) // 2
    ok, b = cv2.imencode(".jpg", cv2.resize(img[y:y+s, x:x+s], (80, 80)), [cv2.IMWRITE_JPEG_QUALITY, 60])
    return "data:image/jpeg;base64," + base64.b64encode(b).decode()
