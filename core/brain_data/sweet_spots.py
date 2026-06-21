"""Brain data: sweet spots knowledge base."""
SWEET_SPOT_TEMPLATES = {
    "portrait": {
        "name": "人像写真",
        "suffix": "professional portrait photography, studio lighting, soft Rembrandt lighting, shallow depth of field, 85mm lens, sharp focus on eyes, skin detail, photorealistic, 8k, high detail",
        "negative": "extra fingers, extra hands, mutated hands, deformed hands, fused fingers, missing fingers, wrong hand anatomy, extra arms, extra limbs, crossed eyes, asymmetric eyes, deformed face, distorted face, ugly, bad anatomy, wrong proportions, clipping, mesh penetration, watermark, text, low quality, blurry",
        "description": "专业人像摄影，避免多手/穿模",
    },
    "full_body": {
        "name": "全身人物",
        "suffix": "full body shot, standing pose, natural proportions, dynamic lighting, photorealistic, high detail, 8k resolution, professional color grading",
        "negative": "extra fingers, extra hands, mutated hands, deformed hands, fused fingers, missing fingers, wrong hand anatomy, extra arms, extra limbs, limb cutoff, body out of frame, head out of frame, bad anatomy, wrong proportions, clipping, intersecting bodies, mesh penetration, fused bodies, merged bodies, floating limbs, disconnected limbs, watermark, text, low quality, blurry",
        "description": "全身人物，重点防穿模/断肢",
    },
    "action": {
        "name": "动作场景",
        "suffix": "dynamic action pose, motion blur, dramatic lighting, cinematic composition, photorealistic, high detail, 8k",
        "negative": "extra fingers, extra hands, mutated hands, deformed hands, fused fingers, wrong hand anatomy, extra arms, extra limbs, bad anatomy, distorted pose, clipping, intersecting bodies, mesh penetration, fused bodies, floating limbs, disconnected limbs, static, frozen, blurry, low quality, watermark",
        "description": "动作/打斗场景，防穿模+动态",
    },
    "animal": {
        "name": "动物",
        "suffix": "wildlife photography, natural habitat, telephoto lens, golden hour lighting, photorealistic, detailed fur/feathers, 8k, national geographic style",
        "negative": "extra limbs, extra heads, mutated anatomy, deformed body, wrong proportions, clipping, mesh penetration, watermark, text, low quality, blurry, cartoon, anime",
        "description": "动物摄影，防多肢体",
    },
    "landscape": {
        "name": "风景",
        "suffix": "landscape photography, wide angle, golden hour, dramatic sky, deep depth of field, vivid colors, 8k, professional color grading, hdr",
        "negative": "blurry, low quality, watermark, text, signature, overexposed, underexposed, noise, grain, compression artifacts, distorted perspective",
        "description": "风景摄影，注重画质",
    },
    "food": {
        "name": "美食",
        "suffix": "food photography, close-up, studio lighting, shallow depth of field, vibrant colors, steam, fresh ingredients, professional styling, 8k",
        "negative": "blurry, low quality, watermark, text, unappetizing, messy, dirty plate, wrong colors, cartoon, anime",
        "description": "美食摄影，注重色泽",
    },
    "anime": {
        "name": "动漫风格",
        "suffix": "anime style, high quality anime illustration, detailed eyes, clean lineart, vibrant colors, studio lighting, masterpiece, best quality",
        "negative": "extra fingers, extra hands, mutated hands, deformed hands, fused fingers, missing fingers, wrong hand anatomy, extra arms, extra limbs, bad anatomy, wrong proportions, low quality, worst quality, blurry, watermark, text, realistic, photorealistic",
        "description": "动漫风格，防多手+风格偏离",
    },
}

# 视频甜点区预设

