# GLM-4.6V 图像/视频识别服务设计

## 概述

在"自定义素材"管线的图片/视频识别场景中，新增智谱 GLM-4.6V 作为第三方识别服务，与现有 ComfyUI（RunningHub/SelfHost）并行共存。用户可在 Web UI 中切换识别服务提供商。

- **接入方式**：直接调用智谱 API（`zai-sdk`），不依赖 ComfyUI 工作流
- **覆盖范围**：图片识别 + 视频识别
- **使用场景**：仅 Web UI 自定义素材管线

## 方案选型

**方案 B：独立服务 + Core 层路由**

保持现有 `ImageAnalysisService` / `VideoAnalysisService`（ComfyUI）不动，新建 `GLMAnalysisService`，在 `PixelleVideoCore` 层增加统一入口方法按 provider 分发。

理由：零侵入现有代码，新增代码完全独立。

---

## Section 1：配置结构

### `config/schema.py` 新增

新增顶层 `glm` 配置（与 `comfyui`、`llm` 平级）：

```python
class GLMConfig(BaseModel):
    """GLM 视觉模型配置"""
    api_key: str = Field(default="", description="智谱 API Key")
    base_url: str = Field(default="", description="API Base URL（可选，默认智谱官方）")
    model: str = Field(default="glm-4.6v", description="视觉模型名称")

# PixelleVideoConfig 新增字段
class PixelleVideoConfig(BaseModel):
    # ... 现有字段不变 ...
    glm: GLMConfig = Field(default_factory=GLMConfig, description="GLM 视觉模型配置")
```

### `config.example.yaml`

```yaml
# GLM 视觉模型配置（图片/视频识别）
glm:
  api_key: "your-api-key"
  base_url: ""
  model: "glm-4.6v"
```

### 配置管理

`config/manager.py` 新增 `get_glm_config()` 方法，返回 GLM 配置 dict。Core 层通过 `self.config.get("glm", {})` 获取。

---

## Section 2：GLMAnalysisService

### 文件：`pixelle_video/services/glm_analysis.py`

```python
from zai import ZhipuAiClient

class GLMAnalysisService:
    """智谱 GLM-4.6V 图像/视频识别服务"""

    def __init__(self, config: dict):
        api_key = config.get("api_key", "")
        if not api_key:
            raise ValueError("GLM API Key is required")
        base_url = config.get("base_url") or None
        self._client = ZhipuAiClient(api_key=api_key, base_url=base_url)
        self._model = config.get("model", "glm-4.6v")

    async def analyze_image(self, image_path: str, prompt: str = "请详细描述这张图片的内容") -> str:
        """图片识别 - base64 编码，流式调用"""
        base64_url = self._encode_image(image_path)
        return await self._analyze(base64_url, prompt)

    async def analyze_video(self, video_path: str, prompt: str = "请详细描述这个视频的内容") -> str:
        """视频识别 - base64 编码，流式调用"""
        base64_url = self._encode_video(video_path)
        return await self._analyze(base64_url, prompt)

    async def _analyze(self, media_url: str, prompt: str) -> str:
        """流式调用，拼接 content 返回完整描述"""
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
            if delta.content:
                content_parts.append(delta.content)
        if not content_parts:
            raise Exception("GLM returned empty response")
        return "".join(content_parts)

    def _encode_image(self, path: str) -> str:
        """编码图片为 data:image/xxx;base64,... 格式"""
        import base64
        from pathlib import Path
        suffix = Path(path).suffix.lower().lstrip(".")
        mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "gif": "gif"}.get(suffix, "jpeg")
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return f"data:image/{mime};base64,{b64}"

    def _encode_video(self, path: str) -> str:
        """编码视频为 data:video/xxx;base64,... 格式"""
        import base64
        from pathlib import Path
        suffix = Path(path).suffix.lower().lstrip(".")
        mime = {"mp4": "mp4", "mov": "quicktime", "avi": "x-msvideo", "webm": "webm"}.get(suffix, "mp4")
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return f"data:video/{mime};base64,{b64}"
```

关键设计决策：
- **流式调用**：`stream=True`，逐步接收 reasoning 和 content，最终只返回 content
- **reasoning 丢弃**：`thinking` 参数开启思考模式，但 reasoning_content 仅用于调试日志，不作为识别结果
- **base64 传递**：图片/视频通过 `data:image/...;base64,...` 格式传递，兼容 GLM-4.6V 的 `image_url` 字段
- **同步转异步**：`zai-sdk` 的 `create()` 是同步方法，用 `asyncio.to_thread()` 包一层避免阻塞事件循环

---

## Section 3：Core 层分发 + 管线改造

### Core 层（`pixelle_video/service.py`）

