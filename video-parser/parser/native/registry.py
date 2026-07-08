from .bilibili import BiliBili
from .douyin import DouYin
from .kuaishou import KuaiShou
from .redbook import RedBook
from .weixin_channels import WeiXinChannels

NATIVE_PARSERS = {
    "douyin.com": DouYin,
    "iesdouyin.com": DouYin,
    "kuaishou.com": KuaiShou,
    "chenzhongtech.com": KuaiShou,
    "gifshow.com": KuaiShou,
    "xiaohongshu.com": RedBook,
    "xhslink.com": RedBook,
    "xhs.cn": RedBook,
    "bilibili.com": BiliBili,
    "b23.tv": BiliBili,
    "bili2233.cn": BiliBili,
    "weixin.qq.com": WeiXinChannels,
    "channels.weixin.qq.com": WeiXinChannels,
}


def get_native_parser(url: str):
    url_lower = url.lower()
    for domain, parser_cls in NATIVE_PARSERS.items():
        if domain in url_lower:
            return parser_cls()
    return None
