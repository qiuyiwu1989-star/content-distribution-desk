"""Versioned integration capabilities, not claims of platform API guarantees."""
RULES_VERSION = '2026-09-26.1'
RULES = {
 'wechat': {'article': {'adapter':'wechatsync','modes':['manual','draft'],'title_max':64,'body_required':True,'cover_recommended':True}, 'gallery':{'adapter':'manual','modes':['manual'],'title_max':64,'image_min':1}},
 'channels': {'video': {'adapter':'sau','modes':['manual','draft','publish'],'title_max':16,'video_required':True,'cover_recommended':True}},
 'rednote': {'gallery':{'adapter':'sau','modes':['manual','publish'],'title_max':20,'body_max':1000,'image_min':1,'image_max':18}, 'video':{'adapter':'sau','modes':['manual','publish'],'title_max':20,'body_max':1000,'video_required':True}},
 'douyin': {'gallery':{'adapter':'sau','modes':['manual','publish'],'title_max':30,'image_min':1,'image_max':35}, 'video':{'adapter':'sau','modes':['manual','publish'],'title_max':30,'video_required':True,'cover_recommended':True}},
 'bilibili': {'video':{'adapter':'sau','modes':['manual','publish'],'title_max':80,'video_required':True,'category_required':True,'tags_required':True}, 'article':{'adapter':'wechatsync','modes':['manual','draft'],'title_max':40,'body_required':True}},
 'zhihu': {'article':{'adapter':'wechatsync','modes':['manual','draft'],'title_max':100,'body_required':True}},
}
MODE_LABELS={'manual':'人工交付','draft':'送入草稿','publish':'提交发布'}
SAU_PLATFORMS={'channels':'tencent','rednote':'xiaohongshu','douyin':'douyin','bilibili':'bilibili'}
WECHAT_PLATFORMS={'wechat':'weixin','zhihu':'zhihu','bilibili':'bilibili'}

def rules_for(platform, format):
    return RULES.get(platform,{}).get(format)
