"""Detection alert pusher for WeChat Work / DingTalk / email.

Sends real-time notifications when target species are detected above
a confidence threshold. Supports webhook-based push for Chinese
enterprise messaging platforms.
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_ALERT_CONFIG_PATH = Path(__file__).parent / "data" / "alert_config.json"


def _load_config() -> dict:
    if _ALERT_CONFIG_PATH.exists():
        return json.loads(_ALERT_CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


def _save_config(config: dict):
    _ALERT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ALERT_CONFIG_PATH.write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
    )


class AlertPusher:
    def __init__(self):
        self.config = _load_config()

    def configure(
        self,
        target_species: list[str],
        min_confidence: float = 0.8,
        wechat_webhook: Optional[str] = None,
        dingtalk_webhook: Optional[str] = None,
        email: Optional[str] = None,
        platform_url: str = "",
    ):
        self.config = {
            "target_species": target_species,
            "min_confidence": min_confidence,
            "wechat_webhook": wechat_webhook,
            "dingtalk_webhook": dingtalk_webhook,
            "email": email,
            "platform_url": platform_url,
            "enabled": True,
        }
        _save_config(self.config)

    def get_config(self) -> dict:
        return self.config

    def should_alert(self, detection: dict) -> bool:
        if not self.config.get("enabled"):
            return False
        species = detection.get("species_scientific") or detection.get("species", "")
        targets = self.config.get("target_species", [])
        if targets and species not in targets:
            return False
        confidence = detection.get("confidence", 0)
        if isinstance(confidence, (int, float)) and confidence < self.config.get(
            "min_confidence", 0.8
        ):
            return False
        return True

    async def push_if_needed(self, detection: dict):
        if not self.should_alert(detection):
            return
        species = detection.get("species_scientific") or detection.get("species", "")
        species_zh = detection.get("species_chinese", species)
        confidence = detection.get("confidence", 0)
        site = detection.get("site_name", "N/A")
        time_str = detection.get("detected_at", "")
        device = detection.get("device_id", "N/A")

        markdown = (
            f"## 🐦 目标种检测告警\n"
            f"**物种**: {species_zh} (*{species}*)\n"
            f"**置信度**: {confidence:.1%}\n"
            f"**站点**: {site}\n"
            f"**时间**: {time_str}\n"
            f"**设备**: {device}"
        )

        if self.config.get("wechat_webhook"):
            await self._push_wechat(markdown)
        if self.config.get("dingtalk_webhook"):
            await self._push_dingtalk(markdown, species_zh)

    async def _push_wechat(self, markdown: str):
        url = self.config["wechat_webhook"]
        payload = {"msgtype": "markdown", "markdown": {"content": markdown}}
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code != 200:
                    logger.warning("WeChat push failed: %s", resp.text)
        except Exception:
            logger.warning("WeChat push error", exc_info=True)

    async def _push_dingtalk(self, markdown: str, title: str = "检测告警"):
        url = self.config["dingtalk_webhook"]
        payload = {
            "msgtype": "markdown",
            "markdown": {"title": title, "text": markdown},
        }
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code != 200:
                    logger.warning("DingTalk push failed: %s", resp.text)
        except Exception:
            logger.warning("DingTalk push error", exc_info=True)
