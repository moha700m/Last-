# realtime_ai_coach.py
# USB HDMI Capture + AI Vision + Live Tactical Coaching (offline/local testing)

import argparse
import asyncio
import math
import os
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import pytesseract
import tkinter as tk
from tkinter import Canvas


class ScreenReader:
    """قراءة USB HDMI Capture في الوقت الفعلي."""

    def __init__(
        self,
        device_index: Optional[int] = None,
        width: int = 1920,
        height: int = 1080,
        fps: int = 120,
        max_probe_devices: int = 8,
    ):
        self.device_index = device_index
        self.width = width
        self.height = height
        self.requested_fps = fps
        self.max_probe_devices = max_probe_devices
        self.last_frame: Optional[np.ndarray] = None
        self.running = False
        self.capture: Optional[cv2.VideoCapture] = None
        self.active_device: Optional[int] = None
        self.actual_width = 0
        self.actual_height = 0
        self.actual_fps = 0.0
        self._open_capture()

    def _backend(self) -> int:
        if os.name == "nt":
            return cv2.CAP_DSHOW
        return cv2.CAP_ANY

    def _configure_capture(self, cap: cv2.VideoCapture) -> None:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.requested_fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def _probe_device(self, index: int) -> Optional[cv2.VideoCapture]:
        cap = cv2.VideoCapture(index, self._backend())
        if not cap.isOpened():
            cap.release()
            return None

        self._configure_capture(cap)
        frame = None
        for _ in range(12):
            ok, candidate = cap.read()
            if ok and candidate is not None and candidate.size:
                frame = candidate
                break
            time.sleep(0.03)

        if frame is None:
            cap.release()
            return None

        self.last_frame = frame
        return cap

    def _open_capture(self) -> None:
        candidates = [self.device_index] if self.device_index is not None else list(range(self.max_probe_devices))

        for index in candidates:
            cap = self._probe_device(index)
            if cap is None:
                continue

            self.capture = cap
            self.active_device = index
            self.actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or self.last_frame.shape[1])
            self.actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or self.last_frame.shape[0])
            self.actual_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            print(
                f"[CAPTURE] USB device={index} "
                f"{self.actual_width}x{self.actual_height} "
                f"reported_fps={self.actual_fps:.1f}"
            )
            return

        requested = "auto" if self.device_index is None else str(self.device_index)
        raise RuntimeError(
            f"لم يتم العثور على USB Capture صالح (device={requested}). "
            "تأكد أنه ظاهر في Windows Camera/OBS ثم جرّب --device 0 أو 1 أو 2."
        )

    def capture_screen(self) -> np.ndarray:
        if self.capture is None:
            raise RuntimeError("Capture device is not initialized")

        ok, frame = self.capture.read()
        if not ok or frame is None or not frame.size:
            raise RuntimeError("فشل قراءة frame من USB Capture")

        self.last_frame = frame
        return frame

    def release(self) -> None:
        if self.capture is not None:
            self.capture.release()
            self.capture = None