```python
class PixelleVideoCore:
    def initialize(self):
        # ... 现有代码不动 ...
        self.image_analysis = ImageAnalysisService(self.config, core=self)
        self.video_analysis = VideoAnalysisService(self.config, core=self)

        # 新增：GLM 分析服务（初始化失败不阻断启动）
        glm_config = self.config.get("glm", {})
        try:
            self.glm_analysis = GLMAnalysisService(glm_config)
        except ValueError as e:
            logger.warning(f"GLM analysis service not available: {e}")
            self.glm_analysis = None

    async def analyze_image(self, image_path: str, provider: str = "comfyui", source: str = "runninghub") -> str:
        """统一图片识别入口"""
        if provider == "glm":
            if self.glm_analysis is None:
                raise Exception("GLM analysis service not configured")
            return await self.glm_analysis.analyze_image(image_path)
        return await self.image_analysis(image_path, source=source)

    async def analyze_video(self, video_path: str, provider: str = "comfyui", source: str = "runninghub") -> str:
        """统一视频识别入口"""
        if provider == "glm":
            if self.glm_analysis is None:
                raise Exception("GLM analysis service not configured")
            return await self.glm_analysis.analyze_video(video_path)
        return await self.video_analysis(video_path, source=source)
```

### 管线层（`pixelle_video/pipelines/asset_based.py`）

```python
# 原来：
analysis_source = context.request.get("source", "runninghub")
description = await self.core.image_analysis(asset_path, source=analysis_source)

# 改为：
provider = context.request.get("provider", "comfyui")
source = context.request.get("source", "runninghub")
description = await self.core.analyze_image(asset_path, provider=provider, source=source)
```

视频分析同理。ComfyUI 路径完全不变（provider 默认 comfyui）。

---

## Section 4：Web UI 改造

### 素材管线 UI（`web/pipelines/asset_based.py`）

当前 Radio 按钮从二选一（RunningHub/SelfHost）改为分组选择：

1. 第一层 Radio：选识别服务提供商（ComfyUI / GLM-4.6V）
2. 第二层（仅 ComfyUI）：选来源（RunningHub / SelfHost）
3. GLM-4.6V 不需要第二层选择

```python
provider_options = {"comfyui": "ComfyUI", "glm": "GLM-4.6V"}
selected_provider = st.radio("识别服务", options=list(provider_options.keys()),
                            format_func=lambda k: provider_options[k], horizontal=True)

if selected_provider == "comfyui":
    source_options = {"runninghub": "RunningHub（云端）", "selfhost": "SelfHost（本地）"}
    selected_source = st.radio("ComfyUI 来源", ...)
else:
    selected_source = "runninghub"  # 占位，GLM 不使用
```

请求参数新增 `provider` 字段：
```python
request = {"source": selected_source, "provider": selected_provider, ...}
```

### 设置页面（`web/components/settings.py`）

新增 GLM 配置区域：API Key（password 输入）、Base URL、Model，放在 ComfyUI 分析配置附近。

### i18n 翻译 Key

- `asset_based.provider.comfyui` → `"ComfyUI"` / `"ComfyUI"`
- `asset_based.provider.glm` → `"GLM-4.6V"` / `"GLM-4.6V"`
- `settings.glm_api_key` → `"GLM API Key"` / `"GLM API Key"`
- `settings.glm_base_url` → `"GLM Base URL"` / `"GLM Base URL"`
- `settings.glm_model` → `"GLM Model"` / `"GLM Model"`

---

## Section 5：依赖和错误处理

### 依赖

`requirements.txt` 新增：
```
zai-sdk>=0.2.2
```

### 错误处理

| 场景 | 处理 |
|------|------|
| API Key 为空 | `GLMAnalysisService.__init__` 抛 `ValueError`，Core 捕获后 `glm_analysis=None`，不阻断启动 |
| API 调用失败 | 捕获异常，log error，向上抛出让管线处理（和 ComfyUI 失败行为一致） |
| 流式 chunk 中断 | 已收集的 content 拼接返回；content_parts 为空则抛异常 |
| 文件不存在 | 调用前校验，不存在直接抛 `FileNotFoundError` |
| base64 编码失败 | 捕获 `OSError`，log error 并抛出 |

### API Key 安全

和现有 RunningHub API Key 处理一致——Web UI 设置页用 `st.text_input(type="password")` 输入。

---

## 涉及文件清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `requirements.txt` | 修改 | 新增 `zai-sdk>=0.2.2` |
| `config/schema.py` | 修改 | 新增 `GLMAnalysisConfig` |
| `config/__init__.py` | 修改 | 导出新配置类 |
| `config/manager.py` | 修改 | 传递 provider 和 glm 配置 |
| `pixelle_video/services/glm_analysis.py` | 新增 | GLM 分析服务 |
| `pixelle_video/service.py` | 修改 | 注册 GLM 服务，新增统一入口 |
| `pixelle_video/pipelines/asset_based.py` | 修改 | 使用统一入口方法 |
| `web/pipelines/asset_based.py` | 修改 | UI 分组选择 provider |
| `web/components/settings.py` | 修改 | 新增 GLM 配置区域 |
| `web/i18n/locales/en_US.json` | 修改 | 新增翻译 key |
| `web/i18n/locales/zh_CN.json` | 修改 | 新增翻译 key |
| `config.example.yaml` | 修改 | 新增 GLM 配置示例 |
