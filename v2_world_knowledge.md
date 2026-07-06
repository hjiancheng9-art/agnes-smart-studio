下面给你一版 新烬龙V2 原生世界知识库 v1.0，按可拆包方式组织，适合后续分成 knowledge/packs/video-production.md、prompt-strategy.md、creative-bible.md、qa-checklists.md、delivery-management.md、multimodal-input.md。
编辑新烬龙V2 世界知识库 v1.0适用对象：24阶段多模态视频创作管线 / CRUX总控 / V2导演层 / Prompt层 / QA层 / 交付层0. 全局生产参数建议默认短片参数项目类型推荐总时长单镜头时长镜头数量画幅帧率输出单图故事海报1张不适用19:16 / 16:9不适用PNG/JPG15秒短视频12-18秒2-4秒4-8镜9:1624/25/30fpsMP430秒短片25-35秒2-5秒8-15镜9:16 / 16:924/30fpsMP460秒短片55-70秒3-6秒12-25镜16:9 / 9:1624/30fpsMP43分钟动画150-210秒3-8秒35-70镜16:924fpsMP4/MOV默认质量门每个阶段至少满足：有明确输入。有结构化输出。有制品路径或文本制品。有证据记录。不允许 placeholder 当真实结果。下游阶段能消费本阶段输出。与 creative-bible 不冲突。与 deliveryGoal 匹配。可人工审阅。可重跑、可回滚、可归档。1. 24阶段视频制作资料1-script 剧本阶段最佳实践先确定片长、受众、风格、情绪曲线。先写 logline，再写三幕结构。短片剧本建议控制在 300-1200 字。30秒以内短片只保留一个核心冲突。每个场景必须有：目标、阻碍、转折、情绪变化。对白要少，视觉行动要多。奇幻/科幻项目必须先锁定世界规则，避免后期补设定。输出应包含：标题、主题、三幕、场景、对白、视觉重点、声音重点。常见错误与修复错误修复设定很多但没有冲突用一句话重写核心冲突：“谁为了什么，必须克服什么。”角色没有动机给主角一个外在目标和一个内在缺口对白解释太多改成动作、环境、道具表达结尾突然解决提前埋伏关键能力或选择反派太扁平给反派一个合理痛点或价值观QA清单是否有明确 logline？是否有主角目标？是否有核心冲突？是否分为清晰三幕？是否有转折点？是否能拆成分镜？是否有可视化动作？是否符合目标时长？是否与世界观一致？是否有情绪高潮？技能/工具编剧结构：三幕、英雄之旅、起承转合。工具：ChatGPT、Kimi、DeepSeek、Notion、Final Draft、WriterDuet。V2制品：script.v1.json、script.md。2-storyboard 分镜阶段最佳实践每个镜头只表达一个动作或一个情绪变化。短视频单镜头建议 2-5 秒。每个镜头包含：景别、主体、动作、镜头运动、转场、台词/音效。分镜必须绑定角色、场景、道具。先做文字分镜，再做关键帧。镜头顺序要有视觉节奏：远景建立 → 中景行动 → 近景情绪 → 大景别高潮。常见错误与修复错误修复一个镜头塞太多动作拆成 2-3 个镜头全是中景增加远景、特写、主观镜头镜头之间跳跃增加转场或动作连接没有时长每镜头补 2-6 秒没有资产引用给每镜头绑定 characterId / sceneId / propIdQA清单镜头编号连续吗？每镜头有时长吗？每镜头有景别吗？每镜头有主体动作吗？是否绑定资产？是否有转场？是否覆盖剧本所有关键情节？是否符合总时长？是否有视觉节奏变化？是否可用于关键帧生成？技能/工具镜头语言、构图、节奏、剪辑逻辑。工具：Storyboarder、Photoshop、Figma、Milanote、ChatGPT。V2制品：storyboard.v1.json、storyboard.md。3-keyframes 关键帧阶段最佳实践每个关键剧情点至少一张关键帧。关键帧必须锁定：主体、场景、灯光、色调、构图、情绪。同一角色必须使用一致外貌描述。画面提示词避免过长，重点放在视觉锚点。每张图应有 shotId、prompt、negativePrompt、styleAnchor。关键帧分三类：建立镜头、动作镜头、情绪镜头。常见错误与修复错误修复角色长相漂移增加角色锁定描述和参考图风格漂移添加 styleAnchor、palette、negative style画面太空增加前景/中景/背景层次主题不突出明确主体位置和镜头焦点构图廉价使用 low angle / rule of thirds / depth layersQA清单是否覆盖关键镜头？是否绑定 storyboard shotId？是否使用角色/场景/道具引用？是否引用 styleAnchor？是否包含负面约束？是否有清晰主体？是否有空间层次？色板是否一致？画面是否符合镜头情绪？是否可用于视频生成？技能/工具图像提示词、构图、摄影、美术指导。工具：ChatGPT、Midjourney、DALL·E、Stable Diffusion、ComfyUI、Jimeng、Gemini。V2制品：keyframe-plan.v1.json、keyframe_images/。4-visual-dev 视觉开发阶段最佳实践先锁定风格关键词：类型、时代、材质、光线、色彩、参考。建立色板：主色 2-3 个，辅助色 2 个，强调色 1 个。输出视觉规则，而不是只输出图片。明确“禁止风格”：例如廉价霓虹、卡通化、过度雾化。视觉开发应服务后续角色、环境、道具、关键帧。常见错误与修复错误修复风格太泛用 5 个具体视觉锚点替代空泛词参考混乱只保留 1 主参考 + 2 辅参考色彩失控建立固定色板世界观和画风冲突用 creative-bible 统一后续阶段没用到把视觉规则写入 styleAnchorQA清单是否有 styleAnchor？是否有主色板？是否有材质规则？是否有灯光规则？是否有构图规则？是否有负面约束？是否适配目标平台？是否可用于角色/环境/道具？是否与故事情绪一致？是否有参考输入？技能/工具美术指导、色彩设计、世界观视觉化。工具：PureRef、Pinterest、Figma、Photoshop、ChatGPT、Gemini。V2制品：visual-dev.v1.json、style-anchor.v1.json。5-character 角色设计阶段最佳实践每个主角至少有：正面、侧面、背面、表情、动作姿态。描述结构：年龄、体型、脸部、发型、服装、材质、标志物、情绪。动画项目角色设计必须可重复生成。关键角色要有 silhouette，即剪影可识别。服装与世界观、职业、性格一致。给每个角色建立 characterId。常见错误与修复错误修复角色脸漂移增加 face lock 与 reference image服装复杂不可动画简化层级，保留核心符号主角不突出加独特标志物与世界观不符回查 era/location/material rules表情单一增加 emotion sheetQA清单是否有 characterId？是否有外貌锁定？是否有服装设定？是否有标志物？是否有性格/动机？是否有表情/pose？是否有参考图？是否与色板一致？是否可动画化？是否与其他角色区分明显？技能/工具角色设计、服装设计、表情设计。工具：Photoshop、Clip Studio、Blender、ComfyUI、Midjourney、Jimeng。V2制品：characters.v1.json、character_sheets/。6-environment 环境设计阶段最佳实践环境必须支持叙事，不只是背景。每个主要场景要有：空间布局、光源、材质、尺度、气氛。设定入口、出口、行动路线。奇幻/科幻环境要定义物理规则。每个场景要有 establishing shot。常见错误与修复错误修复背景漂亮但不可拍加路径、平台、前中后景尺度不清放入人物或地标作为比例参考场景重复给每个场景不同光线/颜色/功能与剧情无关给场景添加叙事功能空间混乱画 top-down layoutQA清单是否有 environmentId？是否有空间布局？是否有主要光源？是否有材质规则？是否有行动路线？是否支持对应剧情？是否有尺度参考？是否有前中后景？是否符合视觉风格？是否可用于分镜？技能/工具场景设计、建筑、环境叙事。工具：Blender、Unreal、Photoshop、PureRef、ChatGPT。V2制品：environments.v1.json、environment_concepts/。7-prop 道具设计阶段最佳实践道具必须有叙事功能。关键道具要有外观、材质、尺寸、使用方式、象征意义。道具需要绑定角色或剧情节点。奇幻道具要定义能量规则。输出正视图、侧视图、细节图。常见错误与修复错误修复道具只是装饰绑定剧情功能尺寸不清加手持/人物比例设计过复杂保留轮廓和核心符号前后不一致建 propId 和 reference sheet不能被动画使用加使用方式说明QA清单是否有 propId？是否有用途？是否绑定角色/场景？是否有材质？是否有尺寸？是否有细节图？是否有状态变化？是否与风格一致？是否影响剧情？是否可复用？技能/工具道具设计、产品设计、叙事符号。工具：Photoshop、Blender、ComfyUI、Jimeng。V2制品：props.v1.json、prop_sheets/。8-fx 特效设计阶段最佳实践特效要服务动作和情绪。每个特效定义：来源、颜色、形态、运动、生命周期。魔法/能量特效应有规则，不可随意变化。特效不要遮挡主体。用低强度版本、中强度版本、高强度版本分级。常见错误与修复错误修复光效过曝降低 bloom，增加核心形状特效喧宾夺主降低面积或透明度每次形态不同设定 fxStyleId不符合物理/魔法规则补规则说明与角色动作脱节绑定动作触发点QA清单是否有 fxId？是否有触发条件？是否有颜色/形态？是否有生命周期？是否有强度等级？是否不遮挡主体？是否与世界规则一致？是否与声音同步？是否支持动画？是否可复用？技能/工具VFX、粒子、合成。工具：After Effects、Nuke、Blender、Unreal Niagara、ComfyUI。V2制品：fx-plan.v1.json、fx_refs/。9-animation 动画阶段最佳实践单镜头只做一个主动作。视频生成提示词必须包含：主体、动作、镜头运动、环境变化、时长。角色动作要符合性格和物理规则。生成前检查关键帧是否合格。每条视频要绑定 shotId。多次生成要保留版本，不能覆盖。常见错误与修复错误修复动作太多拆镜头角色变形缩短时长，增强角色参考镜头乱动限制 camera movement风格漂移引用 keyframe + styleAnchor时长不匹配明确 duration: 3s/4s/5sQA清单是否绑定 shotId？是否基于已批准关键帧？是否有单一主动作？是否有明确镜头运动？是否符合时长？角色是否稳定？场景是否稳定？是否无明显变形？是否可剪辑？是否有生成证据？技能/工具动画、视频生成、运动设计。工具：Kling、Runway、Luma、Pika、Seedance、ComfyUI、After Effects。V2制品：animation-plan.v1.json、video_clips/。10-lighting 灯光阶段最佳实践确定主光、辅光、轮廓光、环境光。灯光要统一时间、情绪、空间方向。光线必须服务主体可读性。奇幻项目要定义魔法光源。灯光强度建议：主光 60-80%，辅光 20-40%，轮廓光 10-30%。常见错误与修复错误修复光源方向混乱建立 light map主体太暗增加轮廓光氛围过雾减少 volumetric density魔法光过曝降低 bloom每镜头不一致用 lighting bibleQA清单是否有主光方向？是否有环境光？是否有轮廓光？主体是否可读？是否符合情绪？是否与场景光源一致？是否与色板一致？是否避免过曝？是否支持后期调色？是否跨镜头一致？技能/工具摄影灯光、渲染、合成。工具：Unreal、Blender、DaVinci Resolve、After Effects。V2制品：lighting-plan.v1.json。11-cinematic 电影化阶段最佳实践每个镜头选择明确景别：远景、中景、近景、特写。镜头运动要有动机。景深服务注意力。情绪高潮使用更稳定或更宏大的镜头。避免无意义旋转、乱飞、过度推拉。常见错误与修复错误修复镜头运动炫技改成叙事驱动全片节奏单一远中近交替主体不突出增加景深/构图焦点镜头不连贯加运动方向规则情绪不匹配调整机位高度和速度QA清单是否每镜头有景别？是否每镜头有镜头运动？镜头运动是否有动机？是否有视觉节奏？是否有焦点设计？是否有转场逻辑？是否支持剪辑？是否符合情绪曲线？是否与动画可执行性匹配？是否避免过度复杂？技能/工具摄影、导演、剪辑。工具：ShotDeck、Celtx、Storyboarder、Premiere、DaVinci。V2制品：cinematic-plan.v1.json。12-voiceover 配音阶段最佳实践先确定语言、角色、语气、速度、情绪。中文旁白建议 3-4 字/秒。英文旁白建议 2-3 words/sec。每段配音绑定镜头或场景。台词避免过长，保留画面表达空间。情绪标注要明确：低声、颤抖、坚定、轻柔。常见错误与修复错误修复配音太长按镜头时长压缩语气不一致建 voice profile语言和剧本不一致锁定 projectLanguage信息重复画面删解释性旁白角色口吻相同为每角色定义声线QA清单是否匹配项目语言？是否绑定镜头？是否控制字数？是否有情绪标注？是否有角色声线？是否可录制？是否与画面不重复？是否有停顿标记？是否有音频文件或脚本？是否进入字幕阶段？技能/工具配音导演、声音表演。工具：ElevenLabs、Azure TTS、剪映、Audition、Descript。V2制品：voiceover-script.v1.json、voiceover_audio/。13-music 音乐阶段最佳实践先确定音乐功能：氛围、节奏、情绪、高潮。短片音乐应有 3 段：开场氛围、冲突增强、结尾释放。音乐不要盖过对白。指定 BPM：舒缓 60-80，中速 90-120，紧张 130-160。定义乐器和质感。常见错误与修复错误修复音乐太满降低编曲密度情绪不匹配按场景重设 mood循环痕迹明显加过渡段抢对白降低 -12dB 到 -18dB风格突兀和世界观乐器一致QA清单是否有音乐风格？是否有 BPM？是否有乐器设定？是否匹配情绪曲线？是否不压对白？是否有高潮点？是否可循环或剪辑？是否有授权来源？是否有音频文件？是否与结尾情绪一致？技能/工具作曲、配乐、混音。工具：Suno、Udio、Logic Pro、Ableton、Audition。V2制品：music-plan.v1.json、music_tracks/。14-sound 音效阶段最佳实践音效分层：环境声、动作声、魔法/科技声、转场声。每个音效绑定时间点或镜头。声音要有空间感：远近、左右、混响。魔法/能量音效应有 signature sound。保留静默，别全程塞满。常见错误与修复错误修复声音太多保留关键动作声不同步绑定 frame/timecode没有空间感加 pan/reverb音量突兀做淡入淡出和音乐冲突频段错开QA清单是否有环境声？是否有动作声？是否有特殊音效？是否绑定镜头/timecode？是否与画面同步？是否有空间定位？是否不压对白？是否有静默设计？是否音量均衡？是否可交付混音？技能/工具声音设计、拟音、混音。工具：Audition、Reaper、Pro Tools、剪映。V2制品：sound-design.v1.json、sfx/。15-edit 剪辑阶段最佳实践先按故事节奏粗剪，再做细剪。每个镜头只保留有信息增量的部分。动作剪辑要接运动方向。情绪剪辑要保留反应镜头。音频节奏可辅助画面剪辑。常见错误与修复错误修复节奏拖缩短无信息镜头跳切突兀增加反应镜头或转场声画面顺序混乱回到 storyboard高潮不强前面降低节奏，高潮加对比音画脱节用音效点对齐剪点QA清单是否按剧本完成？是否总时长达标？是否有节奏变化？是否有情绪反应镜头？镜头顺序是否清晰？转场是否自然？音画是否同步？是否无黑帧/空帧？是否保留高潮？是否可进入调色？技能/工具剪辑、节奏、叙事。工具：Premiere、DaVinci、Final Cut、剪映。V2制品：edit-decision-list.v1.json、rough_cut.mp4。16-color 调色阶段最佳实践先做色彩校正，再做风格调色。保持肤色/主体可读性。按场景统一色温。输出 LUT 或调色参数。控制高光不过曝、暗部不死黑。常见错误与修复错误修复色彩过饱和降 saturation 10-20%暗部丢失提升 shadow 或加 fill镜头色彩不连贯shot matching风格太重降 LUT opacity主体不突出局部调整亮度/对比QA清单是否完成基础校正？是否匹配 styleAnchor？是否统一色温？是否高光不过曝？是否暗部有细节？是否主体可读？是否跨镜头一致？是否有 LUT/参数记录？是否适配交付平台？是否不过度风格化？技能/工具调色、色彩管理。工具：DaVinci Resolve、Premiere、After Effects。V2制品：color-plan.v1.json、graded_cut.mp4、LUT.cube。17-vfx 视觉特效阶段最佳实践VFX 必须补充画面，不破坏叙事。每个 VFX 元素绑定镜头和层级。注意遮罩、跟踪、合成边缘。粒子/光效要匹配镜头运动。输出合成前后对比。常见错误与修复错误修复合成边缘明显羽化和色彩匹配特效跟踪漂移重新 motion tracking光影不匹配加接触光和阴影粒子太假增加随机性和深度压缩后糊提高码率或渲染分辨率QA清单是否绑定镜头？是否有 VFX 列表？是否合成自然？是否匹配光影？是否跟踪稳定？是否不遮挡主体？是否无边缘瑕疵？是否有前后对比？是否渲染无错误？是否与声音同步？技能/工具合成、跟踪、粒子。工具：After Effects、Nuke、Blender、Fusion。V2制品：vfx-plan.v1.json、vfx_shots/。18-title 标题阶段最佳实践标题要匹配类型和受众。标题画面不宜过长，短片 2-4 秒。字体必须可读。标题动效服务情绪。标题和封面应保持视觉一致。常见错误与修复错误修复字太小移动端最小高度建议画面 5%字体不符选符合世界观字体动效过花简化为淡入/位移/光扫标题太长缩短到 2-8 字与画面冲突加遮罩或暗角QA清单标题是否准确？字体是否可读？是否符合风格？是否有安全边距？是否适配移动端？动效是否自然？是否无错别字？是否有片尾信息？是否与封面一致？是否可导出透明版？技能/工具平面设计、动效设计。工具：After Effects、Photoshop、Figma、剪映。V2制品：title-design.v1.json、title_cards/。19-subtitle 字幕阶段最佳实践中文字幕每行建议 12-18 字。单条字幕显示 1.2-4 秒。字幕不遮挡主体。对白字幕和旁白字幕样式区分。输出 SRT/VTT/ASS。常见错误与修复错误修复字幕太快延长或拆分遮挡主体上移/下移断句差按语义断句语言不一致锁定 projectLanguage缺字幕文件导出 SRT + Burn-in 版本QA清单是否完整覆盖对白？是否时间轴准确？是否无错别字？是否断句自然？是否字体可读？是否安全边距正确？是否不遮挡主体？是否导出 SRT/VTT？是否有烧录版？是否多语言需求满足？技能/工具字幕编辑、语言校对。工具：Subtitle Edit、剪映、Premiere、Aegisub。V2制品：subtitles.srt、subtitles.ass。20-packaging 打包阶段最佳实践打包包含视频、字幕、缩略图、项目说明、证据清单。命名规范：projectName_version_date.输出交付清单 manifest。检查路径、文件大小、hash。分原始工程包和客户交付包。常见错误与修复错误修复漏文件用 manifest 自动检查文件名混乱统一命名字幕丢失强制 delivery gate版本覆盖增加 version tag无证据生成 evidence ledgerQA清单是否有最终视频？是否有字幕？是否有封面？是否有交付说明？是否有 manifest？是否有 hash？是否有版本号？是否文件可打开？是否符合平台规格？是否包含证据链？技能/工具文件管理、打包、交付。工具：Node fs、zip、剪映、Premiere。V2制品：delivery-package.zip、manifest.json。21-review 审阅阶段最佳实践审阅分三类：创意审阅、技术审阅、交付审阅。每条问题标注 severity。输出 pass / needs_changes / fail。给出最小返工方案。审阅必须基于 evidence，不可凭空判断。常见错误与修复错误修复只说“不好看”转为具体问题没有优先级标 blocker/error/warn没有修复建议给最小返工路径忽略证据绑定 artifactId审阅标准不匹配按 deliveryGoal 选择 checklistQA清单是否检查叙事？是否检查画面？是否检查音频？是否检查字幕？是否检查证据？是否检查交付规格？是否有 severity？是否有修复建议？是否有 pass/fail？是否可进入交付？技能/工具审片、QC、客户沟通。工具：Gemini、ChatGPT、Kimi、DaVinci、VLC。V2制品：review-report.v1.json。22-delivery 交付阶段最佳实践输出最终视频和可编辑包。明确平台规格：抖音/YouTube/B站/客户内部。视频编码建议：H.264 MP4，1080p，10-20Mbps；4K，35-60Mbps。音频建议：AAC，48kHz，-14 LUFS 附近。附交付说明。常见错误与修复错误修复格式不符合平台按平台预设重新导出无字幕阻断交付视频太大调整码率音量过低loudness normalize文件无法播放重新编码 H.264QA清单是否有最终 MP4？是否可播放？是否分辨率正确？是否帧率正确？是否音频正常？是否有字幕版本？是否有无字幕版本？是否码率合理？是否命名规范？是否客户可直接使用？技能/工具编码、平台规范、交付。工具：FFmpeg、Media Encoder、DaVinci、Premiere。V2制品：final_delivery/。23-archive 归档阶段最佳实践所有输入、产物、prompt、证据、QA报告入档。归档不可只存最终视频。使用 checksum 防止文件损坏。记录版本和生成来源。归档后能复现项目。常见错误与修复错误修复只归档最终视频增加完整 return package无 prompt 快照补 promptSnapshot无输入引用记录 inputIds无证据生成 evidence ledger文件散乱按 stageId/group 归档QA清单输入是否归档？输出是否归档？prompt 是否归档？evidence 是否归档？QA report 是否归档？manifest 是否生成？hash 是否存在？版本是否记录？是否可复现？是否可迁移？技能/工具数据归档、文件系统、元数据。工具：Node fs、SQLite、JSONL、zip。V2制品：archive_manifest.json、evidence_ledger.json。24-retro 回顾阶段最佳实践总结成功点、失败点、重跑次数、客户反馈。抽取可复用模板。生成 knowledge candidate。更新 prompt strategy proposal。统计阶段耗时和质量分。常见错误与修复错误修复只写感想转成可执行规则没有数据引用 metrics不沉淀经验生成 template/knowledge candidate不区分问题严重度分类 blocker/error/warn不连接下一项目提取 reusable profileQA清单是否总结项目目标？是否记录阶段耗时？是否记录失败点？是否记录重跑次数？是否记录客户反馈？是否提取模板？是否生成知识候选？是否生成规则候选？是否生成 prompt 改进建议？是否归档 retro？技能/工具复盘、知识管理、产品优化。工具：ChatGPT、Kimi、Notion、JSONL。V2制品：retro-report.v1.json、knowledge_candidates.jsonl。2. 提示词工程资料2.1 剧本创作模板：三幕结构你是专业剧本创作专家。请根据以下设定创作一个[时长]的[类型]短片剧本。

