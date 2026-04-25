# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
GLM-4.6V Analysis Service - Image/Video recognition via ZhipuAI API

Supports streaming responses with thinking mode.
"""

import asyncio
import base64
from pathlib import Path

from loguru import logger
from zai import ZhipuAiClient


class GLMAnalysisService:
    """ZhipuAI GLM-4.6V image/video analysis service"""

    def __init__(self, config: dict):
        api_key = config.get("api_key", "")
        if not api_key:
            raise ValueError("GLM API Key is required")

        base_url = config.get("base_url") or None
        self._client = ZhipuAiClient(api_key=api_key, base_url=base_url)
        self._model = config.get("model", "glm-4.6v")
        logger.info(f"GLM analysis service initialized (model: {self._model})")

    async def analyze_image(self, image_path: str, prompt: str = "请详细描述这张图片的内容") -> str:
        """Analyze image via GLM-4.6V streaming API"""
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        logger.info(f"GLM analyzing image: {path.name}")
        base64_url = self._encode_image(path)
        return await self._analyze(base64_url, prompt)

    async def analyze_video(self, video_path: str, prompt: str = "请详细描述这个视频的内容") -> str:
        """Analyze video via GLM-4.6V streaming API"""
        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")

        logger.info(f"GLM analyzing video: {path.name}")
        base64_url = self._encode_video(path)
        return await self._analyze(base64_url, prompt)

    async def _analyze(self, media_url: str, prompt: str) -> str:
        """Streaming call, collect content parts and return full description"""
        def _call():
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": media_url}},
                        {"type": "text", "text": prompt}
                    ]
                }],
                thinking={"type": "enabled"},
                stream=True,
            )
            content_parts = []
            for chunk in response:
                delta = chunk.choices[0].delta
                if hasattr(delta, "content") and delta.content:
                    content_parts.append(delta.content)
            if not content_parts:
                raise Exception("GLM returned empty response")
            return "".join(content_parts)

        return await asyncio.to_thread(_call)

    def _encode_image(self, path: Path) -> str:
        """Encode image to data:image/xxx;base64,... format"""
        suffix = path.suffix.lower().lstrip(".")
        mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "gif": "gif"}.get(suffix, "jpeg")
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return f"data:image/{mime};base64,{b64}"

    def _encode_video(self, path: Path) -> str:
        """Encode video to data:video/xxx;base64,... format"""
        suffix = path.suffix.lower().lstrip(".")
        mime = {"mp4": "mp4", "mov": "quicktime", "avi": "x-msvideo", "webm": "webm"}.get(suffix, "mp4")
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return f"data:video/{mime};base64,{b64}"