SWEET_SPOT_VIDEO_TEMPLATES = {
    "portrait_video": {
        "name": "人物视频",
        "suffix": "subtle head movement, gentle expression change, soft lighting, cinematic, 24fps, smooth motion",
        "negative": "extra fingers, extra hands, mutated hands, deformed hands, fused fingers, wrong hand anatomy, extra arms, extra limbs, bad anatomy, face morphing, body morphing, clipping, intersecting bodies, mesh penetration, flickering, jittery motion, temporal inconsistency, ghosting, double image, static, frozen, blurry, low quality, watermark",
        "description": "人物微动视频，防面部变形",
    },
    "action_video": {
        "name": "动作视频",
        "suffix": "dynamic action, fast camera movement, motion blur, dramatic lighting, cinematic, 24fps",
        "negative": "extra fingers, extra hands, mutated hands, deformed hands, wrong hand anatomy, extra arms, extra limbs, bad anatomy, distorted pose, face morphing, body morphing, clipping, intersecting bodies, mesh penetration, fused bodies, flickering, jittery motion, temporal inconsistency, ghosting, double image, frozen, static, blurry, low quality, watermark, frame skipping, unnatural movement",
        "description": "动作视频，防穿模+时序问题",
    },
    "camera_pan": {
        "name": "镜头运动",
        "suffix": "slow camera pan, tracking shot, smooth movement, cinematic, 24fps, steady cam",
        "negative": "jittery motion, shaky camera, frame skipping, flickering, temporal inconsistency, ghosting, double image, morphing artifacts, static, frozen, blurry, low quality, watermark",
        "description": "纯镜头运动，防抖动+闪烁",
    },
}


# ── 失败修复映射表 ──────────────────────────────────
# 来源：新烬龙V2 negative-prompt-rules.md —— 常见失败现象 → 精准修复关键词

