# hermes-image-studio

面向 **Hermes Agent** 的多后端生图插件与 Skill 仓库，统一管理双引擎：

- **NovelAI（默认主引擎）**：独立调用 NovelAI Diffusion V5 / V4.5 / V4 / V3，接管内置 `image_generate` 并提供完整参数工具 `novelai_generate` / `novelai_status`。
- **ComfyUI（按需独立工具，经 Tailscale 回连本机）**：调用 ComfyUI 导出的 API Workflow JSON，注入正/负面提示词与少量关键参数，提供 `comfyui_generate` / `comfyui_status`（亦实现了 `ComfyUIImageGenProvider` 便于按需切换）。

---

## 安装和更新

```bash
hermes plugins install https://github.com/SNamiris/hermes-image-studio --enable
hermes plugins validate ~/.hermes/plugins/hermes-image-studio
hermes plugins update hermes-image-studio
```

如果之前通过脚本单独部署过两个后端，迁移时将 `plugins.enabled` 里的
`image_gen/novelai` 和 `image_gen/comfyui` 换成 `hermes-image-studio`，停用旧插件以避免重复注册。
原有的 `image_gen` 和 `platform_toolsets` 配置可以继续使用。重启 Hermes 或 Gateway 后，
可通过 `skill_view` 加载 `hermes-image-studio:prompt-craft`、
`hermes-image-studio:novelai-prompting` 和 `hermes-image-studio:comfyui-workflow`。

## 目录结构

```text
hermes-image-studio/
├── plugin.yaml                   # Hermes 插件清单
├── __init__.py                    # 统一注册两个后端和三个 Skill
├── plugins/image_gen/
│   ├── novelai/                   # NovelAI Provider 和工具
│   └── comfyui/                   # ComfyUI Provider 和工具
├── prompt_kit/                    # 本地提示词抽选、检索和初始化
├── assets/painting_seed/          # 示例词库与配方
├── skills/
│   ├── prompt-craft/              # 抽选、提示词改写和参考指南
│   ├── novelai-prompting/
│   └── comfyui-workflow/
└── workflows/example-sdxl.json     # ComfyUI API 格式示例工作流
```

## 提示词工坊

用户词库默认保存在 `~/painting/`，插件更新时由 Hermes 单独管理插件代码。
可用 `--data-dir <path>` 或 `HERMES_PAINTING_DIR` 指定数据目录，命令行参数优先。

```text
~/painting/
├── wildcards/   # .txt 或 YAML 词库，支持子目录
├── recipes/     # YAML 配方，slots 映射的顺序就是抽选顺序
├── artists/     # YAML 或 JSON 画师预设
└── guides/      # 私有 Markdown 指南，和内置指南一起检索
```

直接放在 `~/painting/` 下的 `.txt`、`.yaml` 和 `.yml` 也可作为词库。
同名文件优先使用 `wildcards/` 下的版本。TXT 每行一个候选项，支持 `3::silver hair` 抽样权重、
`{red|blue|2::golden}` 行内分支和 `__outfit/casual__` 词库引用。YAML 支持列表和嵌套分组，分组叶项一起抽选。

用安装了 PyYAML 的 Python 3.10+ 运行以下命令。从仓库运行时也可用 `python -m prompt_kit.cli`。

```bash
kit=~/.hermes/plugins/hermes-image-studio/skills/prompt-craft/scripts/prompt_kit.py
python3 "$kit" init
python3 "$kit" list --kind wildcards
python3 "$kit" roll --target nai --seed 42
python3 "$kit" roll --recipe scene_cinematic --count 2 --target comfyui
python3 "$kit" roll -f hair_eyes.txt -f 'outfit,accessories:2,scene' --target nai
python3 "$kit" roll -f outfit,scene --lock 'scene=snowy shrine' --exclude accessories
python3 "$kit" artists search --style painterly --engine nai
python3 "$kit" guides show tag-guide --format text
```

`init` 跳过已有文件。只有显式传入 `--overwrite` 才会替换已有的同名种子文件。
没有默认配方时，`roll` 从顶层词库各抽一项。`-f` 按输入顺序选择词库，`-f 'outfit/*'` 按名称展开该子目录里的匹配文件。
`accessories:2` 从同一池抽取两个不同条目。`--lock` 固定或添加槽位，`--exclude` 优先排除槽位。
输出默认使用 JSON，包含槽位、来源、提示词和抽选种子。`--format text` 可直接阅读提示词。

需要加入画师预设时可传 `--with-artist`、`--artist-style <style>` 或 `--artist-id <id>`。
配方和画师预设的示例位于 `assets/painting_seed/recipes/` 和 `assets/painting_seed/artists/README.yaml`。

## NovelAI 插件能力清单

- **接管内置 `image_generate`**：在 `~/.hermes/config.yaml` 设置 `image_gen.provider: novelai` 即可无缝用于 Telegram / CLI。
- **专用完整工具 `novelai_generate`（toolset: `novelai`）**：
  - 模型：`nai-diffusion-5-full`（默认）、`nai-diffusion-5-curated`、`nai-diffusion-4-5-full`、`nai-diffusion-4-5-curated`、`nai-diffusion-4-full`、`nai-diffusion-4-curated-preview`、`nai-diffusion-3`、`nai-diffusion-furry-3`
  - 负面提示词 `negative_prompt` + UC 预设 + 自动画质词 `quality_tags`
  - V4 / V4.5 / V5 多角色提示词与坐标定位 `characters`
  - 自定义宽高/比例、步数、CFG、采样器、调度器、固定 `seed`、批量出图 `count`（1–8，串行 `n_samples=1` 保 Opus 免费并防 429）、`variety_boost`
  - 图生图 Img2Img、Precise Reference（V5 支持 `outfit` 与 `strength 0.0–5.0`）、Vibe Transfer（V4.5/V4/V3）
- **账号查询工具 `novelai_status`（toolset: `novelai`）**：查询订阅档位与剩余 Anlas。

---

## ComfyUI 插件能力清单

- **独立按需工具 `comfyui_generate`（toolset: `comfyui`）**：
  - 直接加载 ComfyUI 导出的 **API Workflow JSON**（`~/.hermes/comfyui/workflows/<name>.json`）
  - 支持注入 `prompt`（必填）及少量可选关键参数：`negative_prompt`、`workflow`、`aspect_ratio` / `width` / `height`、`steps`、`cfg`、`seed`、`count`（1–8，串行执行避免爆显存，亦支持 workflow 内自带 `batch_size > 1` 全量拉回）
  - 自动沿采样器（`KSampler` / `SamplerCustomAdvanced` 等）上游连线定位正/负文本节点与 Latent 尺寸节点，亦支持 `<name>.meta.json` 或 `config.yaml` 显式 `node_id.field` 映射覆盖
  - 3 秒快速 `/system_stats` 探活，本机未开机时立即返回明确提示
- **状态探活工具 `comfyui_status`（toolset: `comfyui`）**：检测 Tailscale 远端 ComfyUI 是否在线、GPU 显存概况与可用 workflow 列表。

---

## Hermes 配置参考（VPS `~/.hermes/config.yaml`）

```yaml
plugins:
  enabled:
    - platforms/telegram
    - hermes-image-studio

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

## 旧版部署脚本

`scripts/deploy-vps.example.ps1` 适用于旧版分离式部署。新版插件使用 `hermes plugins install`
和 `hermes plugins update`。自定义 ComfyUI 工作流仍放在 `~/.hermes/comfyui/workflows/`。
