# OpenAI gpt-image-2 图片生成集成设计

## 概述

在 Pixelle-Video 中新增 OpenAI gpt-image-2 作为图片生成后端，与现有 ComfyUI 方案并行共存。用户通过配置切换后端，无需修改调用代码。

## 设计决策

- **方案**：策略模式（方案 A）
- **范围**：视频流水线（FrameProcessor）+ REST API + Web UI 全部对齐
- **API Key 管理**：独立配置段，不复用 LLM 的 Key
- **图片分析**：不涉及，保持 ComfyUI

## 1. 配置结构

### config.yaml 新增字段

```yaml
comfyui:
  image:
    provider: "comfyui"          # "comfyui"（默认） 或 "openai"
    default_workflow: "runninghub/image_flux.json"
    prompt_prefix: "..."

    # OpenAI 图片生成配置（provider=openai 时生效）
    openai:
      api_key: ""
      base_url: ""               # 可选，支持代理/兼容接口
      model: "gpt-image-2"
      quality: "medium"          # "low" | "medium" | "high"
      size: "1024x1024"          # 默认输出尺寸
```

### Pydantic 模型变更（`pixelle_video/config/schema.py`）

新增 `OpenAIImageConfig`，扩展 `ImageSubConfig`：

```python
class OpenAIImageConfig(BaseModel):
    api_key: str = ""
    base_url: str = ""
    model: str = "gpt-image-2"
    quality: str = "medium"
    size: str = "1024x1024"

class ImageSubConfig(BaseModel):
    provider: str = "comfyui"
    default_workflow: Optional[str] = None
    prompt_prefix: str = "..."
    openai: OpenAIImageConfig = Field(default_factory=OpenAIImageConfig)
```

## 2. 后端策略架构

### 新增文件结构

```
pixelle_video/services/image_backends/
  __init__.py           # 导出 ImageBackend, ComfyUIBackend, OpenAIImageBackend
  base.py               # ImageBackend 抽象基类
  comfyui.py            # ComfyUIBackend（从 MediaService 提取现有逻辑）
  openai.py             # OpenAIImageBackend（新增）
```

### ImageBackend 抽象基类（`base.py`）

```python
from abc import ABC, abstractmethod
from pixelle_video.models.media import MediaResult

class ImageBackend(ABC):
    @abstractmethod
    async def generate(self, prompt: str, width: int = None, height: int = None, **params) -> MediaResult:
        pass
```

### OpenAIImageBackend（`openai.py`）

核心逻辑：
1. 初始化 OpenAI 客户端（`openai.AsyncOpenAI`）
2. `generate()` 调用 `client.images.generate()`，传入 prompt 和映射后的尺寸
3. 解码返回的 `b64_json`，保存为本地 PNG 文件
4. 返回 `MediaResult(media_type="image", url=本地文件路径)`

尺寸映射规则（gpt-image-2 支持三种尺寸）：

| 请求尺寸关系 | 映射到 | 场景 |
|-------------|--------|------|
| 宽 = 高 | `1024x1024` | 正方形 |
| 宽 > 高 | `1536x1024` | 横向/风景 |
| 高 > 宽 | `1024x1536` | 纵向/人像 |
| 未指定 | 使用配置的 `size` | 默认 |

### ComfyUIBackend（`comfyui.py`）

将 `MediaService.__call__()` 中现有的 ComfyKit 图片生成逻辑提取到此类。保持行为不变。

## 3. MediaService 改造

`pixelle_video/services/media.py`：

- `__init__` 中根据 `config.image.provider` 创建对应后端实例
- `__call__` 中，当 `media_type == "image"` 时路由到后端
- 当 `media_type == "video"` 时，仍然走 ComfyUI（不变）
- `list_workflows()` 在 OpenAI 后端下返回空列表或提示信息

```python
class MediaService(ComfyBaseService):
    def __init__(self, config, core=None):
        super().__init__(config, service_name="image", core=core)
        self._backend = self._create_backend()

    def _create_backend(self) -> ImageBackend:
        provider = self.config.get("provider", "comfyui")
        if provider == "openai":
            from pixelle_video.services.image_backends.openai import OpenAIImageBackend
            return OpenAIImageBackend(self.config.get("openai", {}))
        from pixelle_video.services.image_backends.comfyui import ComfyUIBackend
        return ComfyUIBackend(self, self.config)

    async def __call__(self, prompt, workflow=None, media_type="image",
                       width=None, height=None, **params) -> MediaResult:
        if media_type == "image" and self._backend:
            return await self._backend.generate(prompt, width, height, **params)
        # video 类型走 ComfyUI（现有逻辑不变）
        ...
```

## 4. REST API 改造

`api/routers/image.py`：

- `ImageGenerateRequest` 新增可选字段 `provider: Optional[str] = None`
- 调用 `MediaService` 时传入 provider（或使用配置默认值）
- `MediaService` 内部自动路由，API 层改动极小

`api/schemas/image.py`：

```python
class ImageGenerateRequest(BaseModel):
    prompt: str
    width: Optional[int] = None
    height: Optional[int] = None
    workflow: Optional[str] = None
    provider: Optional[str] = None  # 新增
```

## 5. Web UI 改造

`web/components/style_config.py`：

在"Media Generation Section"中新增：
1. **Provider 选择框**：`ComfyUI` / `OpenAI`，读取并更新 `comfyui.image.provider`
2. 当选 `OpenAI` 时，隐藏工作流下拉框，显示 OpenAI 配置（model、size 选择）
3. 当选 `ComfyUI` 时，显示现有的工作流下拉框
4. prompt prefix 输入框两种后端通用

## 6. 错误处理

| 场景 | 处理方式 |
|------|---------|
| API Key 未配置 | 初始化时检查，provider=openai 且 key 为空时抛出明确配置错误 |
| API 调用失败 | 捕获 `openai.APIError`，记录日志，向上抛出 |
| 内容审核拒绝 | 捕获 `openai.BadRequestError`，提示用户修改 prompt |
| 不支持的尺寸 | 自动映射到最接近的支持尺寸，不报错 |
| 网络超时 | 使用 openai SDK 默认重试机制 |

## 7. 不涉及的部分

- **图片分析**（`ImageAnalysisService`）：保持 ComfyUI，不做改动
- **视频生成**：保持 ComfyUI，OpenAI 后端仅处理图片
- **LLM 服务**：保持独立，与本次改动无关
- **TTS 服务**：不涉及

## 8. 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `pixelle_video/config/schema.py` | 修改 | 新增 `OpenAIImageConfig`，扩展 `ImageSubConfig` |
| `pixelle_video/services/image_backends/__init__.py` | 新增 | 模块导出 |
| `pixelle_video/services/image_backends/base.py` | 新增 | `ImageBackend` 抽象基类 |
| `pixelle_video/services/image_backends/openai.py` | 新增 | OpenAI 图片生成后端 |
| `pixelle_video/services/image_backends/comfyui.py` | 新增 | 从 MediaService 提取 ComfyUI 逻辑 |
| `pixelle_video/services/media.py` | 修改 | 引入后端策略路由 |
| `api/schemas/image.py` | 修改 | 新增 `provider` 字段 |
| `api/routers/image.py` | 修改 | 传递 provider 参数 |
| `web/components/style_config.py` | 修改 | 新增 Provider 选择 UI |
| `config.example.yaml` | 修改 | 新增 OpenAI 配置示例 |