ENTITY_SWEET_SPOT_TEMPLATES = {
    "spirit": {
        "image": {
            "suffix": "ethereal translucent figure, soft inner glow, flowing mist-like edges, floating pose, otherworldly presence, volumetric light, atmospheric, 8k, high detail",
            "negative": "solid body, heavy physical mass, grounded stance, human skin, organic texture, flesh tone, realistic human proportions, extra limbs, clipping, watermark, text, low quality",
        },
        "video": {
            "suffix": "gentle floating motion, ethereal drift, soft pulsing glow, translucent body phase, atmospheric, 24fps, smooth motion",
            "negative": "solid body, heavy landing, grounded walk, physical impact, flesh deformation, clipping, flickering, jittery motion, temporal inconsistency, ghosting, low quality",
        },
    },
    "energy_body": {
        "image": {
            "suffix": "pure luminous energy form, particle body, radiant aura, no solid mass, floating energy core, prismatic light dispersion, 8k, high detail",
            "negative": "solid body, organic texture, flesh, skin, heavy mass, grounded, physical contact, realistic human proportions, clipping, watermark, text, low quality",
        },
        "video": {
            "suffix": "energy pulsing motion, particle flow, slow orbit, light fluctuation, atmospheric, 24fps, smooth motion",
            "negative": "solid body collision, physical impact, organic movement, flesh deformation, clipping, flickering, jittery motion, temporal inconsistency, low quality",
        },
    },
    "anthropomorphic": {
        "image": {
            "suffix": "anthropomorphic character, species-accurate anatomy, detailed fur/scales/feathers, expressive eyes, natural pose, 8k, high detail",
            "negative": "extra fingers, extra hands, wrong digit count, human skin, bare flesh tone, mutated anatomy, deformed paws, clipping, mesh penetration, watermark, text, low quality",
        },
        "video": {
            "suffix": "natural anthropomorphic movement, species-appropriate motion, fluid animation, 24fps, smooth motion",
            "negative": "extra fingers, wrong digit count, human skin, bare flesh, mutated anatomy, face morphing, clipping, flickering, jittery motion, temporal inconsistency, low quality",
        },
    },
    "robot": {
        "image": {
            "suffix": "mechanical body, precise panel lines, synthetic shell, metallic finish, mechanical joints, sensor array, 8k, high detail",
            "negative": "organic skin, flesh, human proportions, soft tissue, body hair, realistic human face, clipping, mesh penetration, watermark, text, low quality",
        },
        "video": {
            "suffix": "mechanical precision movement, servo-driven motion, rigid joint articulation, 24fps, smooth motion",
            "negative": "organic skin, flesh, soft tissue movement, body hair, realistic human face morphing, clipping, flickering, jittery motion, temporal inconsistency, low quality",
        },
    },
    "AI": {
        "image": {
            "suffix": "holographic entity, data particle body, interface glow, digital avatar, translucent projection, 8k, high detail",
            "negative": "solid body, physical mass, organic texture, flesh, skin, grounded, realistic human proportions, clipping, watermark, text, low quality",
        },
        "video": {
            "suffix": "holographic flicker, data stream motion, projection phase shift, digital presence, 24fps, smooth motion",
            "negative": "solid body, physical mass, organic movement, flesh deformation, clipping, flickering, jittery motion, temporal inconsistency, low quality",
        },
    },
    "creature": {
        "image": {
            "suffix": "detailed creature anatomy, species-accurate body structure, natural pose, environmental context, 8k, high detail",
            "negative": "extra limbs, wrong anatomy for species, human-like hands, human face on creature, clipping, mesh penetration, watermark, text, low quality",
        },
        "video": {
            "suffix": "natural creature movement, species-appropriate locomotion, fluid animation, 24fps, smooth motion",
            "negative": "extra limbs, wrong anatomy, human-like movement, face morphing, clipping, flickering, jittery motion, temporal inconsistency, low quality",
        },
    },
    "vehicle_character": {
        "image": {
            "suffix": "sentient vehicle design, expressive front face, functional vehicle body with personality, anthropomorphic vehicle features, 8k, high detail",
            "negative": "ordinary vehicle, no personality, broken mechanics, wrong proportions, floating parts, clipping, watermark, text, low quality",
        },
        "video": {
            "suffix": "expressive vehicle movement, personality-driven motion, responsive driving, 24fps, smooth motion",
            "negative": "ordinary vehicle motion, no personality, mechanical failure, parts falling off, clipping, flickering, jittery motion, temporal inconsistency, low quality",
        },
    },
    "object_character": {
        "image": {
            "suffix": "animated object character, expressive features on inanimate form, clear object identity, personality cues, 8k, high detail",
            "negative": "ordinary object, no personality, broken object, wrong proportions, floating parts, clipping, watermark, text, low quality",
        },
        "video": {
            "suffix": "expressive object animation, personality-driven object motion, bouncing or hopping, 24fps, smooth motion",
            "negative": "ordinary object, static, no animation, broken, wrong proportions, clipping, flickering, jittery motion, temporal inconsistency, low quality",
        },
    },
}

# ── 帅哥美女专属甜点区 ──────────────────────────────────
# 来源：新烬龙V2 character-clothing.md + LTX2.3生产甜点区规格.md

