import cv2

for i in range(4):
    cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
    if cap.isOpened():
        ret, frame = cap.read()
        print(f"Index {i}: opened={cap.isOpened()}, got frame={ret}, shape={None if not ret else frame.shape}")
    else:
        print(f"Index {i}: could not open")
    cap.release()