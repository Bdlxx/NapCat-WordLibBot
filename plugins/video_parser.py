"""
视频解析插件 - 检测群内分享的视频链接，解析并发送无水印版本
支持平台：哔哩哔哩、抖音、快手、小红书、TikTok

解析策略：
- 哔哩哔哩：公开 API（无需登录）
- 抖音：web API + 模拟浏览器辅助
- TikTok：web API
- 快手/小红书：Playwright 模拟浏览器提取
"""

import asyncio
import json
import os
import re
import sys
import time
import requests

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.api import send_message
from utils.config import get_bot_name, get_bot_qq, get_config
from utils.plugin_toggle import is_enabled as _pt_enabled, set_enabled as _pt_set

# ========== 配置 ==========
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(DATA_DIR, "video_parser_config.json")

DEFAULT_CONFIG = {
    "enabled": True,
    "auto_send_video": True,
    "auto_send_images": True,
    "max_images": 9,
    "@_reply": True,
    "show_source": True,
}

_CONFIG = {}
_browser_pool = None

def _load_config():
    global _CONFIG
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                _CONFIG = json.load(f)
        except:
            _CONFIG = {}
    else:
        _CONFIG = {}
    for k, v in DEFAULT_CONFIG.items():
        _CONFIG.setdefault(k, v)
    _save_config()

def _save_config():
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(_CONFIG, f, ensure_ascii=False, indent=2)

def cfg(key, default=None):
    return _CONFIG.get(key, default)

_load_config()

# ========== 平台匹配 ==========
PLATFORM_PATTERNS = [
    (r'https?://v\.douyin\.com/[A-Za-z0-9_-]+/?', '抖音'),
    (r'https?://www\.douyin\.com/video/\d+', '抖音'),
    (r'https?://www\.iesdouyin\.com/\S+', '抖音'),
    (r'https?://www\.douyin\.com/share/video/\d+', '抖音'),
    (r'https?://www\.bilibili\.com/video/BV[\w]+', '哔哩哔哩'),
    (r'https?://b23\.tv/[\w]+', '哔哩哔哩'),
    (r'https?://m\.bilibili\.com/video/BV[\w]+', '哔哩哔哩'),
    (r'https?://v\.kuaishou\.com/[A-Za-z0-9_-]+/?', '快手'),
    (r'https?://www\.kuaishou\.com/\S+', '快手'),
    (r'https?://www\.xiaohongshu\.com/explore/[\w]+', '小红书'),
    (r'https?://www\.xiaohongshu\.com/discovery/item/[\w]+', '小红书'),
    (r'https?://xhslink\.com/[A-Za-z0-9_-]+/?', '小红书'),
    (r'https?://www\.tiktok\.com/@[\w.-]+/video/\d+', 'TikTok'),
    (r'https?://vt\.tiktok\.com/[A-Za-z0-9_-]+/?', 'TikTok'),
    (r'https?://vm\.tiktok\.com/[A-Za-z0-9_-]+/?', 'TikTok'),
]

PLATFORM_NAMES = {
    '抖音': '🎵', '哔哩哔哩': '📺', '快手': '🎬',
    '小红书': '📕', 'TikTok': '🌍',
}

BOT_NAME = get_bot_name()
_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')


def extract_url(text):
    for pattern, platform in PLATFORM_PATTERNS:
        match = re.search(pattern, text)
        if match:
            url = match.group(0)
            url = re.sub(r'[^\w/:-]$', '', url)
            if url.startswith('http://'):
                url = url.replace('http://', 'https://', 1)
            return url, platform
    return None, None


def _req_headers(referer=None):
    h = {'User-Agent': _UA}
    if referer:
        h['Referer'] = referer
    return h


