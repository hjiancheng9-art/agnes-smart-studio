# Agnes Smart Studio

基于 Agnes AI 的智能图片/视频生成工具。

## 安装

```bash
pip install -r requirements.txt
cp .env.example .env  # 填入 API Key
```

## 快速启动

### 方式一：启动器（推荐）

双击 `launch.bat`（Windows）或运行 `./launch.sh`（macOS/Linux），自动检测环境并进入模式选择菜单。

```bash
# Windows
launch.bat

# macOS / Linux
./launch.sh

# 也可以直接传参
launch.bat -q "一只猫"
./launch.sh -q "海边" -v
```

### 方式二：Python 启动器

```bash
python launcher.py       # 图形化菜单 + 环境检测
```

### 方式三：命令行直接使用

```bash
# 交互模式
python agnes_studio.py

# 快速模式
python agnes_studio.py -q "一只猫"             # 文生图
python agnes_studio.py -q "海边" -v            # 文生视频
python agnes_studio.py -q "城市" -p            # 一站式流水线（文本→图片→视频）

# 异步模式（避免IDE超时）
python agnes_studio.py -q "日落" -v --submit-only   # 仅提交，返回 video_id
python agnes_studio.py --video-id VIDEO_ID            # 查询任务状态（⚠ 必须用 video_id）
python agnes_studio.py --video-id VIDEO_ID --timeout 60  # 查询并限时等待

# 测试
python test_advanced.py              # 运行全部快速测试
python test_advanced.py i2v         # 图生视频（submit-only）
python test_advanced.py i2v-wait    # 图生视频（限时等待）
python test_advanced.py check ID    # 查询视频任务
```
