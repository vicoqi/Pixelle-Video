# OpenAI gpt-image-2 Image Generation Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add OpenAI gpt-image-2 as a parallel image generation backend alongside ComfyUI, selectable via config.

**Architecture:** Strategy pattern — an `ImageBackend` ABC with `ComfyUIBackend` (existing logic extracted) and `OpenAIImageBackend` (new). `MediaService` routes image calls to the configured backend; video calls still go through ComfyUI. No changes to `FrameProcessor`, pipeline, or downstream callers.

**Tech Stack:** Python 3.11+, `openai>=2.6.0` (already in deps), Pydantic, asyncio

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `pixelle_video/config/schema.py` | Modify | Add `OpenAIImageConfig`, extend `ImageSubConfig` with `provider` + `openai` fields |
| `pixelle_video/config/__init__.py` | Modify | Export `OpenAIImageConfig` |
| `pixelle_video/config/manager.py` | Modify | Add `openai` fields to `get_comfyui_config()` |
| `pixelle_video/services/image_backends/__init__.py` | Create | Module exports |
| `pixelle_video/services/image_backends/base.py` | Create | `ImageBackend` ABC |
| `pixelle_video/services/image_backends/comfyui.py` | Create | ComfyUI image backend (extracted from MediaService) |
| `pixelle_video/services/image_backends/openai.py` | Create | OpenAI gpt-image-2 backend |
| `pixelle_video/services/media.py` | Modify | Route image calls through backend strategy |
| `api/schemas/image.py` | Modify | Add `provider` field |
| `api/routers/image.py` | Modify | Pass `provider` through |
| `web/components/style_config.py` | Modify | Add provider selector UI |
| `config.example.yaml` | Modify | Add OpenAI config example |
| `docs/superpowers/specs/2026-04-25-openai-image-generation-design.md` | Already exists | Design spec (already committed) |

---

### Task 1: Add configuration schema for OpenAI image backend

**Files:**
- Modify: `pixelle_video/config/schema.py`
- Modify: `pixelle_video/config/__init__.py`
- Modify: `config.example.yaml`

- [ ] **Step 1: Add `OpenAIImageConfig` and update `ImageSubConfig` in `schema.py`**

In `pixelle_video/config/schema.py`, add `OpenAIImageConfig` class BEFORE `ImageSubConfig`, then update `ImageSubConfig` to include `provider` and `openai` fields:

```python
class OpenAIImageConfig(BaseModel):
    """OpenAI image generation configuration"""
    api_key: str = Field(default="", description="OpenAI API Key for image generation")
    base_url: str = Field(default="", description="OpenAI API Base URL (optional, for proxies)")
    model: str = Field(default="gpt-image-2", description="OpenAI image model name")
    quality: str = Field(default="medium", description="Image quality: low, medium, high")
    size: str = Field(default="1024x1024", description="Default image size")


class ImageSubConfig(BaseModel):
    """Image-specific configuration (under comfyui.image)"""
    provider: str = Field(default="comfyui", description="Image generation provider: comfyui or openai")
    default_workflow: Optional[str] = Field(default=None, description="Default image workflow (optional)")
    prompt_prefix: str = Field(
        default="Minimalist black-and-white matchstick figure style illustration, clean lines, simple sketch style",
        description="Prompt prefix for all image generation"
    )
    openai: OpenAIImageConfig = Field(default_factory=OpenAIImageConfig, description="OpenAI image generation configuration")
```

- [ ] **Step 2: Update `config/__init__.py` exports**

In `pixelle_video/config/__init__.py`, add `OpenAIImageConfig` to the import line and `__all__`:

Change:
```python
from .schema import PixelleVideoConfig, LLMConfig, ComfyUIConfig, TTSSubConfig, ImageSubConfig, VideoSubConfig
```
To:
```python
from .schema import PixelleVideoConfig, LLMConfig, ComfyUIConfig, TTSSubConfig, ImageSubConfig, VideoSubConfig, OpenAIImageConfig
```

Add `"OpenAIImageConfig"` to the `__all__` list.

- [ ] **Step 3: Update `config.example.yaml`**

Add OpenAI section under `comfyui.image`:

```yaml
  # Image-specific configuration
  image:
    # Image generation provider: "comfyui" (default) or "openai"
    provider: comfyui

    # Required: Default workflow to use (for ComfyUI provider)
    # Options: runninghub/image_flux.json (recommended, no local setup)
    #          selfhost/image_flux.json (requires local ComfyUI)
    default_workflow: runninghub/image_flux.json

    # Image prompt prefix (optional)
    prompt_prefix: "Minimalist black-and-white matchstick figure style illustration, clean lines, simple sketch style"

    # OpenAI image generation config (used when provider=openai)
    openai:
      api_key: ""           # OpenAI API Key
      base_url: ""           # Optional: for proxies or compatible APIs
      model: "gpt-image-2"  # Image generation model
      quality: "medium"     # Image quality: low, medium, high
      size: "1024x1024"     # Default output size
```

- [ ] **Step 4: Commit**

```bash
git add pixelle_video/config/schema.py pixelle_video/config/__init__.py config.example.yaml
git commit -m "feat: add OpenAI image generation config schema"
```

---

### Task 2: Add `provider` and `openai` to ConfigManager

**Files:**
- Modify: `pixelle_video/config/manager.py`

- [ ] **Step 1: Update `get_comfyui_config()` to include new fields**

In `pixelle_video/config/manager.py`, update the `get_comfyui_config` method. Replace the `"image"` dict to include `provider` and `openai`:

```python
            "image": {
                "provider": self.config.comfyui.image.provider,
                "default_workflow": self.config.comfyui.image.default_workflow,
                "prompt_prefix": self.config.comfyui.image.prompt_prefix,
                "openai": {
                    "api_key": self.config.comfyui.image.openai.api_key,
                    "base_url": self.config.comfyui.image.openai.base_url,
                    "model": self.config.comfyui.image.openai.model,
                    "quality": self.config.comfyui.image.openai.quality,
                    "size": self.config.comfyui.image.openai.size,
                },
            },
```

- [ ] **Step 2: Commit**

```bash
git add pixelle_video/config/manager.py
git commit -m "feat: expose OpenAI image config in ConfigManager"
```

---

### Task 3: Create ImageBackend ABC

**Files:**
- Create: `pixelle_video/services/image_backends/__init__.py`
- Create: `pixelle_video/services/image_backends/base.py`

- [ ] **Step 1: Create `__init__.py`**

```python
from pixelle_video.services.image_backends.base import ImageBackend
from pixelle_video.services.image_backends.comfyui import ComfyUIBackend
from pixelle_video.services.image_backends.openai import OpenAIImageBackend

__all__ = ["ImageBackend", "ComfyUIBackend", "OpenAIImageBackend"]
```

- [ ] **Step 2: Create `base.py`**

```python
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
```

- [ ] **Step 3: Commit**

```bash
git add pixelle_video/services/image_backends/__init__.py pixelle_video/services/image_backends/base.py
git commit -m "feat: add ImageBackend abstract base class"
```

---

### Task 4: Create ComfyUIBackend (extract from MediaService)

**Files:**
- Create: `pixelle_video/services/image_backends/comfyui.py`

This extracts the ComfyUI image generation logic from `MediaService.__call__()` into a standalone backend class.

- [ ] **Step 1: Create `comfyui.py`**