【项目目标】
- 片长: [30秒/60秒/3分钟]
- 类型: [奇幻/科幻/广告/治愈/冒险]
- 受众: [儿童/年轻人/品牌客户/泛娱乐]
- 情绪曲线: [神秘→危机→觉醒→胜利]

【世界观】
时代: [时代]
地点: [地点]
核心规则: [物理/魔法/科技规则]
核心冲突: [冲突]

【角色】
主角: [姓名/年龄/身份/目标/缺点/成长]
导师: [姓名/功能]
反派: [姓名/动机]

【输出要求】
请输出:
1. 剧本标题
2. Logline，一句话故事
3. 三幕结构
4. 每幕 2-4 个场景
5. 每场景包含: 场景描述、角色对白、视觉重点、声音重点、情绪基调
6. 最后输出角色列表和关键设定

【质量要求】
- 每场景必须推动剧情
- 对白简洁
- 动作可视化
- 结尾必须回应主题2.2 剧本创作模板：英雄之旅请使用英雄之旅结构创作短片剧本。

必须包含:
1. 平凡世界
2. 冒险召唤
3. 拒绝召唤
4. 导师出现
5. 跨越门槛
6. 考验与盟友
7. 最深洞穴
8. 核心试炼
9. 奖赏
10. 回归
11. 新生
12. 带回礼物

