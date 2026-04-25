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
Image generation endpoints
"""

from fastapi import APIRouter, HTTPException
from loguru import logger

from api.dependencies import PixelleVideoDep
from api.schemas.image import ImageGenerateRequest, ImageGenerateResponse

router = APIRouter(prefix="/image", tags=["Basic Services"])


@router.post("/generate", response_model=ImageGenerateResponse)
async def image_generate(
    request: ImageGenerateRequest,
    pixelle_video: PixelleVideoDep
):
    """
    Image generation endpoint

    Generate image from text prompt.
    Supports both ComfyUI and OpenAI backends.

    - **prompt**: Image description/prompt
    - **width**: Image width (512-2048)
    - **height**: Image height (512-2048)
    - **workflow**: Optional custom workflow filename (ComfyUI only)
    - **provider**: Optional provider override ("comfyui" or "openai")

    Returns path to generated image.
    """
    try:
        logger.info(f"Image generation request: {request.prompt[:50]}...")

        # If provider specified in request, temporarily override backend
        if request.provider:
            pixelle_video.media.set_provider(request.provider)

        media_result = await pixelle_video.media(
            prompt=request.prompt,
            width=request.width,
            height=request.height,
            workflow=request.workflow
        )
        
        # For backward compatibility, only support image results in /image endpoint
        if media_result.is_video:
            raise HTTPException(
                status_code=400,
                detail="Video workflow used. Please use /media/generate endpoint for video generation."
            )
        
        return ImageGenerateResponse(
            image_path=media_result.url
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

