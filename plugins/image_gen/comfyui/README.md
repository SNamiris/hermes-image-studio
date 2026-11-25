# ComfyUI Backend (Planned)

此目录预留给后续的 **ComfyUI 生图后端插件**，目标设计：

1. **独立调用**：注册 `comfyui` 的 `ImageGenProvider` 及专用工具 `comfyui_generate`（支持选择 `workflows/` 下的 API 格式工作流 JSON、覆盖正反提示词、底模/LoRA/尺寸/seed/图生图输入）。
2. **网络回连本机**：支持连接本机 Windows ComfyUI（推荐 Tailscale 私网 `http://<tailscale-ip>:8188`，或 SSH 反向隧道 `http://127.0.0.1:8188`）。
3. **与 NovelAI 协同 / 自动兜底**：
   - 可独立指定调用 `comfyui_generate` 或 `novelai_generate`；
   - 可配置健康检查（`GET /system_stats`，1-2s 超时）：本机 ComfyUI 在线时优先走本地显卡，离线时自动回退到 `novelai`。