class GameStateAnalyzer:
    """تحليل حالة اللعبة من USB capture؛ مخصص للاختبار المحلي/الأوفلاين."""

    def __init__(self, enemy_hex: str = "#FF00FF", mask_hud: bool = True):
        self.enemies_detected: List[Dict] = []
        self.teammate_positions: List[Dict] = []
        self.map_awareness: Dict = {}
        self.current_weapon = "Unknown"
        self.health = 100
        self.ammo: Dict = {}
        self.enemy_hex = enemy_hex
        self.mask_hud = mask_hud
        self._enemy_hsv = self._hex_to_hsv(enemy_hex)
        self._last_weapon_ocr = 0.0
        self._weapon_ocr_interval = 1.0
        self._last_mask: Optional[np.ndarray] = None

    @staticmethod
    def _hex_to_hsv(hex_color: str) -> Tuple[int, int, int]:
        value = hex_color.strip().lstrip("#")
        if len(value) != 6:
            raise ValueError("enemy_hex must be in #RRGGBB format")
        r = int(value[0:2], 16)
        g = int(value[2:4], 16)
        b = int(value[4:6], 16)
        pixel = np.uint8([[[b, g, r]]])
        h, s, v = cv2.cvtColor(pixel, cv2.COLOR_BGR2HSV)[0, 0]
        return int(h), int(s), int(v)

    async def analyze_frame(self, frame: np.ndarray) -> Dict:
        enemies = await self.detect_enemies(frame)
        analysis = {
            "enemies": enemies,
            "teammates": await self.detect_teammates(frame),
            "health": await self.read_health_bar(frame),
            "weapon": await self.identify_weapon(frame),
            "minimap": await self.analyze_minimap(frame),
            "timestamp": datetime.now().isoformat(),
        }
        self.enemies_detected = enemies
        return analysis

    def _apply_hud_exclusion(self, mask: np.ndarray) -> np.ndarray:
        if not self.mask_hud:
            return mask

        h, w = mask.shape[:2]
        result = mask.copy()
        regions = [
            (0.00, 0.00, 0.24, 0.27),
            (0.00, 0.80, 0.31, 1.00),
            (0.68, 0.79, 1.00, 1.00),
            (0.77, 0.00, 1.00, 0.13),
        ]
        for x1n, y1n, x2n, y2n in regions:
            x1, y1 = int(w * x1n), int(h * y1n)
            x2, y2 = int(w * x2n), int(h * y2n)
            result[y1:y2, x1:x2] = 0
        return result

    def _enemy_color_mask(self, frame: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        hue, _, _ = self._enemy_hsv
        hue_tolerance = 9
        sat_min = 145
        val_min = 135
        lower_h = max(0, hue - hue_tolerance)
        upper_h = min(179, hue + hue_tolerance)
        mask = cv2.inRange(
            hsv,
            np.array([lower_h, sat_min, val_min], dtype=np.uint8),
            np.array([upper_h, 255, 255], dtype=np.uint8),
        )
        mask = self._apply_hud_exclusion(mask)
        open_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 11))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, open_kernel, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel, iterations=1)
        self._last_mask = mask
        return mask

    @staticmethod
    def _contour_solidity(contour: np.ndarray) -> float:
        area = cv2.contourArea(contour)
        hull = cv2.convexHull(contour)
        hull_area = cv2.contourArea(hull)
        if hull_area <= 0:
            return 0.0
        return float(area / hull_area)

    @staticmethod
    def _bbox_magenta_ratio(mask: np.ndarray, x: int, y: int, w: int, h: int) -> float:
        roi = mask[y:y + h, x:x + w]
        if roi.size == 0:
            return 0.0
        return float(cv2.countNonZero(roi) / roi.size)

    def _looks_like_player_body(self, contour: np.ndarray, mask: np.ndarray, frame_shape: Tuple[int, int, int]) -> Optional[Dict]:
        frame_h, frame_w = frame_shape[:2]
        frame_area = frame_h * frame_w
        area = cv2.contourArea(contour)
        x, y, w, h = cv2.boundingRect(contour)
        min_area = max(70.0, frame_area * 0.000025)
        max_area = frame_area * 0.09
        if not (min_area <= area <= max_area):
            return None
        if w < max(4, int(frame_w * 0.002)) or h < max(12, int(frame_h * 0.012)):
            return None
        aspect = h / max(w, 1)
        if not (0.70 <= aspect <= 6.8):
            return None
        bbox_area = w * h
        extent = area / max(bbox_area, 1)
        if not (0.055 <= extent <= 0.92):
            return None
        solidity = self._contour_solidity(contour)
        if solidity < 0.20:
            return None
        magenta_ratio = self._bbox_magenta_ratio(mask, x, y, w, h)
        if magenta_ratio < 0.045:
            return None
        if w > h * 2.2:
            return None

        cx = x + w // 2
        cy = y + h // 2
        center_dx = (cx - frame_w / 2) / max(frame_w / 2, 1)
        center_dy = (cy - frame_h / 2) / max(frame_h / 2, 1)
        center_distance = min(1.0, math.hypot(center_dx, center_dy) / math.sqrt(2))
        shape_score = min(
            1.0,
            0.45 * solidity
            + 0.35 * min(magenta_ratio * 3.0, 1.0)
            + 0.20 * (1.0 - center_distance),
        )
        return {
            "position": (x, y),
            "center": (cx, cy),
            "size": (w, h),
            "area": float(area),
            "aspect": float(aspect),
            "solidity": float(solidity),
            "color_ratio": float(magenta_ratio),
            "confidence": round(shape_score, 3),
        }

    async def detect_enemies(self, frame: np.ndarray) -> List[Dict]:
        mask = self._enemy_color_mask(frame)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        enemies: List[Dict] = []
        for contour in contours:
            candidate = self._looks_like_player_body(contour, mask, frame.shape)
            if candidate is None:
                continue
            x, y = candidate["position"]
            w, h = candidate["size"]
            candidate["screen_location"] = self.get_screen_direction(x + w // 2, y + h // 2, frame.shape)
            candidate["distance_estimate"] = self.estimate_distance(h, frame.shape[0])
            enemies.append(candidate)
        enemies.sort(key=lambda item: item["confidence"], reverse=True)
        return enemies[:12]

    async def detect_teammates(self, frame: np.ndarray) -> List[Dict]:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array([96, 120, 120]), np.array([132, 255, 255]))
        mask = self._apply_hud_exclusion(mask)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        frame_h, frame_w = frame.shape[:2]
        min_area = frame_h * frame_w * 0.00004
        teammates = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            if h < 14 or w < 4 or w > h * 2.5:
                continue
            teammates.append({"position": (x, y), "size": (w, h), "status": "alive"})
        return teammates[:12]

    async def read_health_bar(self, frame: np.ndarray) -> int:
        h, w = frame.shape[:2]
        y1, y2 = int(h * 0.86), int(h * 0.94)
        x1, x2 = int(w * 0.025), int(w * 0.16)
        health_region = frame[y1:y2, x1:x2]
        if health_region.size == 0:
            return self.health
        hsv = cv2.cvtColor(health_region, cv2.COLOR_BGR2HSV)
        green_mask = cv2.inRange(hsv, np.array([35, 80, 80]), np.array([90, 255, 255]))
        ratio = cv2.countNonZero(green_mask) / max(green_mask.size, 1)
        estimate = int(round(min(1.0, ratio * 3.8) * 100))
        if estimate > 0:
            self.health = estimate
        return self.health

    async def identify_weapon(self, frame: np.ndarray) -> str:
        now = time.monotonic()
        if now - self._last_weapon_ocr < self._weapon_ocr_interval:
            return self.current_weapon
        self._last_weapon_ocr = now

        h, w = frame.shape[:2]
        weapon_region = frame[int(h * 0.80):h, int(w * 0.74):w]
        if weapon_region.size == 0:
            return self.current_weapon
        gray = cv2.cvtColor(weapon_region, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
        try:
            text = await asyncio.to_thread(pytesseract.image_to_string, gray, config="--psm 6")
            cleaned = " ".join(text.split())
            if cleaned:
                self.current_weapon = cleaned[:80]
        except Exception:
            pass
        return self.current_weapon

    async def analyze_minimap(self, frame: np.ndarray) -> Dict:
        h, w = frame.shape[:2]
        minimap_region = frame[0:int(h * 0.25), 0:int(w * 0.24)]
        if minimap_region.size == 0:
            return {"enemies_on_map": 0, "teammates_visible": 0, "danger_zones": []}
        hsv = cv2.cvtColor(minimap_region, cv2.COLOR_BGR2HSV)
        enemy_mask = cv2.inRange(hsv, np.array([141, 145, 135]), np.array([159, 255, 255]))
        teammate_mask = cv2.inRange(hsv, np.array([96, 120, 120]), np.array([132, 255, 255]))
        return {
            "enemies_on_map": int(cv2.countNonZero(enemy_mask) // 55),
            "teammates_visible": int(cv2.countNonZero(teammate_mask) // 55),
            "danger_zones": [],
        }

    @staticmethod
    def get_screen_direction(x: int, y: int, frame_shape: Tuple[int, int, int]) -> str:
        screen_h, screen_w = frame_shape[:2]
        if x < screen_w * 0.33:
            horizontal = "يسار"
        elif x < screen_w * 0.66:
            horizontal = "وسط"
        else:
            horizontal = "يمين"
        if y < screen_h * 0.33:
            vertical = "أعلى"
        elif y < screen_h * 0.66:
            vertical = "وسط"
        else:
            vertical = "أسفل"
        return f"{vertical} {horizontal}"

    @staticmethod
    def estimate_distance(bbox_height: int, frame_height: int) -> str:
        relative = bbox_height / max(frame_height, 1)
        if relative > 0.30:
            return "قريب جداً"
        if relative > 0.18:
            return "قريب"
        if relative > 0.09:
            return "متوسط"
        return "بعيد"

    def annotate_frame(self, frame: np.ndarray, game_state: Dict) -> np.ndarray:
        output = frame.copy()
        h, w = output.shape[:2]
        for enemy in game_state.get("enemies", []):
            x, y = enemy["position"]
            bw, bh = enemy["size"]
            confidence = enemy.get("confidence", 0.0)
            cv2.rectangle(output, (x, y), (x + bw, y + bh), (255, 0, 255), 2)
            cv2.putText(
                output,
                f"MAGENTA BODY {confidence:.2f}",
                (x, max(18, y - 7)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 0, 255),
                1,
                cv2.LINE_AA,
            )
        cv2.drawMarker(
            output,
            (w // 2, h // 2),
            (255, 255, 255),
            markerType=cv2.MARKER_CROSS,
            markerSize=20,
            thickness=1,
        )
        return output


class TacticalAdvisor:
    """مستشار تكتيكي للاختبار المحلي/الأوفلاين."""

    def __init__(self):
        self.game_state = None
        self.previous_state = None

    async def analyze_situation(self, game_state: Dict) -> List[str]:
        suggestions: List[str] = []
        enemies = game_state.get("enemies", [])
        health = game_state.get("health", 100)
        weapon = game_state.get("weapon", "")
        teammates = game_state.get("teammates", [])
        if len(enemies) > 3:
            suggestions.append("⚠️ أهداف كثيرة ظاهرة - استخدم cover")
        elif len(enemies) == 1:
            suggestions.append("🎯 هدف واحد ظاهر")
        if health < 30:
            suggestions.append("❤️ الصحة منخفضة")
        for enemy in enemies[:4]:
            direction = enemy.get("screen_location", "")
            distance = enemy.get("distance_estimate", "")
            confidence = enemy.get("confidence", 0.0)
            suggestions.append(f"🔎 جسم {direction} ({distance}) conf={confidence:.2f}")
        if len(teammates) < 2:
            suggestions.append("👥 عدد الزملاء الظاهر قليل")
        weapon_l = weapon.lower()
        if "sniper" in weapon_l:
            suggestions.append("💡 قناصة: حافظ على مسافة")
        elif "pdw" in weapon_l or "smg" in weapon_l:
            suggestions.append("💡 سلاح قصير: مناسب للمسافة القريبة")
        return suggestions

    async def get_positioning_advice(self, game_state: Dict) -> str:
        enemies = game_state.get("enemies", [])
        if not enemies:
            return "✅ لا يوجد جسم FF00FF مطابق لفلتر اللاعب"
        positions = [enemy.get("screen_location", "") for enemy in enemies]
        if all("يمين" in pos for pos in positions):
            return "← التجمع المرصود جهة اليمين"
        if all("يسار" in pos for pos in positions):
            return "→ التجمع المرصود جهة اليسار"
        return "⚠️ أجسام مرصودة في أكثر من جهة"


class CoachingOverlay:
    """واجهة Coaching على شاشة الكمبيوتر."""

    def __init__(self):
        self.overlay_window: Optional[tk.Tk] = None
        self.canvas: Optional[Canvas] = None

    def create_overlay(self) -> None:
        self.overlay_window = tk.Tk()
        self.overlay_window.title("AI Coach - Offline Test")
        self.overlay_window.attributes("-topmost", True)
        self.overlay_window.attributes("-alpha", 0.88)
        self.overlay_window.geometry("430x610+1460+80")
        self.overlay_window.configure(bg="#1a1a1a")
        self.overlay_window.overrideredirect(True)
        self.canvas = Canvas(self.overlay_window, bg="#1a1a1a", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

    def update_display(self, suggestions: List[str], game_state: Dict, fps: float) -> None:
        if not self.overlay_window or not self.canvas:
            return
        self.canvas.delete("all")
        self.canvas.create_text(
            215,
            22,
            text="🎮 AI COACH — USB CAPTURE",
            font=("Arial", 15, "bold"),
            fill="#00FF88",
        )
        y = 55
        rows = [
            (f"FPS: {fps:.1f}", "#FFFFFF"),
            (f"FF00FF bodies: {len(game_state.get('enemies', []))}", "#FF55FF"),
            (f"Health estimate: {game_state.get('health', 0)}%", "#66FF66"),
            (f"Weapon OCR: {game_state.get('weapon', 'Unknown')}", "#FFFF66"),
        ]
        for text, color in rows:
            self.canvas.create_text(18, y, text=text, font=("Arial", 11), fill=color, anchor="w")
            y += 28
        y += 10
        self.canvas.create_text(
            215,
            y,
            text="📋 Vision / Tactical Readout",
            font=("Arial", 13, "bold"),
            fill="#55AAFF",
        )
        y += 32
        for suggestion in suggestions[:10]:
            self.canvas.create_text(
                18,
                y,
                text=suggestion,
                font=("Arial", 10),
                fill="#FFFFFF",
                anchor="w",
                width=395,
            )
            y += 31
        self.overlay_window.update_idletasks()
        self.overlay_window.update()

    def close(self) -> None:
        if self.overlay_window is not None:
            try:
                self.overlay_window.destroy()
            except tk.TclError:
                pass
            self.overlay_window = None


class RealtimeAICoach:
    """البوت الرئيسي - USB capture vision coach للاختبار المحلي/الأوفلاين."""

    def __init__(
        self,
        device_index: Optional[int],
        width: int,
        height: int,
        fps: int,
        preview: bool,
        overlay_enabled: bool,
        mask_hud: bool,
    ):
        self.screen_reader = ScreenReader(device_index, width, height, fps)
        self.analyzer = GameStateAnalyzer(enemy_hex="#FF00FF", mask_hud=mask_hud)
        self.advisor = TacticalAdvisor()
        self.overlay = CoachingOverlay()
        self.running = False
        self.preview = preview
        self.overlay_enabled = overlay_enabled
        self._fps = 0.0
        self._fps_frames = 0
        self._fps_started = time.perf_counter()

        print("\n" + "=" * 64)
        print("[🎮 REALTIME AI COACH — USB HDMI CAPTURE]")
        print("=" * 64)
        print(f"[INFO] device: {self.screen_reader.active_device}")
        print(f"[INFO] enemy highlight: {self.analyzer.enemy_hex}")
        print("[INFO] mode: local/offline vision testing")
        print("[INFO] ESC/Q في Preview لإيقاف البرنامج")
        print("=" * 64 + "\n")

    def _update_fps(self) -> None:
        self._fps_frames += 1
        elapsed = time.perf_counter() - self._fps_started
        if elapsed >= 0.75:
            self._fps = self._fps_frames / elapsed
            self._fps_frames = 0
            self._fps_started = time.perf_counter()

    async def main_loop(self) -> None:
        if self.overlay_enabled:
            self.overlay.create_overlay()
        self.running = True
        frame_count = 0
        try:
            while self.running:
                frame = self.screen_reader.capture_screen()
                game_state = await self.analyzer.analyze_frame(frame)
                suggestions = await self.advisor.analyze_situation(game_state)
                positioning = await self.advisor.get_positioning_advice(game_state)
                if positioning not in suggestions:
                    suggestions.insert(0, positioning)
                self._update_fps()
                if self.overlay_enabled:
                    self.overlay.update_display(suggestions, game_state, self._fps)
                if self.preview:
                    preview_frame = self.analyzer.annotate_frame(frame, game_state)
                    cv2.putText(
                        preview_frame,
                        f"Vision FPS: {self._fps:.1f}",
                        (20, 35),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.85,
                        (255, 255, 255),
                        2,
                        cv2.LINE_AA,
                    )
                    cv2.imshow("USB Capture - FF00FF Body Tracking", preview_frame)
                    key = cv2.waitKey(1) & 0xFF
                    if key in (27, ord("q")):
                        self.running = False
                if frame_count % 120 == 0:
                    print(
                        f"[{datetime.now().strftime('%H:%M:%S')}] "
                        f"vision_fps={self._fps:.1f} bodies={len(game_state['enemies'])}"
                    )
                    for suggestion in suggestions[:4]:
                        print(f"  {suggestion}")
                frame_count += 1
                await asyncio.sleep(0)
        except KeyboardInterrupt:
            print("\n[X] Stopping AI Coach...")
        finally:
            self.running = False
            self.screen_reader.release()
            self.overlay.close()
            cv2.destroyAllWindows()

    async def run(self) -> None:
        print("\n[🚀 Starting Real-time AI Coach]\n")
        await self.main_loop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="USB HDMI Capture vision coach for local/offline testing")
    parser.add_argument("--device", default="auto", help="USB capture index: auto, 0, 1, 2...")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=120)
    parser.add_argument("--preview", action="store_true", help="show annotated capture preview")
    parser.add_argument("--no-overlay", action="store_true", help="disable Tk coaching overlay")
    parser.add_argument("--no-hud-mask", action="store_true", help="do not exclude common HUD regions")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    device_index = None if str(args.device).lower() == "auto" else int(args.device)
    coach = RealtimeAICoach(
        device_index=device_index,
        width=args.width,
        height=args.height,
        fps=args.fps,
        preview=args.preview,
        overlay_enabled=not args.no_overlay,
        mask_hud=not args.no_hud_mask,
    )
    await coach.run()


if __name__ == "__main__":
    asyncio.run(main())
