"""
GRID Vision Module — OpenCV-powered computer vision tools
Extends GRID with camera validation, OCR, face analysis, video forensics, and image analysis.
"""

import os
import re
import io
import urllib.request
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def _ensure_cascade():
    """Download Haar cascade XML if not present."""
    dest = os.path.join(os.path.dirname(__file__), "haarcascade_frontalface_default.xml")
    if not os.path.exists(dest):
        url = "https://raw.githubusercontent.com/opencv/opencv/4.x/data/haarcascades/haarcascade_frontalface_default.xml"
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception:
            return None
    return dest

def _ocr_text(gray):
    """Extract text from grayscale image, gracefully handling missing tesseract."""
    try:
        import pytesseract
        return pytesseract.image_to_string(gray, lang='eng').strip()
    except Exception:
        return ""


class Vision:
    """Computer vision tools for GRID."""

    @staticmethod
    def analyze_image(path: str) -> str:
        """Full image analysis: OCR, face detection, QR/barcode, and metadata."""
        path = path.strip().strip('"').strip("'")
        if not os.path.exists(path):
            return f"Error: file not found: {path}"
        try:
            img = cv2.imread(path)
            if img is None:
                return f"Error: could not read image: {path}"
            lines = []
            lines.append(f"Image: {os.path.basename(path)}")
            h, w = img.shape[:2]
            lines.append(f"Size: {w}x{h}")
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            brightness = gray.mean()
            lines.append(f"Brightness: {brightness:.0f}/255")
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            lines.append(f"Sharpness: {laplacian_var:.1f}")
            ocr_text = _ocr_text(gray)
            if ocr_text:
                lines.append(f"OCR text ({len(ocr_text)} chars): {ocr_text[:500]}")
            else:
                lines.append("OCR: no text detected")
            # QR / barcode detection
            qcd = cv2.QRCodeDetector()
            retval, decoded_info, pts, straight_qrcode = qcd.detectAndDecodeMulti(img)
            if retval:
                for info in decoded_info:
                    if info:
                        lines.append(f"QR Code: {info}")
            cascade_path = _ensure_cascade()
            if cascade_path:
                face_cascade = cv2.CascadeClassifier(cascade_path)
                faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            else:
                faces = []
            if len(faces) > 0:
                lines.append(f"Faces detected: {len(faces)}")
                for i, (x, y, fw, fh) in enumerate(faces):
                    lines.append(f"  Face {i+1}: ({x}, {y}) {fw}x{fh}")
            else:
                lines.append("Faces: none detected")
            return "\n".join(lines)
        except Exception as e:
            return f"Error analyzing image: {e}"

    @staticmethod
    def screenshot_ocr(_unused: str = "") -> str:
        """Take a screenshot and extract text via OCR."""
        try:
            from PIL import ImageGrab
        except ImportError:
            return "Error: pillow required for screenshots."
        try:
            path = f"screen_{datetime.now():%Y%m%d_%H%M%S}.png"
            pil_img = ImageGrab.grab()
            pil_img.save(path)
            img = cv2.imread(path)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            ocr_text = _ocr_text(gray)
            size = os.path.getsize(path)
            result = f"Screenshot saved: {path} ({size // 1024} KB)\n"
            if ocr_text:
                result += f"OCR extracted ({len(ocr_text)} chars):\n{ocr_text[:1000]}"
            else:
                result += "OCR: no text detected in screenshot"
            return result
        except Exception as e:
            return f"Screenshot OCR failed: {e}"

    @staticmethod
    def camera_check(ip_port: str) -> str:
        """Validate a camera stream by attempting to connect and grab a frame.
        Accepts: ip:port, http://ip:port/path, rtsp://..."""
        target = ip_port.strip().strip('"').strip("'")
        urls_to_try = []
        if "://" in target:
            urls_to_try.append(target)
        elif ":" in target:
            parts = target.split(":")
            host = parts[0]
            port = parts[1].split("/")[0]
            for scheme in ["http", "rtsp", "rtmp"]:
                urls_to_try.append(f"{scheme}://{host}:{port}")
            urls_to_try.append(f"http://{host}:{port}/video")
            urls_to_try.append(f"http://{host}:{port}/mjpeg")
            urls_to_try.append(f"http://{host}:{port}/stream")
        else:
            urls_to_try.append(f"http://{target}:80")
        for url in urls_to_try:
            try:
                cap = cv2.VideoCapture(url, cv2.CAP_DSHOW)
                cap.set(cv2.CAP_PROP_TIMEOUT_MSEC, 3000)
                if not cap.isOpened():
                    cap.release()
                    continue
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    h, w = frame.shape[:2]
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    brightness = gray.mean()
                    laplacian = cv2.Laplacian(gray, cv2.CV_64F).var()
                    # Detect motion/noise — blank feeds have very low variance
                    is_placeholder = brightness < 5 or laplacian < 0.5
                    status = "PLACEHOLDER/BLANK" if is_placeholder else "LIVE FEED"
                    lines = [
                        f"Camera: {target}",
                        f"Stream URL: {url}",
                        f"Status: {status}",
                        f"Resolution: {w}x{h}",
                        f"Brightness: {brightness:.0f}/255",
                        f"Sharpness: {laplacian:.1f}",
                    ]
                    return "\n".join(lines)
            except Exception:
                continue
        return f"Camera offline or unreachable: {target} (tried {len(urls_to_try)} URLs)"

    @staticmethod
    def detect_faces(path: str) -> str:
        """Detect faces in an image file and return locations."""
        path = path.strip().strip('"').strip("'")
        if not os.path.exists(path):
            return f"Error: file not found: {path}"
        try:
            img = cv2.imread(path)
            if img is None:
                return f"Error: could not read image: {path}"
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            cascade_path = _ensure_cascade()
            if not cascade_path:
                return "Face detection unavailable (cascade file not found)"
            face_cascade = cv2.CascadeClassifier(cascade_path)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            lines = [f"Image: {os.path.basename(path)}", f"Faces found: {len(faces)}"]
            for i, (x, y, fw, fh) in enumerate(faces):
                lines.append(f"  Face {i+1}: position=({x},{y}) size={fw}x{fh}")
                # Draw rectangle on a copy
                cv2.rectangle(img, (x, y), (x+fw, y+fh), (0, 255, 0), 2)
            if len(faces) > 0:
                output_path = f"faces_{os.path.basename(path)}"
                cv2.imwrite(output_path, img)
                lines.append(f"Annotated image saved: {output_path}")
            return "\n".join(lines)
        except Exception as e:
            return f"Face detection error: {e}"

    @staticmethod
    def compare_faces(pair: str) -> str:
        """Compare two face images for similarity. Input: path1 | path2"""
        parts = [p.strip().strip('"').strip("'") for p in pair.split("|")]
        if len(parts) < 2:
            return "Error: provide two paths separated by | (e.g. 'face1.jpg | face2.jpg')"
        p1, p2 = parts[0], parts[1]
        if not os.path.exists(p1):
            return f"Error: first file not found: {p1}"
        if not os.path.exists(p2):
            return f"Error: second file not found: {p2}"
        try:
            img1 = cv2.imread(p1, cv2.IMREAD_GRAYSCALE)
            img2 = cv2.imread(p2, cv2.IMREAD_GRAYSCALE)
            if img1 is None or img2 is None:
                return "Error: could not read one or both images"
            h1, w1 = img1.shape
            h2, w2 = img2.shape
            if h1 != h2 or w1 != w2:
                img2 = cv2.resize(img2, (w1, h1))
            # Use histogram comparison as a simple similarity metric
            hist1 = cv2.calcHist([img1], [0], None, [256], [0, 256])
            hist2 = cv2.calcHist([img2], [0], None, [256], [0, 256])
            cv2.normalize(hist1, hist1, 0, 1, cv2.NORM_MINMAX)
            cv2.normalize(hist2, hist2, 0, 1, cv2.NORM_MINMAX)
            similarity = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
            # Structural similarity via template matching at center
            min_dim = min(h1, w1)
            if min_dim > 50:
                center_slice1 = img1[h1//4:3*h1//4, w1//4:3*w1//4]
                center_slice2 = img2[h2//4:3*h2//4, w2//4:3*w2//4]
                if center_slice1.shape == center_slice2.shape:
                    res = cv2.matchTemplate(center_slice1, center_slice2, cv2.TM_CCOEFF_NORMED)
                    tm_score = res[0][0]
                else:
                    tm_score = 0
            else:
                tm_score = 0
            score = (similarity + tm_score) / 2 * 100
            verdict = "LIKELY SAME" if score > 70 else "POSSIBLY SAME" if score > 40 else "DIFFERENT"
            return (
                f"Comparison: {os.path.basename(p1)} vs {os.path.basename(p2)}\n"
                f"Histogram similarity: {similarity*100:.1f}%\n"
                f"Template match score: {tm_score*100:.1f}%\n"
                f"Combined score: {score:.1f}%\n"
                f"Verdict: {verdict}"
            )
        except Exception as e:
            return f"Face comparison error: {e}"

    @staticmethod
    def video_analyze(path: str) -> str:
        """Extract keyframes and metadata from a video file."""
        path = path.strip().strip('"').strip("'")
        if not os.path.exists(path):
            return f"Error: file not found: {path}"
        try:
            cap = cv2.VideoCapture(path)
            if not cap.isOpened():
                return f"Error: could not open video: {path}"
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            duration = total_frames / fps if fps > 0 else 0
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            lines = [
                f"Video: {os.path.basename(path)}",
                f"Resolution: {w}x{h}",
                f"Frames: {total_frames}",
                f"FPS: {fps:.1f}",
                f"Duration: {duration:.1f}s ({duration/60:.1f}m)",
            ]
            # Extract keyframes: sample at 30-frame intervals
            keyframe_dir = f"keyframes_{Path(path).stem}_{datetime.now():%Y%m%d_%H%M%S}"
            os.makedirs(keyframe_dir, exist_ok=True)
            sample_interval = max(1, total_frames // 10)  # max 10 keyframes
            extracted = 0
            frame_idx = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                if frame_idx % sample_interval == 0:
                    kf_path = os.path.join(keyframe_dir, f"frame_{frame_idx:06d}.jpg")
                    cv2.imwrite(kf_path, frame)
                    extracted += 1
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    laplacian = cv2.Laplacian(gray, cv2.CV_64F).var()
                    ocr_text = _ocr_text(gray)[:100]
                    lines.append(f"  Keyframe {extracted} (frame {frame_idx}): sharpness={laplacian:.1f}")
                    if ocr_text:
                        lines.append(f"    OCR: {ocr_text}")
                frame_idx += 1
            cap.release()
            lines.append(f"\nExtracted {extracted} keyframes to {keyframe_dir}/")
            return "\n".join(lines)
        except Exception as e:
            return f"Video analysis error: {e}"
