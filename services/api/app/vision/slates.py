"""Slate segmentation from one photo of several slates (guide §6.2.2).

Each child places a laminated ArUco ID card at the TOP-LEFT corner of their slate. The marker gives
identity (marker id = roster slot) *and* geometry: a homography from the marker's corners lets us
crop and rectify the slate region (in marker units) even when the photo is taken at an angle.
Cropping before any API call also guarantees no faces/hands are sent to Claude.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

ARUCO_DICT = cv2.aruco.DICT_4X4_100  # 100 roster slots per classroom


@dataclass(frozen=True)
class SlateGeometry:
    left: float = -0.15  # slate extent relative to the marker (marker occupies [0,1]x[0,1])
    top: float = -0.15
    right: float = 6.0
    bottom: float = 4.5
    px_per_unit: int = 110


@dataclass
class SlateCrop:
    marker_id: int
    jpeg: bytes
    width: int
    height: int
    sharpness: float  # variance of Laplacian; low = blurry
    marker_px: float  # marker side length in the photo; small = too far away

    @property
    def usable(self) -> bool:
        return self.sharpness >= 40 and self.marker_px >= 28


def _detector() -> cv2.aruco.ArucoDetector:
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    return cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(ARUCO_DICT), params)


def decode_image(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("unreadable image")
    return img


def enhance(gray: np.ndarray) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    out = clahe.apply(gray)
    return cv2.fastNlMeansDenoising(out, h=7)


def detect_and_crop(image_bytes: bytes, geom: SlateGeometry = SlateGeometry()) -> tuple[list[SlateCrop], dict]:
    img = decode_image(image_bytes)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = _detector().detectMarkers(gray)
    meta = {"image_size": [int(img.shape[1]), int(img.shape[0])], "markers": 0}
    if ids is None:
        return [], meta
    meta["markers"] = len(ids)
    crops: list[SlateCrop] = []
    unit_sq = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)
    for c, mid in zip(corners, ids.ravel()):
        pts = c.reshape(4, 2).astype(np.float32)
        H = cv2.getPerspectiveTransform(unit_sq, pts)  # marker units -> image pixels
        u = geom.px_per_unit
        w = int((geom.right - geom.left) * u)
        h = int((geom.bottom - geom.top) * u)
        # output pixel (x, y) -> marker units (left + x/u, top + y/u) -> image
        S = np.array([[1 / u, 0, geom.left], [0, 1 / u, geom.top], [0, 0, 1]], dtype=np.float64)
        warp = cv2.warpPerspective(gray, H @ S, (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                                   borderMode=cv2.BORDER_CONSTANT, borderValue=128)
        # blank out the marker itself so the model only sees the child's writing
        x0, y0 = int(-geom.left * u), int(-geom.top * u)
        cv2.rectangle(warp, (max(0, x0 - 4), max(0, y0 - 4)), (x0 + u + 4, y0 + u + 4), 128, -1)
        sharp = float(cv2.Laplacian(warp, cv2.CV_64F).var())
        out = enhance(warp)
        ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            continue
        side = float(np.mean(np.linalg.norm(pts - np.roll(pts, 1, axis=0), axis=1)))
        crops.append(SlateCrop(int(mid), buf.tobytes(), w, h, sharp, side))
    crops.sort(key=lambda s: s.marker_id)
    return crops, meta


def make_marker_card(slot: int, px: int = 400, label: str | None = None) -> np.ndarray:
    """Printable ID card: marker + big slot number (for the child and teacher to recognise)."""
    marker = cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(ARUCO_DICT), slot, px)
    card = np.full((px + 160, px + 80), 255, dtype=np.uint8)
    card[40:40 + px, 40:40 + px] = marker
    cv2.putText(card, label or f"{slot:02d}", (40, px + 130), cv2.FONT_HERSHEY_SIMPLEX, 2.6, 0, 6, cv2.LINE_AA)
    cv2.rectangle(card, (2, 2), (card.shape[1] - 3, card.shape[0] - 3), 0, 2)
    return card
