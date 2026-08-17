"""
通用 HTTP 请求工具模块

提供统一的 GET/POST 请求封装，自动处理 JSON 解析、超时、异常包装。
用法：
    from utils.http_client import http_get, http_post_json, HttpError

    data = http_get('https://api.example.com/data', params={'page': 1})
    result = http_post_json('https://api.example.com/submit', data={'name': 'test'})
"""

import json
import requests

# 全局默认超时（秒）
TIMEOUT = 10


class HttpError(Exception):
    """HTTP 请求异常"""
    def __init__(self, message: str, status_code: int = 0):
        self.status_code = status_code
        super().__init__(message)


def http_get(url: str, params: dict = None, headers: dict = None,
             timeout: int = None) -> dict:
    """
    发送 GET 请求并返回 JSON 响应

    :param url: 接口地址
    :param params: URL 查询参数
    :param headers: 自定义请求头
    :param timeout: 超时秒数，默认 TIMEOUT
    :return: 解析后的 JSON dict
    :raises HttpError: 请求失败或状态码异常
    """
    try:
        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=timeout or TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout as e:
        raise HttpError(f"GET 请求超时: {url[:60]}", status_code=0) from e
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else 0
        raise HttpError(f"HTTP {status}: {str(e)[:100]}", status_code=status) from e
    except requests.exceptions.RequestException as e:
        raise HttpError(f"GET 请求失败: {str(e)[:100]}", status_code=0) from e
    except json.JSONDecodeError as e:
        raise HttpError(f"响应不是合法 JSON: {str(e)[:100]}", status_code=0) from e


def http_post_json(url: str, data: dict = None, headers: dict = None,
                   timeout: int = None) -> dict:
    """
    发送 POST 请求（JSON 格式请求体）

    :param url: 接口地址
    :param data: JSON 请求体字典
    :param headers: 自定义请求头（默认自动加 Content-Type: application/json）
    :param timeout: 超时秒数，默认 TIMEOUT
    :return: 解析后的 JSON dict
    :raises HttpError: 请求失败或状态码异常
    """
    req_headers = dict(headers or {})
    req_headers.setdefault('Content-Type', 'application/json')

    try:
        response = requests.post(
            url,
            json=data,
            headers=req_headers,
            timeout=timeout or TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout as e:
        raise HttpError(f"POST 请求超时: {url[:60]}", status_code=0) from e
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else 0
        raise HttpError(f"HTTP {status}: {str(e)[:100]}", status_code=status) from e
    except requests.exceptions.RequestException as e:
        raise HttpError(f"POST 请求失败: {str(e)[:100]}", status_code=0) from e
    except json.JSONDecodeError as e:
        raise HttpError(f"响应不是合法 JSON: {str(e)[:100]}", status_code=0) from e
