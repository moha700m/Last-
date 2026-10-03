# Last- — Offline Gameplay Vision Coach

Safe development build for analyzing **recorded gameplay footage or local test clips**.

## What it does

- Detects a configurable highlight color (`#FF00FF` by default).
- Filters magenta HUD/noise using body-shape heuristics instead of treating every purple pixel as a player.
- Keeps the vision logic modular so it can later be tested against annotated replay footage.
- Does **not** provide a live competitive-game overlay or automated tactical assistance.

## Run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python offline_enemy_detector.py input.mp4 --show
```

Optional output video:

```bash
python offline_enemy_detector.py input.mp4 --show --output analyzed.mp4
```

## Detection strategy

The detector converts the configured RGB highlight to HSV and builds a tolerance mask. It then applies morphological cleanup and rejects blobs that do not resemble upright player-sized regions using:

- contour area
- height/width aspect ratio
- bounding-box extent
- contour solidity
- minimum vertical size

Tune the thresholds in `DetectorConfig` for your footage resolution and UI theme.