限制:
- 总场景数: [6-10]
- 总时长: [60-180秒]
- 主角成长弧: [从A到B]
- 每个节点必须有视觉动作，不只靠对白解释。2.3 剧本创作模板：非线性结构请创作一个非线性短片剧本。

结构:
- 开场先展示结果或危机高潮
- 中段通过闪回揭示原因
- 结尾回到开场并反转意义

输出:
1. 时间线A: 真实发生顺序
2. 时间线B: 观众观看顺序
3. 每个场景标注 current / flashback / vision
4. 每次闪回必须有视觉触发物
5. 结尾必须让开场镜头获得新含义2.4 分镜提示词模板你是专业分镜导演。基于以下剧本，生成分镜表。

【输入】
剧本: [script]
目标时长: [秒]
画幅: [9:16/16:9]
风格: [电影感/动画/写实/奇幻]
镜头数量: [数量]

【输出字段】
- Shot编号
- 场景名
- 景别: [远景/全景/中景/近景/特写/俯拍/仰拍]
- 画面描述
- 主体动作
- 摄影机运动: [固定/推近/拉远/横移/环绕/跟拍/俯冲]
- 时长
- 台词
- 音效
- BGM
- 转场
- assetRefs: characterId/sceneId/propId

【规则】
- 每镜头只表达一个主动作
- 单镜头时长 2-6 秒
- 镜头之间必须有情绪或动作连接
- 总时长误差不得超过 10%2.5 关键帧提示词模板生成关键帧图像提示词。