BEAUTY_SWEET_SPOT_TEMPLATES = {
    "handsome": {
        "image": {
            "suffix": "male high-appeal portrait, sharp bone structure, defined jawline, prominent brow bone, straight nose bridge, restrained expression, dimensional lighting, 85mm portrait lens, shallow depth of field, backlit rim light, cinematic, photorealistic, 8k, high detail",
            "negative": "template face, generic male, soft features, feminine jawline, undefined bone structure, exaggerated expression, extra fingers, extra hands, mutated hands, deformed hands, wrong hand anatomy, face distortion, asymmetric eyes, bad anatomy, wrong proportions, watermark, text, low quality, blurry, model catalog pose, same-face syndrome",
        },
        "video": {
            "suffix": "subtle head turn, gentle expression shift, restrained gaze movement, backlit rim light on hair, cinematic portrait video, identity-locked face, 24fps, smooth motion",
            "negative": "template face, face morphing, identity drift, exaggerated expression, extra fingers, extra hands, mutated hands, deformed hands, wrong hand anatomy, body morphing, clipping, flickering, jittery motion, temporal inconsistency, ghosting, double image, static, frozen, blurry, low quality, watermark, same-face syndrome",
        },
    },
    "beauty": {
        "image": {
            "suffix": "female high-appeal portrait, refined bone structure, elegant lip line, layered gaze, facial negative space, 45-degree photogenic angle, backlit contour, soft Rembrandt lighting, 85mm portrait lens, shallow depth of field, cinematic, photorealistic, 8k, high detail",
            "negative": "template face, generic beauty, plain features, hard expression, lifeless eyes, overdone makeup, extra fingers, extra hands, mutated hands, deformed hands, wrong hand anatomy, face distortion, asymmetric eyes, bad anatomy, wrong proportions, watermark, text, low quality, blurry, model catalog pose, same-face syndrome, masculine jawline",
        },
        "video": {
            "suffix": "subtle gaze shift, gentle head tilt, soft hair movement, backlit contour glow, cinematic portrait video, identity-locked face, 24fps, smooth motion",
            "negative": "template face, face morphing, identity drift, hard expression, extra fingers, extra hands, mutated hands, deformed hands, wrong hand anatomy, body morphing, clipping, flickering, jittery motion, temporal inconsistency, ghosting, double image, static, frozen, blurry, low quality, watermark, same-face syndrome, masculine features",
        },
    },
}

# ── 实体专属失败修复映射 ──────────────────────────────────
# 来源：新烬龙V2 asset-continuity.md + business-brain-main-trunk.md
# 每种非人实体的专属失败模式 → 精准修复关键词

