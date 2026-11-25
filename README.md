# hermes-image-studio

面向 **Hermes Agent** 的多后端生图插件与 Skill 仓库，统一管理双引擎：

- **NovelAI（默认主引擎）**：独立调用 NovelAI Diffusion V5 / V4.5 / V4 / V3，接管内置 `image_generate` 并提供完整参数工具 `novelai_generate` / `novelai_status`。
- **ComfyUI（按需独立工具，经 Tailscale 回连本机）**：调用 ComfyUI 导出的 API Workflow JSON，注入正/负面提示词与少量关键参数，提供 `comfyui_generate` / `comfyui_status`（亦实现了 `ComfyUIImageGenProvider` 便于按需切换）。

---

## 目录结构

```text
hermes-image-studio/
├── plugins/
│   └── image_gen/
│       ├── novelai/              # NovelAI 后端插件（对应 VPS ~/.hermes/plugins/image_gen/novelai/）
│       │   ├── plugin.yaml
│       │   ├── __init__.py       # 插件入口、ImageGenProvider 与工具注册
│       │   ├── client.py         # NovelAI HTTP 执行与账号状态查询
│       │   ├── payload.py        # 配置读取、模型判定与请求参数构建
│       │   ├── media.py          # 图片加载/预处理、ZIP 解包与 Vibe 缓存
│       │   ├── schemas.py        # novelai_generate / novelai_status 工具 Schema
│       │   └── constants.py      # 模型目录、画质词、UC 预设与默认参数
│       └── comfyui/              # ComfyUI API Workflow 插件（对应 VPS ~/.hermes/plugins/image_gen/comfyui/）
│           ├── plugin.yaml
│           ├── __init__.py       # ComfyUIImageGenProvider 与工具注册
│           ├── client.py         # /system_stats 探活、/prompt 提交、/history 轮询、/view 拉图
│           ├── workflow.py       # workflows/*.json 加载与节点参数注入（自动反查 + 显式映射）
│           ├── schemas.py        # comfyui_generate / comfyui_status 工具 Schema
│           ├── constants.py      # 超时、比例预设与 System Prompt 指引
│           └── README.md         # Tailscale 连通与自定义节点映射说明
├── skills/
│   ├── novelai-prompting/SKILL.md # 配套 NovelAI Prompt Skill
│   └── comfyui-workflow/SKILL.md  # 配套 ComfyUI Workflow Skill
├── workflows/
│   └── example-sdxl.json         # ComfyUI API 格式示例工作流（私有工作流可命名 *.local.json）
└── scripts/
    └── deploy-vps.example.ps1    # 无敏感信息部署模板（复制为 deploy-vps.ps1 本地使用，已加入 .gitignore）
```

---

## NovelAI 插件能力清单

- **接管内置 `image_generate`**：在 `~/.hermes/config.yaml` 设置 `image_gen.provider: novelai` 即可无缝用于 Telegram / CLI。
- **专用完整工具 `novelai_generate`（toolset: `novelai`）**：
  - 模型：`nai-diffusion-5-full`（默认）、`nai-diffusion-5-curated`、`nai-diffusion-4-5-full`、`nai-diffusion-4-5-curated`、`nai-diffusion-4-full`、`nai-diffusion-4-curated-preview`、`nai-diffusion-3`、`nai-diffusion-furry-3`
  - 负面提示词 `negative_prompt` + UC 预设 + 自动画质词 `quality_tags`
  - V4 / V4.5 / V5 多角色提示词与坐标定位 `characters`
  - 自定义宽高/比例、步数、CFG、采样器、调度器、固定 `seed`、`variety_boost`
  - 图生图 Img2Img、Precise Reference（V5 支持 `outfit` 与 `strength 0.0–5.0`）、Vibe Transfer（V4.5/V4/V3）
- **账号查询工具 `novelai_status`（toolset: `novelai`）**：查询订阅档位与剩余 Anlas。

---

## ComfyUI 插件能力清单

- **独立按需工具 `comfyui_generate`（toolset: `comfyui`）**：
  - 直接加载 ComfyUI 导出的 **API Workflow JSON**（`~/.hermes/comfyui/workflows/<name>.json`）
  - 支持注入 `prompt`（必填）及少量可选关键参数：`negative_prompt`、`workflow`、`aspect_ratio` / `width` / `height`、`steps`、`cfg`、`seed`（未传的参数保留 workflow 原值；未传 `seed` 时自动随机防缓存命中）
  - 自动沿采样器（`KSampler` / `SamplerCustomAdvanced` 等）上游连线定位正/负文本节点与 Latent 尺寸节点，亦支持 `<name>.meta.json` 或 `config.yaml` 显式 `node_id.field` 映射覆盖
  - 3 秒快速 `/system_stats` 探活，本机未开机时立即返回明确提示
- **状态探活工具 `comfyui_status`（toolset: `comfyui`）**：检测 Tailscale 远端 ComfyUI 是否在线、GPU 显存概况与可用 workflow 列表。

---

## Hermes 配置参考（VPS `~/.hermes/config.yaml`）

```yaml
plugins:
  enabled:
    - platforms/telegram
    - image_gen/novelai
    - image_gen/comfyui

image_gen:
  provider: novelai
  model: nai-diffusion-5-full
  novelai:
    model: nai-diffusion-5-full
    sampler: k_euler_ancestral
    noise_schedule: karras
    steps: 23
    scale: 7.0
    cfg_rescale: 0.0
    uc_preset: heavy
    quality_tags: true
    variety_boost: false
  comfyui:
    default_workflow: default
    timeout: 180

platform_toolsets:
  cli:
    - hermes-cli
    - novelai
    - comfyui
  telegram:
    - hermes-telegram
    - novelai
    - comfyui
```

密钥与私有地址存放在 VPS 的 `~/.hermes/.env`（权限 `600`，不要提交到仓库）：

```dotenv
NOVELAI_API_KEY=pst-...
COMFYUI_BASE_URL=http://<your-tailscale-ip>:8188
```

---

## 同步部署到 VPS

方式一：直接通过参数或环境变量运行模板脚本：

```powershell
.\scripts\deploy-vps.example.ps1 -HostAddress "ubuntu@your-server-ip" -KeyPath "C:\path\to\key.pem"
# 如需走本地 SOCKS5 代理（如 10808 端口），可额外传入 -SocksProxyPort 10808
```

方式二：复制 `scripts/deploy-vps.example.ps1` 为 `scripts/deploy-vps.ps1`（已被 `.gitignore` 忽略），填入你自己的服务器地址和密钥路径后直接运行：

```powershell
.\scripts\deploy-vps.ps1
```

如果只想同步文件而不重启 gateway：

```powershell
.\scripts\deploy-vps.ps1 -NoRestart
```
