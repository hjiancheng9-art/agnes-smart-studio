"""Agnes — Agnes AI 平台本地客户端 v1.0

多模态 AI API 工具：Chat / Vision / Image / Img2Img / Video

快速开始:
  from agnes.client import AgnesClient
  client = AgnesClient()
  print(client.chat_text("你好"))
  client.generate_image_and_save("一只猫")
"""

__version__ = "1.0.0"

from agnes.client import AgnesClient, AgnesConfig, AgnesError
from agnes.config import has_api_key, load_config, load_env_into_os, save_config, show_setup_dialog

__all__ = [
    "AgnesClient",
    "AgnesConfig",
    "AgnesError",
    "has_api_key",
    "load_config",
    "load_env_into_os",
    "save_config",
    "show_setup_dialog",
]
