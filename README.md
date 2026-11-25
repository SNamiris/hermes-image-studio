# hermes-image-studio

面向 **Hermes Agent** 的多后端生图插件与 Skill 仓库，统一管理：

- **NovelAI（已实现，完整版）**：独立调用 NovelAI Diffusion V4.5 / V4 / V3，支持接管内置 `image_generate` 与完整参数工具 `novelai_generate` / `novelai_status`。
- **ComfyUI（预留扩展）**：独立调用本地/远程 ComfyUI API 工作流（通过 Tailscale / SSH 反向隧道 / frp），并支持“本地 ComfyUI 优先 + NovelAI 自动兜底”的混合模式。

---

## 目录结构

```text
hermes-image-studio/
├── plugins/
│   └── image_gen/
│       ├── novelai/              # NovelAI 后端插件（对应 VPS ~/.hermes/plugins/image_gen/novelai/）
│       │   ├── plugin.yaml
│       │   └── __init__.py
│       └── comfyui/              # ComfyUI 后端插件（规划中）
│           └── README.md
├── skills/
│   └── novelai-prompting/        # 配套 Prompt Skill（对应 VPS ~/.hermes/skills/creative/novelai-prompting/）
│       └── SKILL.md
├── workflows/                    # 后续存放 ComfyUI API 格式工作流 JSON
└── scripts/
    └── deploy-vps.example.ps1    # 无敏感信息部署模板（复制为 deploy-vps.ps1 本地使用，已加入 .gitignore）
```

---

## NovelAI 插件能力清单

- **接管内置 `image_generate`**：在 `~/.hermes/config.yaml` 设置 `image_gen.provider: novelai` 即可无缝用于 Telegram / CLI。
- **专用完整工具 `novelai_generate`（toolset: `novelai`）**：
  - 模型：`nai-diffusion-4-5-full`（默认）、`nai-diffusion-4-5-curated`、`nai-diffusion-4-full`、`nai-diffusion-4-curated-preview`、`nai-diffusion-3`、`nai-diffusion-furry-3`
  - 负面提示词 `negative_prompt` + UC 预设（`heavy` / `light` / `furry_focus` / `human_focus` / `none`）+ 自动画质词 `quality_tags`
  - V4 / V4.5 多角色提示词与坐标定位 `characters`
  - 自定义宽高/比例（默认 `832x1216` / `1216x832` / `1024x1024`、`steps <= 28`，贴合 Opus 免费档）、`scale`、`cfg_rescale`、`sampler`、`noise_schedule`、`seed`、`variety_boost`
  - 图生图 Img2Img（`source_image`、`strength`、`noise`）
  - V4.5 精准参考 Precise / Character Reference（`character_references`，自动黑边填充至 `1024x1536` / `1536x1024` / `1472x1472`）
  - 风格迁移 Vibe Transfer（`vibe_references`，V4/V4.5 自动调用 `/ai/encode-vibe` 并做本地缓存避免重复扣 Anlas）
- **账号查询工具 `novelai_status`（toolset: `novelai`）**：查询订阅档位与剩余 Anlas。
- **System Prompt 指引**：自动注册 `novelai_image_gen`，指导 Agent 输出英文 Danbooru/自然语言提示词，并在调用 `novelai_generate` 后输出 `MEDIA:<path>` 以触发 Telegram 自动发图。

---

## Hermes 配置参考（VPS `~/.hermes/config.yaml`）

```yaml
plugins:
  enabled:
    - platforms/telegram
    - image_gen/novelai

image_gen:
  provider: novelai
  model: nai-diffusion-4-5-full
  novelai:
    model: nai-diffusion-4-5-full
    sampler: k_euler_ancestral
    noise_schedule: karras
    steps: 28
    scale: 5.0
    cfg_rescale: 0.0
    uc_preset: heavy
    quality_tags: true
    variety_boost: false

platform_toolsets:
  cli:
    - hermes-cli
    - novelai
  telegram:
    - hermes-telegram
    - novelai
```

密钥存放在 VPS 的 `~/.hermes/.env`（权限 `600`，不要提交到仓库）：

```dotenv
NOVELAI_API_KEY=pst-...
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