【Shot信息】
shotId: [编号]
剧情功能: [建立/动作/情绪/高潮]
景别: [远景/中景/近景/特写]
主体: [角色/物体]
动作: [动作]
场景: [环境]
情绪: [情绪]

【视觉分层】
主体层: [人物外貌、姿态、表情、服装]
环境层: [地点、空间、背景元素]
灯光层: [主光、环境光、轮廓光、体积光]
色调层: [主色、辅助色、对比色]
材质层: [皮肤、布料、金属、晶体、雾、水]
构图层: [三分法/中心构图/低角度/纵深]
镜头层: [焦距、景深、视角]
细节层: [符号、纹理、粒子、道具]
渲染层: [cinematic, high detail, volumetric light, global illumination]

【负面约束】
避免: [风格漂移、廉价感、畸形手、过曝、低清晰度、错误服装]

输出:
1. 中文画面描述
2. 英文生成提示词
3. Negative prompt
4. 风格锚点2.6 视觉开发模板你是视觉开发美术指导。请为项目建立视觉风格锚点。

输出:
1. 风格关键词: 8-12个
2. 主色板:
   - 主色1: #[HEX]
   - 主色2: #[HEX]
   - 辅助色1: #[HEX]
   - 辅助色2: #[HEX]
   - 强调色: #[HEX]