# ========== 哔哩哔哩：公开 API ==========
def _parse_bilibili(bvid):
    """B站用公开API取视频地址"""
    headers = _req_headers('https://www.bilibili.com/')
    info = requests.get(f'https://api.bilibili.com/x/web-interface/view?bvid={bvid}',
                        headers=headers, timeout=15)
    if info.status_code != 200 or info.json().get('code') != 0:
        return None
    d = info.json()['data']
    title = d.get('title', '')
    author = d.get('owner', {}).get('name', '')
    cid = d['pages'][0]['cid']
    p = requests.get(
        f'https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&qn=80&fnver=0&fnval=16',
        headers=headers, timeout=15
    )
    if p.status_code != 200 or p.json().get('code') != 0:
        return None
    video_data = p.json()['data']
    video_url = ''
    for item in video_data.get('durl', []):
        video_url = item.get('url', '') or video_url
    if not video_url:
        videos = video_data.get('dash', {}).get('video', [])
        if videos:
            videos.sort(key=lambda x: x.get('id', 0), reverse=True)
            video_url = videos[0].get('base_url', '')
    if not video_url:
        return None
    return {'video_url': video_url, 'image_list': [], 'title': title, 'author': author}


# ========== 抖音：Playwright 浏览器自动化 (hellotik.app) ==========

def _parse_douyin(url):
    """抖音：用 Playwright 打开 hellotik.app，自动粘贴链接→解析→取结果"""
    try:
        return asyncio.run(_parse_douyin_async(url))
    except Exception as e:
        print(f"[视频解析] 抖音 Playwright 异常: {e}")
        import traceback
        traceback.print_exc()
        return None

