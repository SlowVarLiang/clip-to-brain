"""平台域名注册表 — 用于识别链接来源并展示给用户。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformInfo:
    name: str
    domains: tuple[str, ...]
    backend: str  # "native" | "ytdlp" | "both"


# native = parse-video-py 原生解析
# ytdlp  = yt-dlp 兜底
# both   = 先 native，失败再 ytdlp
PLATFORMS: tuple[PlatformInfo, ...] = (
    # ── 国内短视频 ──
    PlatformInfo("抖音", ("v.douyin.com", "www.douyin.com", "www.iesdouyin.com", "douyin.com"), "both"),
    PlatformInfo("快手", ("v.kuaishou.com", "www.kuaishou.com", "chenzhongtech.com", "gifshow.com"), "both"),
    PlatformInfo("小红书", ("xiaohongshu.com", "xhslink.com", "xhs.cn"), "both"),
    PlatformInfo("微博", ("weibo.com", "weibo.cn", "m.weibo.cn"), "native"),
    PlatformInfo("微视", ("weishi.qq.com", "isee.weishi.qq.com"), "native"),
    PlatformInfo("皮皮虾", ("pipix.com", "h5.pipix.com"), "native"),
    PlatformInfo("皮皮搞笑", ("pipigx.com", "h5.pipigx.com"), "native"),
    PlatformInfo("最右", ("xiaochuankeji.cn", "share.xiaochuankeji.cn", "izuiyou.com"), "native"),
    PlatformInfo("西瓜视频", ("ixigua.com", "v.ixigua.com"), "native"),
    PlatformInfo("今日头条", ("toutiao.com", "m.toutiao.com", "m.toutiaocdn.com"), "ytdlp"),
    PlatformInfo("火山小视频", ("huoshan.com", "hotsoon.snssdk.com"), "ytdlp"),
    PlatformInfo("度小视/全民小视频", ("xspshare.baidu.com", "quanmin.baidu.com"), "native"),
    PlatformInfo("好看视频", ("haokan.baidu.com", "haokan.hao123.com"), "native"),
    PlatformInfo("梨视频", ("pearvideo.com", "www.pearvideo.com"), "native"),
    PlatformInfo("美拍", ("meipai.com",), "native"),
    PlatformInfo("全民K歌", ("kg.qq.com",), "native"),
    PlatformInfo("逗拍", ("doupai.cc",), "native"),
    PlatformInfo("绿洲", ("weibo.cn/square",), "native"),
    # ── 长视频 / 综合 ──
    PlatformInfo("哔哩哔哩", ("bilibili.com", "b23.tv", "bili2233.cn"), "native"),
    PlatformInfo("AcFun", ("acfun.cn",), "native"),
    PlatformInfo("腾讯视频", ("v.qq.com", "m.v.qq.com"), "native"),
    PlatformInfo("搜狐视频", ("sohu.com", "tv.sohu.com", "my.tv.sohu.com"), "native"),
    PlatformInfo("央视网", ("cctv.com", "cctv.cn", "tv.cctv.cn"), "native"),
    PlatformInfo("新片场", ("xinpianchang.com",), "native"),
    PlatformInfo("虎牙", ("huya.com", "v.huya.com"), "native"),
    PlatformInfo("六间房", ("6.cn",), "native"),
    PlatformInfo("QQ看点", ("kandian.qq.com", "view.inews.qq.com"), "ytdlp"),
    # ── 音乐 / 社交 ──
    PlatformInfo("Twitter/X", ("twitter.com", "x.com", "t.co", "mobile.twitter.com"), "both"),
    PlatformInfo("知乎", ("zhihu.com", "zhuanlan.zhihu.com"), "ytdlp"),
    PlatformInfo("网易云音乐", ("music.163.com", "y.music.163.com"), "ytdlp"),
    PlatformInfo("酷狗音乐", ("kugou.com",), "ytdlp"),
    PlatformInfo("酷我音乐", ("kuwo.cn",), "ytdlp"),
    PlatformInfo("唱吧", ("changba.com",), "ytdlp"),
    PlatformInfo("YY", ("yy.com",), "ytdlp"),
    PlatformInfo("陌陌", ("immomo.com", "m.immomo.com"), "ytdlp"),
    # ── 国际平台 ──
    PlatformInfo("TikTok", ("tiktok.com", "vm.tiktok.com", "vt.tiktok.com", "tiktokv.com"), "ytdlp"),
    PlatformInfo("YouTube", ("youtube.com", "youtu.be", "youtube-nocookie.com"), "ytdlp"),
    PlatformInfo("Instagram", ("instagram.com",), "ytdlp"),
    PlatformInfo("Facebook", ("facebook.com", "fb.watch", "fb.com"), "ytdlp"),
    PlatformInfo("Vimeo", ("vimeo.com",), "ytdlp"),
    PlatformInfo("Reddit", ("reddit.com", "v.redd.it"), "ytdlp"),
    PlatformInfo("VUE", ("vuevideo.net",), "ytdlp"),
    # ── 浏览器 / 资讯 ──
    PlatformInfo("腾讯新闻", ("news.qq.com", "new.qq.com"), "ytdlp"),
    PlatformInfo("人民日报", ("people.cn", "people.com.cn", "app.people.cn"), "ytdlp"),
    PlatformInfo("开眼", ("eyepetizer.net", "open.eyepetizer.net"), "ytdlp"),
    PlatformInfo("懂车帝", ("dongchedi.com", "dcdapp.com"), "ytdlp"),
    PlatformInfo("趣头条", ("qutoutiao.net", "qutoutiao.com"), "ytdlp"),
    PlatformInfo("剪映", ("capcut.cn", "capcut.com", "lv.ulikecam.com"), "ytdlp"),
    PlatformInfo("迅雷", ("xunlei.com",), "ytdlp"),
    # ── 电商 (部分含视频) ──
    PlatformInfo("京东", ("jd.com", "3.cn"), "ytdlp"),
    PlatformInfo("淘宝", ("taobao.com", "tb.cn"), "ytdlp"),
    PlatformInfo("天猫", ("tmall.com",), "ytdlp"),
    PlatformInfo("拼多多", ("yangkeduo.com", "pinduoduo.com", "mobile.yangkeduo.com"), "ytdlp"),
    PlatformInfo("大众点评", ("dianping.com",), "ytdlp"),
    PlatformInfo("微信视频号", ("weixin.qq.com/sph", "channels.weixin.qq.com"), "native"),
)


def detect_platform(url: str) -> PlatformInfo | None:
    url_lower = url.lower()
    for platform in PLATFORMS:
        for domain in platform.domains:
            if domain in url_lower:
                return platform
    return None


def list_platforms() -> list[str]:
    return [p.name for p in PLATFORMS]