3. 材质规则:
   - 建筑:
   - 服装:
   - 道具:
   - 能量/魔法:
4. 光影规则:
   - 主光方向:
   - 对比度:
   - 体积光:
   - bloom强度:
5. 构图规则:
   - 角色比例:
   - 空间层次:
   - 镜头高度:
6. 禁止项:
   - 不要:
7. 可用于关键帧的styleAnchor文本2.7 角色设计模板请生成角色设计说明和图像提示词。

角色:
- 姓名:
- 年龄:
- 身份:
- 性格:
- 动机:
- 成长弧:

视觉:
- 体型:
- 脸部:
- 发型:
- 眼睛:
- 服装:
- 材质:
- 标志物:
- 色彩:
- 武器/道具:
- 表情:
- pose:

输出:
1. 角色设计说明
2. Turnaround提示词: front view, side view, back view
3. 表情表提示词: neutral, fear, anger, joy, determination
4. 动作pose提示词
5. 负面约束2.8 电影化提示词模板请为以下分镜生成电影化执行方案。

输入:
- shotId:
- 画面:
- 情绪:
- 动作:
- 时长:

输出:
1. 景别
2. 镜头运动
3. 焦距建议:
   - 广角: 18-28mm
   - 标准: 35-50mm
   - 人像: 70-100mm
