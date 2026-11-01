"""Audio decoding (any container the phone produces: webm/opus, ogg, mp4/aac, wav) to 16 kHz mono
float32, plus simple signal-quality checks used to decide whether a recording is scorable."""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np

TARGET_SR = 16000


def decode_to_16k_mono(data: bytes) -> np.ndarray:
    import av  # PyAV bundles FFmpeg, so no system ffmpeg is needed

    with av.open(io.BytesIO(data)) as container:
        stream = next(s for s in container.streams if s.type == "audio")
        resampler = av.AudioResampler(format="flt", layout="mono", rate=TARGET_SR)
        chunks: list[np.ndarray] = []
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):
            chunks.append(out.to_ndarray().reshape(-1))
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks).astype(np.float32)


@dataclass
class SignalQuality:
    duration_s: float
    rms_dbfs: float
    noise_floor_dbfs: float
    snr_db: float
    speech_ratio: float
    clipped_ratio: float

    @property
    def scorable(self) -> bool:
        return self.duration_s >= 0.3 and self.snr_db >= 6.0 and self.rms_dbfs > -50 and self.clipped_ratio < 0.05


def signal_quality(wave: np.ndarray, sr: int = TARGET_SR, frame_ms: float = 20.0) -> SignalQuality:
    if wave.size == 0:
        return SignalQuality(0, -120, -120, 0, 0, 0)
    n = max(1, int(sr * frame_ms / 1000))
    frames = wave[: len(wave) // n * n].reshape(-1, n) if len(wave) >= n else wave.reshape(1, -1)
    energy = np.sqrt((frames ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(energy + 1e-12)
    noise = float(np.percentile(db, 10))
    speech = float(np.percentile(db, 90))
    return SignalQuality(
        duration_s=len(wave) / sr,
        rms_dbfs=float(20 * np.log10(np.sqrt((wave ** 2).mean()) + 1e-12)),
        noise_floor_dbfs=noise,
        snr_db=speech - noise,
        speech_ratio=float((db > noise + 10).mean()),
        clipped_ratio=float((np.abs(wave) > 0.99).mean()),
    )


def trim_silence(wave: np.ndarray, sr: int = TARGET_SR, margin_s: float = 0.25) -> np.ndarray:
    """Energy-based trim of leading/trailing silence (keeps a margin so onsets aren't clipped)."""
    if wave.size == 0:
        return wave
    n = int(sr * 0.02)
    if len(wave) < n * 3:
        return wave
    frames = wave[: len(wave) // n * n].reshape(-1, n)
    db = 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1) + 1e-12))
    thr = np.percentile(db, 10) + 10
    active = np.where(db > thr)[0]
    if active.size == 0:
        return wave
    m = int(margin_s * sr)
    return wave[max(0, active[0] * n - m): min(len(wave), (active[-1] + 1) * n + m)]
