# 🚀 Deployment Guide

This guide explains how to deploy the **YOLOv8-OBB + ArUco** web application to your server.

## 📂 Repository Structure vs. Server Structure

We have organized the code to keep things clean. Here is where each file should go on your server:

| Folder / File | Local Path (Repository) | **Server Path** (Destination) | Description |
| :--- | :--- | :--- | :--- |
| **Backend** | `web_app/backend/` | `/home/g7tuesm/aruco/` | Contains `app.py`, `best.pt` |
| **Frontend** | `web_app/frontend/` | `/home/g7tuesm/domains/g7tuesm.consolutechcloud.com/public_html/` | Contains `index.html`, `.htaccess` |
| **Notebooks** | `notebooks/` | *(Not required on server)* | Research & Training files |

---

## 🛠️ Step-by-Step Deployment

### 1. Upload Backend Files
Upload the contents of `web_app/backend/` to `/home/g7tuesm/aruco/`.
- Ensure `app.py` is present.
- Ensure your trained model `best.pt` is in this folder (or update the path in `app.py`).

**Start the Backend:**
Connect to your server via SSH and run:
```bash
cd /home/g7tuesm/aruco/
pm2 start app.py --name yolo-api
pm2 save
```
*(This keeps the Python API running in the background on port 1600)*

### 2. Upload Frontend Files
Upload the contents of `web_app/frontend/` to your public HTML folder `/home/g7tuesm/domains/g7tuesm.consolutechcloud.com/public_html/`.
- `index.html`: Your web interface.
- `.htaccess`: The bridge configuration.

**Verify `.htaccess`**:
Make sure it contains the Reverse Proxy rule:
```apache
RewriteEngine On
RewriteRule ^backend/(.*)$ http://127.0.0.1:1600/$1 [P,L]
```

### 3. Test
Open your browser and go to:
`https://g7tuesm.consolutechcloud.com/`

If everything is correct, the frontend should load and successfully communicate with the backend (via `https://.../backend/auto_process`).
