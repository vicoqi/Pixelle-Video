from abc import ABC, abstractmethod
from typing import Optional

from pixelle_video.models.media import MediaResult


class ImageBackend(ABC):
    """Abstract base class for image generation backends"""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        **params,
    ) -> MediaResult:
        """
        Generate an image from a text prompt.

        Args:
            prompt: Image generation prompt
            width: Desired image width
            height: Desired image height
            **params: Backend-specific parameters

        Returns:
            MediaResult with media_type="image" and url pointing to the generated image
        """
        pass