async def _parse_douyin_async(url):
    """异步：浏览器操作 hellotik.app"""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
            ]
        )
        ctx = await browser.new_context(
            user_agent=('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/120.0.0.0 Safari/537.36'),
            locale='zh-CN',
            viewport={'width': 1280, 'height': 800},
            # 去除 webdriver 特征
            permissions=[],
        )
        # 注入 stealth 脚本
        await ctx.add_init_script('''() => {
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });
        }''')

        page = await ctx.new_page()

        print(f"[视频解析] 打开 hellotik.app ...")
        try:
            await page.goto('https://www.hellotik.app/zh/douyin',
                           wait_until='networkidle', timeout=20000)
        except Exception as e:
            print(f"[视频解析] hellotik 页面加载超时，继续: {e}")

        await page.wait_for_timeout(1500)

        # 检查页面是否正常
        body_text = await page.evaluate('() => document.body.innerText')
        if '解析' not in body_text:
            print(f"[视频解析] hellotik 页面异常: {body_text[:200]}")
            await browser.close()
            return None

        # 用原生 setter 设置输入框（React 需要正确的 input 事件）
        print(f"[视频解析] 填入链接...")
        await page.evaluate(f'''() => {{
            const input = document.querySelector('input[type="text"], input:not([type="hidden"])');
            if (!input) return false;
            // React 兼容的输入方式
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            ).set;
            nativeInputValueSetter.call(input, '{url}');
            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
            input.dispatchEvent(new Event('change', {{ bubbles: true }}));
            return true;
        }}''')
        await page.wait_for_timeout(500)

        # 点击解析按钮
        print(f"[视频解析] 点击解析...")
        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('button[type="submit"]')
                     || document.querySelector('button:has-text("解析")')
                     || [...document.querySelectorAll('button')].find(b => b.textContent.includes('解析'));
            if (btn) { btn.click(); return true; }
            return false;
        }''')
        if not clicked:
            print("[视频解析] 未找到解析按钮")
            await browser.close()
            return None

        # 等待解析结果（最多等 20 秒）
        print(f"[视频解析] 等待解析结果...")
        result = None
        for _ in range(20):
            await page.wait_for_timeout(1000)

            result = await page.evaluate('''() => {
                // 找 video 标签
                const v = document.querySelector('video');
                if (v && v.getAttribute('src') && v.getAttribute('src').length > 20
                    && !v.getAttribute('src').includes('uuu_')) {
                    return {type: 'video', url: v.getAttribute('src')};
                }

                // 找下载按钮/链接
                const links = document.querySelectorAll('a[href*=".mp4"], a[download]');
                for (const a of links) {
                    if (a.href) return {type: 'link', url: a.href};
                }

                // 找页面文本中的 mp4 链接
                const text = document.body.innerText;
                const m = text.match(/https?:\\/\\/[^\\s"'<>]+\\.mp4[^\\s"'<>]*/);
                if (m) return {type: 'text', url: m[0]};

                // 没找到但还在加载
                if (text.includes('解析失败') || text.includes('错误')) {
                    return {type: 'error', text: text.substring(0, 200)};
                }

                // 还在处理中
                if (text.includes('解析中') || text.includes('处理')) {
                    return {type: 'loading'};
                }

                return null; // 继续等
            }''')

            if result and result.get('type') in ('video', 'link', 'text'):
                video_url = result['url']
                print(f"[视频解析] 获取到视频链接")

                # 获取标题和作者信息
                info = await page.evaluate('''() => {
                    const text = document.body.innerText;
                    const lines = text.split('\\n').filter(l => l.trim());
                    const title = lines.find(l => l.length > 5 && l.length < 100) || '';
                    return {title};
                }''')

                await browser.close()
                return {
                    'video_url': video_url,
                    'image_list': [],
                    'title': info.get('title', '') or '',
                    'author': '',
                }

            if result and result.get('type') == 'error':
                print(f"[视频解析] hellotik 解析失败: {result.get('text', '')}")
                await browser.close()
                return None

        # 超时
        print("[视频解析] hellotik 解析超时")
        await browser.close()
        return None
        import traceback
        traceback.print_exc()
        return None


# ========== TikTok：web API ==========
def _parse_tiktok(url):
    """TikTok：用 oembed/公开接口取视频"""
    headers = _req_headers('https://www.tiktok.com/')
    try:
        r = requests.get(f'https://www.tiktok.com/oembed?url={url}', headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return {
                'video_url': data.get('thumbnail_url', ''),
                'image_list': [],
                'title': data.get('title', ''),
                'author': data.get('author_name', ''),
            }
    except:
        pass
    return None


# ========== Playwright 模拟浏览器（快手、小红书） ==========
async def _parse_with_browser(url, platform):
    """用 Playwright 打开页面提取视频/图片"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[视频解析] 需要 playwright: pip3 install playwright && playwright install chromium")
        return None

    global _browser_pool
    if _browser_pool is None:
        p = await async_playwright().start()
        _browser_pool = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )

    ctx = await _browser_pool.new_context(
        user_agent=_UA,
        viewport={'width': 1920, 'height': 1080},
        locale='zh-CN',
    )
    page = await ctx.new_page()
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)

        if platform == '快手':
            # 尝试提取 video 标签
            video = await page.eval_on_selector_all(
                'video source[src]',
                'els => els.map(e => e.getAttribute("src")).filter(Boolean)'
            ) or await page.evaluate('''() => {
                const v = document.querySelector('video');
                return v ? v.getAttribute('src') || (v.querySelector("source")||{}).getAttribute("src") : null;
            }''')
            if video:
                v = video[0] if isinstance(video, list) else video
                return {'video_url': v, 'image_list': [], 'title': '', 'author': ''}
            # og:video
            og = await page.evaluate(
                "document.querySelector('meta[property=\"og:video\"]')?.getAttribute('content')")
            if og:
                return {'video_url': og, 'image_list': [], 'title': '', 'author': ''}

        elif platform == '小红书':
            await page.wait_for_timeout(3000)
            imgs = await page.evaluate(r'''() => {
                const urls = new Set();
                document.querySelectorAll('img').forEach(img => {
                    const src = img.getAttribute('src') || img.getAttribute('data-src') || '';
                    if (src.includes('xhscdn.com') && !src.includes('avatar') && !src.includes('icon')) {
                        // 取最大图
                        urls.add(src.replace(/!thumbnail|!webp|!w\d+_\d+/g, '').replace('http://', 'https://'));
                    }
                });
                return [...urls];
            }''')
            if imgs:
                return {'video_url': '', 'image_list': [{'url': u} for u in imgs],
                        'title': '', 'author': ''}

        return None
    finally:
        await page.close()
        await ctx.close()


# ========== 入口调度 ==========
def parse_video(url, platform):
    """同步入口，根据平台选解析策略"""
    try:
        if platform == '哔哩哔哩':
            m = re.search(r'BV[\w]+', url)
            if m:
                return _parse_bilibili(m.group(0))
        elif platform == '抖音':
            return _parse_douyin(url)
        elif platform == 'TikTok':
            return _parse_tiktok(url)
        elif platform in ('快手', '小红书'):
            result = asyncio.run(_parse_with_browser(url, platform))
            return result
    except Exception as e:
        print(f"[视频解析] 解析 {platform} 失败: {e}")
        import traceback
        traceback.print_exc()
    return None


# ========== 消息发送 ==========
def send_video(event, video_url, platform, title, author):
    user_id = event.get("user_id")
    group_id = event.get("group_id")
    msg = []
    if cfg("@_reply"):
        msg.append({"type": "at", "data": {"qq": user_id}})
    txt = f"\n📹 视频解析结果"
    if cfg("show_source") and platform:
        txt += f" ({PLATFORM_NAMES.get(platform, '')}{platform})"
    if title:
        txt += f"\n📌 {title[:50]}"
    if author:
        txt += f"\n👤 {author[:20]}"
    msg.append({"type": "text", "data": {"text": txt + "\n"}})
    msg.append({"type": "video", "data": {"file": video_url}})
    print(f"[视频解析] 发送视频到群 {group_id}")
    send_message(event, msg)


def send_images(event, image_urls, platform, title, author):
    user_id = event.get("user_id")
    group_id = event.get("group_id")
    max_img = cfg("max_images", 9)
    imgs = image_urls[:max_img]
    msg = []
    if cfg("@_reply"):
        msg.append({"type": "at", "data": {"qq": user_id}})
    txt = f"\n📸 图片解析结果"
    if cfg("show_source") and platform:
        txt += f" ({PLATFORM_NAMES.get(platform, '')}{platform})"
    if title:
        txt += f"\n📌 {title[:50]}"
    txt += f"\n共 {len(imgs)} 张图片"
    msg.append({"type": "text", "data": {"text": txt}})
    send_message(event, msg)
    for u in imgs:
        time.sleep(0.3)
        send_message(event, [{"type": "image", "data": {"file": u}}])
        print(f"[视频解析] 发送图片 {group_id}")


def is_master(user_id):
    ml = get_config("MASTER_QQ", [])
    if not isinstance(ml, list):
        ml = [ml]
    return str(user_id) in [str(m) for m in ml]


def handle(event):
    if event.get("post_type") != "message":
        return False

    raw = event.get("raw_message", "").strip()
    uid = event.get("user_id", 0)

    if is_master(uid):
        if raw == "开启视频解析" or raw.endswith("开启视频解析"):
            if event.get("message_type") == "group":
                _pt_set(event.get("group_id"), "video_parser", True)
                send_message(event, "视频解析已在本群开启")
            else:
                _CONFIG["enabled"] = True; _save_config()
                send_message(event, "视频解析已开启")
            return True
        if raw == "关闭视频解析" or raw.endswith("关闭视频解析"):
            if event.get("message_type") == "group":
                _pt_set(event.get("group_id"), "video_parser", False)
                send_message(event, "视频解析已在本群关闭")
            else:
                _CONFIG["enabled"] = False; _save_config()
                send_message(event, "视频解析已关闭")
            return True

    if not cfg("enabled", True):
        return False
    if event.get("message_type") != "group":
        return False
    # 分群检查
    if not _pt_enabled(event.get("group_id"), "video_parser"):
        return False
    if not raw:
        return False

    url, platform = extract_url(raw)
    if not url or not platform:
        return False

    print(f"[视频解析] {platform}: {url[:50]}...")
    send_message(event, f"⏳ 正在解析{platform}视频，请稍候...")
    result = parse_video(url, platform)
    if not result:
        print(f"[视频解析] {platform} 解析失败")
        return True

    video_url = result.get("video_url", "")
    image_list = result.get("image_list", [])
    title = result.get("title", "")
    author = result.get("author", "")

    img_urls = []
    for img in image_list:
        u = img.get("url") if isinstance(img, dict) else img
        if u:
            img_urls.append(u)

    has_video = bool(video_url) and cfg("auto_send_video", True)
    has_images = bool(img_urls) and cfg("auto_send_images", True)

    if not has_video and not has_images:
        print(f"[视频解析] 无内容可发")
        return True

    if has_video:
        send_video(event, video_url, platform, title, author)
    elif has_images:
        send_images(event, img_urls, platform, title, author)
    return True