```python
import base64
import os
import tempfile
from typing import Optional

from loguru import logger

from pixelle_video.models.media import MediaResult
from pixelle_video.services.image_backends.base import ImageBackend


class ComfyUIBackend(ImageBackend):
    """ComfyUI-based image generation backend"""

    def __init__(self, media_service, config: dict):
        """
        Args:
            media_service: MediaService instance (for accessing core ComfyKit)
            config: Image-specific config dict
        """
        self._media_service = media_service
        self._config = config

    async def generate(
        self,
        prompt: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        **params,
    ) -> MediaResult:
        """Generate image using ComfyUI workflow"""
        from comfykit import ComfyKit

        workflow = params.get("workflow")
        workflow_info = self._media_service._resolve_workflow(workflow=workflow)

        workflow_params = {"prompt": prompt}
        if width is not None:
            workflow_params["width"] = width
        if height is not None:
            workflow_params["height"] = height
        for key in ("negative_prompt", "steps", "seed", "cfg", "sampler"):
            if key in params and params[key] is not None:
                workflow_params[key] = params[key]
        workflow_params.update(
            {k: v for k, v in params.items() if k not in ("workflow", "negative_prompt", "steps", "seed", "cfg", "sampler")}
        )

        logger.debug(f"ComfyUI backend parameters: {workflow_params}")

        kit = await self._media_service.core._get_or_create_comfykit()

        if workflow_info["source"] == "runninghub" and "workflow_id" in workflow_info:
            workflow_input = workflow_info["workflow_id"]
            logger.info(f"Executing RunningHub workflow: {workflow_input}")
        else:
            workflow_input = workflow_info["path"]
            logger.info(f"Executing selfhost workflow: {workflow_input}")

        result = await kit.execute(workflow_input, workflow_params)

        if result.status != "completed":
            error_msg = result.msg or "Unknown error"
            logger.error(f"ComfyUI image generation failed: {error_msg}")
            raise Exception(f"ComfyUI image generation failed: {error_msg}")

        if not result.images:
            raise Exception("No image generated by ComfyUI workflow")

        image_url = result.images[0]
        logger.info(f"ComfyUI generated image: {image_url}")

        return MediaResult(media_type="image", url=image_url)
```

- [ ] **Step 2: Commit**

```bash
git add pixelle_video/services/image_backends/comfyui.py
git commit -m "feat: add ComfyUI image backend (extracted from MediaService)"
```

---

### Task 5: Create OpenAIImageBackend

**Files:**
- Create: `pixelle_video/services/image_backends/openai.py`

This is the core new functionality. It calls OpenAI's `images.generate` API with `gpt-image-2`, decodes the `b64_json` response, and saves it locally.

**Key behavior:**
- gpt-image-2 supports flexible sizes: max edge 3840px, multiples of 16, ratio ≤ 3:1
- If user passes `width`/`height`, snap to nearest multiple of 16 and validate constraints
- If no size specified, use config `size`
- Save decoded image to `output/openai_images/` with UUID filename
- Returns `MediaResult(media_type="image", url=local_path)`

- [ ] **Step 1: Create `openai.py`**

```python
import base64
import os
import uuid
from pathlib import Path
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
    - Aspect ratio ≤ 3:1
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

    # Enforce min total pixels (655,360)
    min_side = 256
    if w * h < 655_360:
        w = max(w, min_side)
        h = max(h, min_side)

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
                response_format="b64_json",
            )
        except Exception as e:
            logger.error(f"OpenAI image generation failed: {e}")
            raise

        image_b64 = response.data[0].b64_json
        image_bytes = base64.b64decode(image_b64)

        # Save to output directory
        output_dir = Path("output") / "openai_images"
        output_dir.mkdir(parents=True, exist_ok=True)
        image_filename = f"{uuid.uuid4().hex}.png"
        image_path = str(output_dir / image_filename)

        with open(image_path, "wb") as f:
            f.write(image_bytes)

        logger.info(f"OpenAI generated image saved: {image_path}")

        return MediaResult(media_type="image", url=image_path)
```

- [ ] **Step 2: Commit**

```bash
git add pixelle_video/services/image_backends/openai.py
git commit -m "feat: add OpenAI gpt-image-2 image generation backend"
```

---

### Task 6: Refactor MediaService to use backend strategy

**Files:**
- Modify: `pixelle_video/services/media.py`

This is the key integration step. `MediaService.__call__()` routes image generation to the selected backend. Video generation stays with ComfyUI.

- [ ] **Step 1: Add backend creation to `__init__`**

Add to `MediaService.__init__()` after the `super().__init__()` call:

```python
        self._image_backend = self._create_image_backend()
```

Add the `_create_image_backend` method to `MediaService`:

```python
    def _create_image_backend(self):
        """Create image backend based on provider config"""
        from pixelle_video.services.image_backends.base import ImageBackend

        provider = self.config.get("provider", "comfyui")
        if provider == "openai":
            from pixelle_video.services.image_backends.openai import OpenAIImageBackend
            try:
                return OpenAIImageBackend(self.config.get("openai", {}))
            except ValueError as e:
                logger.warning(f"OpenAI backend init failed: {e}. Falling back to ComfyUI.")
                from pixelle_video.services.image_backends.comfyui import ComfyUIBackend
                return ComfyUIBackend(self, self.config)
        from pixelle_video.services.image_backends.comfyui import ComfyUIBackend
        return ComfyUIBackend(self, self.config)
```

- [ ] **Step 2: Modify `__call__` to route image calls through backend**

In `MediaService.__call__()`, insert a routing block at the top of the method body (after the docstring). The existing ComfyUI workflow execution code only runs for video or when backend is ComfyUI.

Add this block right after the existing docstring and before `# 1. Resolve workflow`:

```python
        # Route image generation through backend strategy
        if media_type == "image" and self._image_backend is not None:
            return await self._image_backend.generate(
                prompt=prompt,
                width=width,
                height=height,
                workflow=workflow,
                negative_prompt=negative_prompt,
                steps=steps,
                seed=seed,
                cfg=cfg,
                sampler=sampler,
                **params,
            )
```

This goes between the closing `"""` of the docstring and the `# 1. Resolve workflow` comment. The rest of the existing `__call__` body (ComfyUI workflow execution) becomes the video path automatically since `media_type == "image"` won't reach it anymore.

- [ ] **Step 3: Verify the full `__call__` method looks correct**

The method should now look like:

```python
    async def __call__(
        self,
        prompt: str,
        workflow: Optional[str] = None,
        media_type: str = "image",
        comfyui_url: Optional[str] = None,
        runninghub_api_key: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        duration: Optional[float] = None,
        negative_prompt: Optional[str] = None,
        steps: Optional[int] = None,
        seed: Optional[int] = None,
        cfg: Optional[float] = None,
        sampler: Optional[str] = None,
        **params
    ) -> MediaResult:
        # Route image generation through backend strategy
        if media_type == "image" and self._image_backend is not None:
            return await self._image_backend.generate(
                prompt=prompt,
                width=width,
                height=height,
                workflow=workflow,
                negative_prompt=negative_prompt,
                steps=steps,
                seed=seed,
                cfg=cfg,
                sampler=sampler,
                **params,
            )

        # 1. Resolve workflow (returns structured info)
        workflow_info = self._resolve_workflow(workflow=workflow)
        # ... rest of existing code unchanged (video path)
```

- [ ] **Step 4: Commit**

```bash
git add pixelle_video/services/media.py
git commit -m "feat: route image generation through backend strategy in MediaService"
```

---

### Task 7: Update REST API to pass provider

**Files:**
- Modify: `api/schemas/image.py`
- Modify: `api/routers/image.py`

- [ ] **Step 1: Add `provider` field to `ImageGenerateRequest`**

In `api/schemas/image.py`, add `provider` field to `ImageGenerateRequest`:

```python
class ImageGenerateRequest(BaseModel):
    """Image generation request"""
    prompt: str = Field(..., description="Image generation prompt")
    width: int = Field(1024, ge=512, le=2048, description="Image width")
    height: int = Field(1024, ge=512, le=2048, description="Image height")
    workflow: Optional[str] = Field(None, description="Custom workflow filename")
    provider: Optional[str] = Field(None, description="Image generation provider: comfyui or openai")

    class Config:
        json_schema_extra = {
            "example": {
                "prompt": "A serene mountain landscape at sunset, photorealistic style",
                "width": 1024,
                "height": 1024
            }
        }
```

- [ ] **Step 2: Update `api/routers/image.py` to handle provider override**

The current code calls `pixelle_video.media(prompt=..., width=..., height=..., workflow=...)`. The `MediaService` already handles routing internally based on its config. For API-level provider override, we temporarily swap the backend:

```python
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
            pixelle_video.media._create_and_set_backend(request.provider)

        media_result = await pixelle_video.media(
            prompt=request.prompt,
            width=request.width,
            height=request.height,
            workflow=request.workflow
        )

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
```

- [ ] **Step 3: Add `_create_and_set_backend` method to `MediaService`**

In `pixelle_video/services/media.py`, add this helper method:

```python
    def _create_and_set_backend(self, provider: str):
        """Temporarily override image backend for current request"""
        from pixelle_video.services.image_backends.comfyui import ComfyUIBackend
        from pixelle_video.services.image_backends.openai import OpenAIImageBackend

        if provider == "openai":
            self._image_backend = OpenAIImageBackend(self.config.get("openai", {}))
        else:
            self._image_backend = ComfyUIBackend(self, self.config)
```

- [ ] **Step 4: Commit**

```bash
git add api/schemas/image.py api/routers/image.py pixelle_video/services/media.py
git commit -m "feat: add provider field to image generation API"
```

---

### Task 8: Update Web UI with provider selector

**Files:**
- Modify: `web/components/style_config.py`

Add a provider selector at the top of the Media Generation Section. When OpenAI is selected, show OpenAI config instead of workflow dropdown.

- [ ] **Step 1: Add provider selector and conditional UI**

In `web/components/style_config.py`, locate the "Media Generation Section" block (starts around line 682 with `if template_requires_media:`). After the section title (`st.markdown(f"**{section_title}**")`) and the help expander, but BEFORE the workflow selection code (line 707 `all_workflows = pixelle_video.media.list_workflows()`), insert a provider selector.

Find this block (around line 691-706):

```python
            st.markdown(f"**{section_title}**")
        
            # 1. ComfyUI Workflow selection
            with st.expander(tr("help.feature_description"), expanded=False):
                ...
```

After the expander, insert the provider selector BEFORE the `# Get available workflows` comment:

```python
            # Provider selection (ComfyUI or OpenAI)
            comfyui_config = config_manager.get_comfyui_config()
            media_config_key = "video" if template_media_type == "video" else "image"
            saved_provider = comfyui_config.get(media_config_key, {}).get("provider", "comfyui")

            # Only show provider selector for image templates (not video)
            if template_media_type == "image":
                provider_options = {"comfyui": "ComfyUI", "openai": "OpenAI"}
                selected_provider = st.radio(
                    "Image Provider",
                    options=list(provider_options.keys()),
                    format_func=lambda x: provider_options[x],
                    index=0 if saved_provider != "openai" else 1,
                    horizontal=True,
                    key="image_provider_selector",
                )
            else:
                selected_provider = "comfyui"
```

Then wrap the existing workflow selection in a condition. Replace the existing workflow selection block with:

```python
            if selected_provider == "openai" and template_media_type == "image":
                # OpenAI provider: show config info instead of workflow selector
                openai_config = comfyui_config.get("image", {}).get("openai", {})
                st.info(f"OpenAI Model: **{openai_config.get('model', 'gpt-image-2')}** | Size: **{openai_config.get('size', '1024x1024')}** | Quality: **{openai_config.get('quality', 'medium')}**")

                # OpenAI size selector
                openai_size = st.selectbox(
                    "Output Size",
                    options=["1024x1024", "1536x1024", "1024x1536", "auto"],
                    index=0,
                    key="openai_size_select",
                )

                # No workflow key needed for OpenAI
                workflow_key = None

                # Override provider in media service for this session
                if hasattr(pixelle_video.media, '_create_and_set_backend'):
                    pixelle_video.media._create_and_set_backend("openai")
            else:
                # ComfyUI provider: show workflow selector (existing code)
                all_workflows = pixelle_video.media.list_workflows()

                # Filter workflows based on template media type
                if template_media_type == "video":
                    workflows = [wf for wf in all_workflows if "video_" in wf["key"].lower()]
                else:
                    workflows = [wf for wf in all_workflows if "video_" not in wf["key"].lower()]

                workflow_options = [wf["display_name"] for wf in workflows]
                workflow_keys = [wf["key"] for wf in workflows]

                default_workflow_index = 0

                comfyui_config_wf = config_manager.get_comfyui_config()
                saved_workflow = comfyui_config_wf.get(media_config_key, {}).get("default_workflow", "")
                if saved_workflow and saved_workflow in workflow_keys:
                    default_workflow_index = workflow_keys.index(saved_workflow)

                workflow_display = st.selectbox(
                    "Workflow",
                    workflow_options if workflow_options else ["No workflows found"],
                    index=default_workflow_index,
                    label_visibility="collapsed",
                    key="media_workflow_select"
                )

                if workflow_options:
                    workflow_selected_index = workflow_options.index(workflow_display)
                    workflow_key = workflow_keys[workflow_selected_index]
                else:
                    workflow_key = "runninghub/image_flux.json"

                check_and_warn_selfhost_workflow(workflow_key)

                # Restore ComfyUI backend if switching from OpenAI
                if hasattr(pixelle_video.media, '_create_and_set_backend'):
                    pixelle_video.media._create_and_set_backend("comfyui")
```