4. 景深:
   - deep focus / shallow depth of field
5. 灯光:
   - key light:
   - fill light:
   - rim light:
6. 剪辑建议
7. 音效提示
8. 适合视频生成平台的短prompt2.9 配音提示词模板请生成配音脚本。

输入:
- 剧本:
- 角色:
- 项目语言:
- 目标时长:
- 情绪曲线:

输出:
每条配音包含:
- voiceId
- characterId
- text
- emotion: [calm/fear/hope/anger/sorrow/determination]
- pace: [slow/normal/fast]
- volume: [soft/normal/loud]
- pause:
- targetDurationSec
- linkedShotIds

规则:
- 中文 3-4字/秒
- 英文 2-3 words/sec
- 每句不超过 8 秒
- 情绪变化必须跟镜头一致3. Creative Bible 参考3.1 世界观构建模板{
  "world": {
    "name": "",
    "genre": "",
    "era": "",
    "location": "",
    "atmosphere": "",
    "history": "",
    "physicalRules": [],
    "magicOrTechSystem": {
      "source": "",
      "cost": "",
      "limits": "",
      "visualForm": "",
      "forbiddenUses": []
    },
    "socialStructure": {
      "groups": [],
      "powerHierarchy": "",
      "conflicts": []
    },
    "visualTone": {
      "palette": [],
      "materials": [],
      "lighting": "",
      "architecture": "",
      "negativeStyle": []
    },
    "storyRules": []
  }
}3.2 角色设定模板{
  "characterId": "",
  "name": "",
  "age": "",
  "role": "",
  "appearance": {
    "body": "",
    "face": "",
    "hair": "",
    "eyes": "",
    "clothing": "",
    "signatureMark": "",
    "colors": []
  },
  "personality": [],
  "motivation": "",
  "fear": "",
  "secret": "",
  "relationshipMap": [],
  "arc": {
    "start": "",
    "turningPoint": "",
    "end": ""
  },
  "voice": {
    "tone": "",
    "pace": "",
    "emotionRange": []
  },
  "referenceInputs": []
}3.3 视觉风格参考说明注意：以下不是要求复刻具体版权风格，而是提取公开可描述的视觉特征，用于建立原创风格锚点。宫崎骏式自然奇幻特征手绘感自然环境。风、云、水、草木有生命感。角色动作朴素真实。机械或魔法不冰冷，带手工感。色彩温暖、空气通透。主题常围绕成长、自然、战争创伤。可转写为原创锚点：handcrafted natural fantasy, living wind and clouds, warm painterly atmosphere, gentle character animation, organic magical realism, detailed natural environments赛博朋克特征霓虹、高密度城市、雨夜、反光路面。巨型企业、信息过载、身体改造。高科技与低生活并存。色彩常用青、紫、品红、酸绿。情绪：孤独、压迫、反叛。原创锚点：rain-soaked vertical megacity, neon reflections, holographic signage, social decay, high-tech low-life, cyan-magenta contrast暗黑奇幻特征古老废墟、腐化森林、黑色魔法。低饱和色、强明暗对比。角色常背负诅咒或命运。特效偏烟、灰、血红、暗金。情绪：宿命、恐惧、庄严。原创锚点：ancient cursed ruins, low-saturation gothic fantasy, ash-filled atmosphere, crimson ritual light, solemn darkness皮克斯式动画特征角色轮廓清晰，表情丰富。材质柔和，光照友好。色彩明快，情绪可读性强。道具和环境有生活细节。镜头语言服务情绪。原创锚点：expressive stylized 3D animation, readable silhouettes, warm global illumination, appealing character design, emotionally clear stagingEVA式心理机甲特征巨大尺度对比。宗教符号、几何构图、压迫构图。孤独、创伤、身份问题。冷色调和红色警示色。机械与生物边界模糊。原创锚点：monumental biomechanical scale, symbolic geometric framing, psychological tension, cold industrial palette with red alerts新海诚式光影青春特征强烈天空、云、雨、水面反射。高饱和蓝色与暖色夕阳。城市与自然交织。情绪细腻、距离感、命运感。光斑、镜头眩光、空气透明。原创锚点：luminous skies, emotional urban fantasy, transparent air, rain reflections, golden sunset bloom, delicate longing3.4 常见世界观设定案例案例1：浮空岛魔法文明{
  "name": "翠翎",
  "era": "远古魔法纪元",
  "coreEnergy": "风心",
  "rules": [
    "岛屿由风心托举",
    "风语者能与风心共鸣",
    "风心能量必须在天空与地底之间平衡"
  ],
  "conflict": "天空享有光明，地底承受暗影",
  "visual": "青金色风流、浮空瀑布、羽叶树、白石祠堂"
}案例2：赛博雨夜垂直城市{
  "name": "霓渊城",
  "era": "近未来",
  "coreEnergy": "活体光轮",
  "rules": [
    "记忆可被存储为琥珀核心",
    "城市垂直分层决定阶级",
    "黑市能交易身份和梦境"
  ],
  "conflict": "个人记忆 vs 企业控制",
  "visual": "雨夜、霓虹、湿金属、青绿色雾光"
}案例3：暗黑森林王国{
  "name": "灰冠林",
  "era": "王国衰亡期",
  "coreEnergy": "腐化月泉",
  "rules": [
    "月光能治愈也能腐化",
    "王族血脉与森林根系相连",
    "说谎会在皮肤长出黑枝"
  ],
  "conflict": "王权延续 vs 自然复仇",
  "visual": "黑枝、银月、腐化花、破败王冠"
}案例4：海底蒸汽文明{
  "name": "潮炉国",
  "era": "蒸汽幻想时代",
  "coreEnergy": "海底热泉炉",
  "rules": [
    "城市由气泡穹顶保护",
    "机械鱼群负责运输",
    "热泉炉衰弱会使海压碾碎城市"
  ],
  "conflict": "工业扩张 vs 海洋神灵",
  "visual": "铜管、蓝绿海光、机械鱼、巨大玻璃穹顶"
}案例5：星际圣殿文明{
  "name": "白曜圣环",
  "era": "遥远星际纪元",
  "coreEnergy": "恒星圣核",
  "rules": [
    "圣殿环绕濒死恒星",
    "记忆以光粒形式存储",
    "祭司能读取恒星梦境"
  ],
  "conflict": "文明永生 vs 个体自由",
  "visual": "白金建筑、恒星光流、透明长廊、宇宙虚空"
}4. 质量管理资料4.1 通用视频质量检查 15项故事是否清晰。主角目标是否明确。冲突是否可理解。情绪曲线是否完整。镜头顺序是否连贯。视觉风格是否一致。角色是否稳定。场景是否稳定。音频是否同步。字幕是否准确。剪辑节奏是否合适。色彩是否统一。是否有明显生成瑕疵。是否符合交付规格。是否有完整证据链。4.2 常见质量问题和修复问题可能原因修复风格漂移prompt未锁定styleAnchor添加固定风格锚点角色变脸缺角色参考添加 reference image 和外貌锁动作混乱单镜头动作过多拆镜头节奏拖沓无信息镜头太多剪短 10-30%画面廉价灯光/材质泛化增加材质、光源、构图字幕不准未对齐音频手动校正 timecode音乐抢对白混音不平衡降音乐 -12dB 到 -18dB输出不能播放编码不兼容H.264 + AAC 重新导出证据缺失未记录来源补 artifact evidence客户不满意目标不清回到 project brief4.3 电影/动画评审标准叙事是否一句话能讲清？是否有角色目标？是否有冲突？是否有转折？是否有结尾回应？视觉是否有统一风格？主体是否清楚？构图是否有层次？色彩是否服务情绪？是否有世界观辨识度？音频对白是否清楚？音乐是否合适？音效是否同步？混音是否平衡？是否有空间感？节奏开场是否快速建立？中段是否有推进？高潮是否明确？结尾是否留有余韵？镜头时长是否合理？完整性视频、字幕、封面、manifest、证据是否齐全。是否符合平台规格。是否可交付给客户。4.4 客户反馈常见问题和应对客户反馈应对策略“不够高级”提供视觉锚点对比，升级灯光/材质/构图“不像我要的风格”回到 reference，重新定义 styleAnchor“节奏太慢”提供快剪版本，减少无信息镜头“角色不一致”锁定角色参考，重跑受影响镜头“画面太空”增加前景/背景/动线/装饰元素“看不懂故事”补旁白或重排镜头“字幕不舒服”调整字号、位置、断句“音乐不对”提供 2-3 个 mood 版本“想要更震撼”强化高潮镜头、音效、低角度和大景别“再改一点”明确修改范围，避免全片重做5. 项目管理/交付资料5.1 时间线模板30秒短片快速版：1-2天阶段时间Brief/脚本1-2小时分镜1-2小时关键帧2-4小时视频生成4-8小时音频/字幕1-2小时剪辑/调色2-4小时审阅/交付1-2小时3分钟动画短片：7-14天阶段时间剧本0.5-1天分镜1-2天视觉开发1天角色/环境/道具1-3天关键帧1-2天动画生成2-5天音频1天剪辑/VFX/调色1-2天审阅/交付0.5-1天5.2 交付物清单阶段交付物scriptscript.md / script.v1.jsonstoryboardstoryboard.md / storyboard.v1.jsonkeyframeskeyframe-plan.json / imagesvisual-devstyle-anchor.json / moodboardcharactercharacter sheetsenvironmentenvironment conceptspropprop sheetsfxfx-plan.jsonanimationvideo clipslightinglighting-plan.jsoncinematiccinematic-plan.jsonvoiceovervoiceover script/audiomusicmusic trackssoundsfx fileseditrough cut / EDLcolorgraded cut / LUTvfxvfx shotstitletitle cardssubtitleSRT/ASSpackagingmanifest/zipreviewreview reportdeliveryfinal mp4archiveevidence ledgerretroretro report5.3 版本管理策略命名projectName_stage_version_date.ext
cuiling_keyframes_v003_20260707.png
cuiling_final_v012_20260707.mp4版本规则v001 初版。v002 小改。v010 客户审阅版。final 只用于最终确认，不可提前使用。每次客户反馈生成新版本。不覆盖旧版本。状态draft
internal_review
client_review
approved
rejected
superseded
final
archived5.4 客户沟通模板需求确认您好，为确保视频方向准确，我需要确认以下信息：

