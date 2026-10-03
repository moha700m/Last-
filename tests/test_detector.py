import asyncio
import cv2
import numpy as np

from realtime_ai_coach import GameStateAnalyzer


def run(coro):
    return asyncio.run(coro)


def test_vertical_magenta_body_is_detected():
    analyzer = GameStateAnalyzer("#FF00FF", mask_hud=False)
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    cv2.rectangle(frame, (900, 350), (950, 650), (255, 0, 255), -1)
    detections = run(analyzer.detect_enemies(frame))
    assert detections, "Expected an upright magenta body-like blob to be detected"


def test_horizontal_magenta_bar_is_rejected():
    analyzer = GameStateAnalyzer("#FF00FF", mask_hud=False)
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    cv2.rectangle(frame, (600, 400), (1100, 440), (255, 0, 255), -1)
    detections = run(analyzer.detect_enemies(frame))
    assert detections == [], "Expected a wide horizontal HUD-like bar to be rejected"