- [ ] **Step 2: Fix the `base64` import missing in style_config.py**

The file uses `base64` at line 832 but never imports it. Add `import base64` to the top-level imports in `web/components/style_config.py`.

- [ ] **Step 3: Update the return dict to include provider info**

Update the return statement at the bottom of `render_style_config()` to include `media_provider`:

```python
    return {
        "tts_inference_mode": tts_mode,
        "tts_voice": selected_voice if tts_mode == "local" else None,
        "tts_speed": tts_speed if tts_mode == "local" else None,
        "tts_workflow": tts_workflow_key if tts_mode == "comfyui" else None,
        "ref_audio": str(ref_audio_path) if ref_audio_path else None,
        "frame_template": frame_template,
        "template_params": custom_values_for_video if custom_values_for_video else None,
        "media_workflow": workflow_key,
        "media_provider": selected_provider if template_media_type == "image" else "comfyui",
        "prompt_prefix": prompt_prefix if prompt_prefix else "",
        "media_width": media_width,
        "media_height": media_height
    }
```

- [ ] **Step 4: Commit**

```bash
git add web/components/style_config.py
git commit -m "feat: add OpenAI/ComfyUI provider selector in web UI"
```

---

### Task 9: Integration test — end-to-end validation

**Files:**
- No new files (manual verification)

- [ ] **Step 1: Verify config loads correctly**

Run:
```bash
python3 -c "
from pixelle_video.config import config_manager
print('Provider:', config_manager.config.comfyui.image.provider)
print('OpenAI model:', config_manager.config.comfyui.image.openai.model)
print('OpenAI size:', config_manager.config.comfyui.image.openai.size)
print('Config OK')
"
```
Expected: Prints default values (provider=comfyui, model=gpt-image-2, size=1024x1024), no errors.

- [ ] **Step 2: Verify MediaService initializes with ComfyUI backend by default**

Run:
```bash
python3 -c "
from pixelle_video.services.media import MediaService
svc = MediaService({})
print('Backend type:', type(svc._image_backend).__name__)
print('OK')
"
```
Expected: `ComfyUIBackend`

- [ ] **Step 3: Verify OpenAI backend rejects missing API key**

Run:
```bash
python3 -c "
from pixelle_video.services.image_backends.openai import OpenAIImageBackend
try:
    backend = OpenAIImageBackend({})
    print('ERROR: should have raised ValueError')
except ValueError as e:
    print('Correctly raised:', str(e)[:80])
"
```
Expected: ValueError about missing api_key.

- [ ] **Step 4: Commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: integration test fixes for OpenAI image backend"
```

---

## Self-Review

**Spec coverage:**
1. Configuration structure → Task 1, Task 2 ✓
2. Backend strategy (ABC + ComfyUI + OpenAI) → Task 3, 4, 5 ✓
3. MediaService routing → Task 6 ✓
4. REST API → Task 7 ✓
5. Web UI → Task 8 ✓
6. Error handling (API key missing, API errors) → Task 5 (init check), Task 6 (fallback) ✓

**Placeholder scan:** No TBDs, TODOs, or vague steps found.

**Type consistency:**
- `ImageBackend.generate()` signature: `(prompt: str, width: Optional[int], height: Optional[int], **params) -> MediaResult`
- `ComfyUIBackend.generate()` and `OpenAIImageBackend.generate()` both match
- `MediaService.__call__()` passes all relevant params through to backend
- `MediaResult(media_type="image", url=str)` used consistently
- `_create_and_set_backend(provider: str)` matches usage in API and UI