1. 视频用途：
2. 目标时长：
3. 目标平台：
4. 画幅比例：
5. 风格参考：
6. 必须出现的角色/产品/信息：
7. 禁止出现的内容：
8. 交付截止时间：
9. 是否需要字幕/配音/音乐：
10. 最终交付格式：

确认后我会先提供剧本和分镜方向。阶段交付本阶段已完成：[阶段名]

交付内容：
- [文件1]
- [文件2]

请重点确认：
1. 故事方向是否正确
2. 视觉风格是否符合预期
3. 角色/场景是否需要调整

如需修改，请尽量按镜头编号反馈。修改反馈整理已收到修改意见，我将按以下优先级处理：

P0 必须修改：
- 

P1 建议修改：
- 

P2 可选优化：
- 

预计影响阶段：
- 

预计新版本交付：
- 最终交付最终版本已交付。

交付包包含：
- 最终视频 MP4
- 字幕文件
- 封面图
- 项目说明
- 版本记录

请下载后确认文件可正常播放。如后续需要二次剪辑或适配其他平台，可基于本版本继续扩展。6. 多模态输入处理6.1 参考视频处理流程导入视频。读取元数据：时长、分辨率、帧率、音频轨。自动抽帧：每 2-5 秒一帧，或按镜头变化抽帧。镜头切分：检测画面变化、运动变化、场景变化。生成镜头摘要。提取风格：色彩、构图、光线、运动。提取声音：对白、音乐、音效。输出 video-analysis.v1.json。写入 creative-bible 候选。绑定后续 storyboard / keyframes。视频标注字段{
  "videoId": "",
  "durationSec": 0,
  "fps": 24,
  "resolution": "1920x1080",
  "shots": [
    {
      "shotId": "",
      "start": 0,
      "end": 3.5,
      "sceneDescription": "",
      "cameraMovement": "",
      "mainAction": "",
      "mood": "",
      "dominantColors": [],
      "audioEvents": []
    }
  ]
}6.2 参考图片处理流程导入图片。读取尺寸、格式、hash。生成缩略图。提取主色板。分析构图：主体位置、视角、景别。分析光线：光源方向、对比度、色温。分析材质：金属、布料、皮肤、玻璃、水等。分析风格标签。输出 image-analysis.v1.json。可写入 styleAnchor 或 character reference。色板提取建议主色：占比最高 2-3 个颜色。辅助色：中等占比 2 个。强调色：高饱和小面积 1 个。输出 HEX。示例：{
  "palette": {
    "primary": ["#0B1F3A", "#2E7FA3"],
    "secondary": ["#D8C48A", "#7A4EB3"],
    "accent": ["#F2E7B8"]
  }
}6.3 音频处理流程导入音频。读取时长、采样率、声道。检测人声/音乐/环境声。如有人声，生成转写。分析情绪：平静、紧张、悲伤、激昂。分析节奏：BPM 或语速。生成时间码。输出 audio-analysis.v1.json。可用于 voiceover / subtitle / sound。音频标注字段{
  "audioId": "",
  "durationSec": 0,
  "sampleRate": 48000,
  "channels": 2,
  "type": "voiceover/music/sfx",
  "transcript": "",
  "segments": [
    {
      "start": 0,
      "end": 2.5,
      "text": "",
      "emotion": "",
      "loudness": ""
    }
  ]
}6.4 文档输入处理流程导入文档。检测语言和编码。提取标题、摘要、人物、地点、设定。识别客户需求和限制。生成 project brief。生成 creative-bible 候选。输出 document-analysis.v1.json。文档标注字段{
  "documentId": "",
  "language": "zh-CN",
  "summary": "",
  "requirements": [],
  "characters": [],
  "worldRules": [],
  "visualReferences": [],
  "deliveryConstraints": []
}6.5 多模态输入标注规范每个输入必须有：{
  "inputId": "",
  "type": "video_file/image_file/audio_file/document/text",
  "role": "reference/source/brief/asset",
  "source": "user_upload/crux_capture/external_url",
  "checksum": "",
  "version": 1,
  "metadata": {},
  "analysis": {},
  "linkedStages": [],
  "linkedCreativeBiblePath": "",
  "usageWeight": 0.0,
  "lockLevel": "weak/medium/strong"
}usageWeight 建议权重含义0.2仅作灵感0.5中等参考0.8强参考1.0必须严格遵守lockLevel等级含义weak可偏离medium需保持大方向strong必须严格保持locked不可更改，除非用户确认7. V2 知识包落地建议建议拆成以下 pack：knowledge/packs/
01-video-production-24-stages.md
02-prompt-engineering-stage-templates.md
03-creative-bible-reference.md
04-quality-management.md
05-project-delivery-management.md
06-multimodal-input-processing.md
07-style-anchor-library.md
08-client-communication.md每个 pack metadata：{
  "packId": "video-production-24-stages",
  "version": "1.0.0",
  "domains": ["video_production", "workflow", "qa"],
  "stageRoutes": ["all"],
  "loadMode": "on_demand",
  "defaultLoad": false,
  "triggerHints": [
    "stage best practice",
    "quality checklist",
    "workflow repair",
    "delivery readiness"
  ]
}
这版可以直接作为 V2 的 世界知识库基础版。下一步最适合做的是把它拆成 8 个 knowledge pack，并为每个 pack 生成 manifest 元数据和 stageRoutes。