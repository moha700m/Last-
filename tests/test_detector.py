import asyncio

import cv2
import numpy as np

from realtime_ai_coach import GameStateAnalyzer


def run(coro):
    return asyncio.run(coro)


def test_body_like_magenta_silhouette_is_detected():
    analyzer = GameStateAnalyzer("#FF00FF", mask_hud=False)
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

    # Concave, upright silhouette: head/torso/arms/legs instead of a solid HUD rectangle.
    points = np.array(
        [
            [900, 350], [950, 350], [950, 430], [980, 430],
            [980, 500], [955, 500], [955, 650], [935, 650],
            [935, 520], [915, 520], [915, 650], [895, 650],
            [895, 500], [870, 500], [870, 430], [900, 430],
        ],
        dtype=np.int32,
    )
    cv2.fillPoly(frame, [points], (255, 0, 255))

    detections = run(analyzer.detect_enemies(frame))
    assert detections, "Expected an upright body-like magenta silhouette to be detected"


def test_horizontal_magenta_bar_is_rejected():
    analyzer = GameStateAnalyzer("#FF00FF", mask_hud=False)
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    cv2.rectangle(frame, (600, 400), (1100, 440), (255, 0, 255), -1)
    detections = run(analyzer.detect_enemies(frame))
    assert detections == [], "Expected a wide horizontal HUD-like bar to be rejected"
