import os
import cv2
import numpy as np
from flask import Flask, request, jsonify, url_for
from flask_cors import CORS
from ultralytics import YOLO
import io
from PIL import Image
from datetime import datetime
import traceback

# ==============================================================================
# ## Configuration & Global Variables (v22 - Final)
# ==============================================================================
app = Flask(__name__)
CORS(app)

# --- Path and Model Setup ---
STATIC_FOLDER = 'static'
RESULT_FOLDER = os.path.join(STATIC_FOLDER, 'results')
os.makedirs(RESULT_FOLDER, exist_ok=True)
app.config['RESULT_FOLDER'] = RESULT_FOLDER
try:
    model = YOLO('best.pt')
    model.fuse(verbose=False) 
    print("YOLOv8 OBB model 'best.pt' loaded and fused successfully.")
except Exception:
    try:
        model = YOLO('best.pt')
        print("YOLOv8 OBB model 'best.pt' loaded (without fusing).")
    except Exception as e2:
        print(f"Critical error loading model: {e2}")
        model = None

# --- Calibration & Dimension Variables ---
CALIBRATION_MATRIX = None
SANDBOX_DIMENSIONS = {'width': 650, 'length': 813} 

# --- ArUco Setup ---
ARUCO_DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
MARKER_IDS = [10, 11, 13, 15]


def calculate_intuitive_angle(cx, cy, w, h, r):
    try:
        cos_r=np.cos(r); sin_r=np.sin(r)
        corners=np.array([[-w/2,-h/2],[w/2,-h/2],[w/2,h/2],[-w/2,h/2]])@np.array([[cos_r,sin_r],[-sin_r,cos_r]])+np.array([cx,cy])
        if w>h: endpoint1,endpoint2=(corners[0]+corners[3])/2,(corners[1]+corners[2])/2
        else: endpoint1,endpoint2=(corners[0]+corners[1])/2,(corners[2]+corners[3])/2
        top_endpoint=endpoint1 if endpoint1[1]<endpoint2[1] else endpoint2
        vector=top_endpoint-np.array([cx,cy])
        real_angle_rad=np.arctan2(-vector[1],vector[0])
        pi_half=np.pi/2
        if real_angle_rad>pi_half:real_angle_rad-=np.pi
        elif real_angle_rad<-pi_half:real_angle_rad+=np.pi
        return real_angle_rad
    except Exception:return r

# ==============================================================================
# ## API Endpoints
# ==============================================================================
@app.route('/set_dimensions', methods=['POST'])
def set_dimensions():
    global SANDBOX_DIMENSIONS, CALIBRATION_MATRIX
    data = request.get_json()
    if 'width' in data and 'length' in data:
        SANDBOX_DIMENSIONS['width'] = int(data['width'])
        SANDBOX_DIMENSIONS['length'] = int(data['length'])
        CALIBRATION_MATRIX = None
        print(f"Dimensions updated: {SANDBOX_DIMENSIONS}")
        return jsonify({"status": "success", "message": "Dimensions updated."})
    return jsonify({"status": "error", "message": "Invalid data."}), 400

@app.route('/reset_calibration', methods=['POST'])
def reset_calibration():
    global CALIBRATION_MATRIX
    CALIBRATION_MATRIX = None
    print("Calibration has been reset by user.")
    return jsonify({"status": "success", "message": "Calibration reset."})

# ==============================================================================
# ## Main API Endpoint: /auto_process
# ==============================================================================
@app.route('/auto_process', methods=['POST'])
def auto_process():
    global CALIBRATION_MATRIX
    try:
        if not model: return jsonify({"status": "error", "message": "Model not loaded"}), 500
        if 'file' not in request.files: return jsonify({"status": "error", "message": "No file part"}), 400

        file = request.files['file']
        image_bytes = file.read()
        pil_image_raw = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        frame_raw = np.array(pil_image_raw)
        frame_raw = cv2.cvtColor(frame_raw, cv2.COLOR_RGB2BGR)

        detector = cv2.aruco.ArucoDetector(ARUCO_DICT)
        corners, ids, _ = detector.detectMarkers(frame_raw)
        
        calibration_status = "Using existing calibration"
        if ids is not None and all(mid in ids.flatten() for mid in MARKER_IDS):
            output_width_px = SANDBOX_DIMENSIONS['width']
            output_length_px = SANDBOX_DIMENSIONS['length']
            
            marker_corners_map = {id[0]: corner for id, corner in zip(ids, corners)}
            
            image_pts = np.array([
                marker_corners_map[10][0][0], marker_corners_map[11][0][1],
                marker_corners_map[13][0][2], marker_corners_map[15][0][3]
            ], dtype="float32")
            
            destination_pts = np.array([
                [0.0, 0.0], [output_width_px, 0.0],
                [output_width_px, output_length_px], [0.0, output_length_px]], dtype="float32")
            
            CALIBRATION_MATRIX = cv2.getPerspectiveTransform(image_pts, destination_pts)
            calibration_status = "Recalibrated this frame"

        if CALIBRATION_MATRIX is None:
            return jsonify({"status": "pending_calibration", "message": "System not calibrated. Show markers to camera."})

        output_dims_px = (SANDBOX_DIMENSIONS['width'], SANDBOX_DIMENSIONS['length'])
        frame_warped = cv2.warpPerspective(frame_raw, CALIBRATION_MATRIX, output_dims_px)
        
        pil_image_warped = Image.fromarray(cv2.cvtColor(frame_warped, cv2.COLOR_BGR2RGB))
        results = model(pil_image_warped, verbose=False, conf=0.5)
        
        detected_objects_data = []
        frame_with_boxes = results[0].plot() if len(results) > 0 else frame_warped
        
        if len(results) > 0:
            for box in results[0].obb:
                cx_mm, cy_mm, w_mm, h_mm, r = box.xywhr[0].tolist()
                
                detected_objects_data.append({
                    "class_name": model.names[int(box.cls.item())],
                    "confidence": box.conf.item(),
                    "center_mm": f"({cx_mm:.1f}, {cy_mm:.1f})",
                    "dimensions_mm": f"({w_mm:.1f}, {h_mm:.1f})",
                    "rotation_rad": calculate_intuitive_angle(cx_mm, cy_mm, w_mm, h_mm, r),
                    # [v22] เพิ่ม key ชั่วคราวสำหรับใช้เรียงลำดับ
                    "raw_cy": cy_mm,
                    "raw_cx": cx_mm
                })
        
        # [v22] เรียงลำดับรายการวัตถุจาก บน->ล่าง, ซ้าย->ขวา
        detected_objects_data.sort(key=lambda obj: (obj['raw_cy'], obj['raw_cx']))

        # [v22] ลบ key ชั่วคราวออกก่อนส่งข้อมูลกลับ
        for obj in detected_objects_data:
            del obj['raw_cy']
            del obj['raw_cx']

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_filename = f"processed_{timestamp}.jpg"
        result_filepath = os.path.join(app.config['RESULT_FOLDER'], result_filename)
        cv2.imwrite(result_filepath, frame_with_boxes)
        result_url = url_for('static', filename=f'results/{result_filename}')

        return jsonify({
            "status": "success",
            "calibration_status": calibration_status,
            "result_image_url": result_url,
            "detections": detected_objects_data
        })

    except Exception as e:
        print("--- AN EXCEPTION OCCURRED ---")
        traceback.print_exc()
        print("-----------------------------")
        return jsonify({"status": "error", "message": "An internal error occurred. Check server logs."}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=1600, debug=False)