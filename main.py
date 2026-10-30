import cv2
from start_cam import UnwarpCamera

aruco_dict = cv2.aruco.Dictionary_get(cv2.aruco.DICT_6X6_250)
aruco_params = cv2.aruco.DetectorParameters_create()

cam = UnwarpCamera(calib_path="../../camera_calibration/calib_result.npz")
cam.start_stream(port=8080)
cam.start_crop_stream(port=8081)

try:
    for pano in cam.frames():
        gray = cv2.cvtColor(pano, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = cv2.aruco.detectMarkers(gray, aruco_dict, parameters=aruco_params)
        if ids is not None: print("detected")
finally:
    cam.release()