COMBAT_SWEET_SPOT_TEMPLATES = {
    "image": {
        "projectile": {
            "name": "战斗-飞行道具(图片)",
            "suffix": "dynamic charging pose, glowing energy gathering at hands, projectile launch with trailing light, impact explosion with debris, cinematic composition, dramatic lighting, photorealistic, 8k",
            "negative": "extra fingers, extra hands, mutated hands, wrong hand anatomy, extra arms, bad anatomy, static pose, no energy effect, flat lighting, missing impact, weak VFX, low quality, blurry, watermark",
        },
        "anti_air": {
            "name": "战斗-升龙对空(图片)",
            "suffix": "upward leap with trailing energy arc, fist at apex with shockwave burst, freeze-frame at peak height, dramatic low-angle perspective, intense upward motion, photorealistic, 8k",
            "negative": "extra fingers, extra hands, mutated hands, wrong hand anatomy, extra arms, bad anatomy, grounded pose, no upward motion, no energy trail, flat angle, low quality, blurry, watermark",
        },
        "spinning": {
            "name": "战斗-旋转旋风(图片)",
            "suffix": "rapid spinning motion with afterimage trails, vortex energy enveloping body, limbs extending with motion blur, top-down or dynamic angle, photorealistic, 8k",
            "negative": "extra fingers, extra hands, mutated hands, extra arms, bad anatomy, static pose, no rotation blur, no afterimage, no energy vortex, low quality, blurry, watermark",
        },
        "rapid_strikes": {
            "name": "战斗-连续打击(图片)",
            "suffix": "rapid multi-hit combo, fan-shaped afterimage array, impact shockwave rings per hit, accelerating rhythm, extreme close-up on final blow, photorealistic, 8k",
            "negative": "extra fingers, extra hands, mutated hands, wrong hand anatomy, extra arms, bad anatomy, single pose no combo, no impact effect, no afterimage, low quality, blurry, watermark",
        },
        "grapple": {
            "name": "战斗-投技抓取(图片)",
            "suffix": "dramatic grab and lift, rotating slam motion, ground impact with crack and dust shockwave, encircling camera angle, photorealistic, 8k",
            "negative": "extra fingers, extra hands, mutated hands, wrong hand anatomy, extra arms, bad anatomy, no grab contact, no ground impact, flat composition, low quality, blurry, watermark",
        },
        "super_move": {
            "name": "战斗-超必杀技(图片)",
            "suffix": "massive aura explosion, energy particles converging, signature ultimate move release, screen-shaking impact, massive explosion with color gradient VFX, slow-motion keyframe, photorealistic, 8k",
            "negative": "extra fingers, extra hands, mutated hands, wrong hand anatomy, extra arms, bad anatomy, weak VFX, no aura, no explosion, no energy effect, flat lighting, anti-climactic, low quality, blurry, watermark",
        },
    },
    "video": {
        "projectile": {
            "name": "战斗-飞行道具(视频)",
            "suffix": "energy charging at hands, projectile launch with glowing trail, impact explosion with debris and screen flash, side-tracking camera, cinematic, smooth motion, 24fps",
            "negative": "extra fingers, extra hands, mutated hands, wrong hand anatomy, extra arms, bad anatomy, flickering, jittery motion, ghosting, double image, temporal inconsistency, frame skipping, missing VFX, no energy trail, weak impact, low quality, watermark",
        },
        "anti_air": {
            "name": "战斗-升龙对空(视频)",
            "suffix": "crouch-to-leap upward arc, energy trail along limb, apex freeze-frame moment, gravity pull-down landing, low-angle camera tilting up, cinematic, smooth motion, 24fps",
            "negative": "extra fingers, extra hands, mutated hands, wrong hand anatomy, extra arms, bad anatomy, flickering, jittery motion, ghosting, double image, temporal inconsistency, frame skipping, no upward motion, no energy trail, low quality, watermark",
        },
        "spinning": {
            "name": "战斗-旋转旋风(视频)",
            "suffix": "spinning acceleration with afterimage trails, vortex energy envelope, deceleration to stop, top-down or side-tracking camera, cinematic, smooth motion, 24fps",
            "negative": "extra fingers, extra hands, mutated hands, wrong hand anatomy, extra arms, bad anatomy, flickering, jittery motion, ghosting, double image, temporal inconsistency, frame skipping, no rotation blur, low quality, watermark",
        },
        "rapid_strikes": {
            "name": "战斗-连续打击(视频)",
            "suffix": "accelerating multi-hit combo with impact frames, afterimage fan array, final blow extreme close-up with shockwave, cinematic, smooth motion, 24fps",
            "negative": "extra fingers, extra hands, mutated hands, wrong hand anatomy, extra arms, bad anatomy, flickering, jittery motion, ghosting, double image, temporal inconsistency, frame skipping, no impact frames, low quality, watermark",
        },
        "grapple": {
            "name": "战斗-投技抓取(视频)",
            "suffix": "quick approach grab, rotating lift and slam, ground impact with crack and dust wave, encircling dolly camera, cinematic, smooth motion, 24fps",
            "negative": "extra fingers, extra hands, mutated hands, wrong hand anatomy, extra arms, bad anatomy, flickering, jittery motion, ghosting, double image, temporal inconsistency, frame skipping, no grab contact, low quality, watermark",
        },
        "super_move": {
            "name": "战斗-超必杀技(视频)",
            "suffix": "aura eruption and energy convergence, signature ultimate release, massive explosion with gradient VFX, slow-motion keyframe into wide shot, camera shake, cinematic, smooth motion, 24fps",
            "negative": "extra fingers, extra hands, mutated hands, wrong hand anatomy, extra arms, bad anatomy, flickering, jittery motion, ghosting, double image, temporal inconsistency, frame skipping, weak VFX, no aura, anti-climactic, low quality, watermark",
        },
    },
}

# ── 战斗专属风险修复映射 ──────────────────────────────────
# 战斗场景特有的失败模式和修复关键词，与通用 NEGATIVE_REPAIR_MAP 互补
