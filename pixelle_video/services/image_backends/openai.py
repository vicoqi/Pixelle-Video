from typing import Optional

from loguru import logger
from openai import AsyncOpenAI

from pixelle_video.models.media import MediaResult
from pixelle_video.services.image_backends.base import ImageBackend


def _snap_to_16(value: int) -> int:
    """Snap a dimension to nearest multiple of 16 (min 256)"""
    snapped = max(256, round(value / 16) * 16)
    return snapped


def _resolve_size(
    width: Optional[int],
    height: Optional[int],
    default_size: str,
) -> str:
    """
    Resolve image size for gpt-image-2.

    gpt-image-2 constraints:
    - Max edge: 3840px
    - Both edges: multiples of 16
    - Aspect ratio <= 3:1
    - Total pixels: 655,360 to 8,294,400

    If width/height provided: snap to valid values.
    If not provided: use default_size from config.
    """
    if width is None or height is None:
        return default_size

    w = _snap_to_16(min(width, 3840))
    h = _snap_to_16(min(height, 3840))

    # Enforce max ratio 3:1
    if w > h * 3:
        w = h * 3
    elif h > w * 3:
        h = w * 3

    # Enforce minimum total pixels (655,360)
    if w * h < 655_360:
        h = max(h, 816)
        w = max(w, 816)

    return f"{w}x{h}"


class OpenAIImageBackend(ImageBackend):
    """OpenAI gpt-image-2 image generation backend"""

    def __init__(self, config: dict):
        """
        Args:
            config: OpenAI image config dict with api_key, base_url, model, quality, size
        """
        self._config = config
        self._api_key = config.get("api_key", "")
        self._base_url = config.get("base_url", "")
        self._model = config.get("model", "gpt-image-2")
        self._quality = config.get("quality", "medium")
        self._default_size = config.get("size", "1024x1024")

        if not self._api_key:
            raise ValueError(
                "OpenAI image generation requires 'comfyui.image.openai.api_key' in config.yaml. "
                "Please set it or switch provider to 'comfyui'."
            )

        client_kwargs = {"api_key": self._api_key}
        if self._base_url:
            client_kwargs["base_url"] = self._base_url
        self._client = AsyncOpenAI(**client_kwargs)

    async def generate(
        self,
        prompt: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        **params,
    ) -> MediaResult:
        """Generate image using OpenAI gpt-image-2"""
        size = _resolve_size(width, height, self._default_size)

        logger.info(f"OpenAI image generation: model={self._model}, size={size}, quality={self._quality}")
        logger.debug(f"Prompt: {prompt[:100]}...")

        try:
            response = await self._client.images.generate(
                model=self._model,
                prompt=prompt,
                n=1,
                size=size,
                quality=self._quality,
                response_format="url",
            )
        except Exception as e:
            logger.error(f"OpenAI image generation failed: {e}")
            raise

        image_url = response.data[0].url
        if not image_url:
            raise Exception("OpenAI returned no image URL (response.data[0].url is None)")
        logger.info(f"OpenAI generated image: {image_url}")

        return MediaResult(media_type="image", url=image_url)
