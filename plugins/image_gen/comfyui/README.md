# ComfyUI Backend Plugin

通过 Tailscale 私网调用本机/远程 ComfyUI API Workflow 的 Hermes 插件，作为独立按需工具与 NovelAI 默认主引擎共存。

## 使用步骤

1. **打通 Tailscale**：本机 Windows 与 VPS 各安装登录同一 Tailscale 账号；本机启动 ComfyUI 时加 `--listen 0.0.0.0 --port 8188`（Windows 防火墙仅放行 Tailscale 网段）。
2. **在 VPS 配置地址**：在 `~/.hermes/.env` 写入：
   ```dotenv
   COMFYUI_BASE_URL=http://<本机Tailscale-IP>:8188
   ```
   （也可写在 `~/.hermes/config.yaml` 的 `image_gen.comfyui.base_url`）
3. **导出 API Workflow JSON**：在 ComfyUI 开启 Dev Mode → `Export (API)`，将 JSON 放到本仓库 `workflows/default.json`（或多套 `<name>.json`；不愿入库的私有工作流可命名为 `*.local.json`），运行部署脚本同步到 VPS `~/.hermes/comfyui/workflows/`。
4. **可选自定义节点映射**：标准 `KSampler` / `SamplerCustomAdvanced` + `CLIPTextEncode` + `EmptyLatentImage` 零配置自动识别；如使用第三方魔改节点，可在同目录放 `<name>.meta.json`：
   ```json
   {
     "positive": "6.text",
     "negative": "7.text",
     "seed": "3.seed",
     "steps": "3.steps",
     "cfg": "3.cfg",
     "width": "5.width",
     "height": "5.height"
   }
   ```
