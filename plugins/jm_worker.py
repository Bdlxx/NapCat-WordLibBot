#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JM 下载工作进程（由 jm_downloader 插件以子进程方式调用）

设计原因：
1. jmcomic 库需要经常自动更新（禁漫反爬频繁变化），子进程隔离保证
   更新后下一次下载立即生效，无需重启机器人。
2. 下载任务耗时长、可能抛异常，隔离在子进程中不会影响主程序。

协议：
- 标准输出中的 "[JM_PROGRESS] {json}" 行会被插件转发到群/私聊
- 结束前把结果写入 --result 指定的 json 文件
- 退出码 0 成功，1 失败

本文件被主程序 import 时不会执行任何逻辑（__main__ 保护）。
"""
import argparse
import json
import os
import sys
import traceback


def log_progress(**kwargs):
    """输出进度行，插件会解析并转发给用户"""
    print(f"[JM_PROGRESS] {json.dumps(kwargs, ensure_ascii=False)}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="JM 下载工作进程")
    parser.add_argument("--option", required=True, help="jmcomic option yml 路径")
    parser.add_argument("--result", required=True, help="结果 json 输出路径")
    parser.add_argument("--ids", nargs="*", required=True,
                        help="本子id列表；支持 p<章节id> 表示只下载某章节，如 123456 或 123456 p789")
    parser.add_argument("--detail-only", action="store_true",
                        help="只查询本子详情并输出，不下载")
    args = parser.parse_args()

    try:
        import jmcomic
    except Exception as e:
        traceback.print_exc()
        _write_result(args.result, ok=False, error=f"无法导入 jmcomic 库: {e}")
        return 1

    option = None
    try:
        option = jmcomic.create_option_by_file(args.option)
        client = option.new_jm_client()
    except Exception as e:
        traceback.print_exc()
        _write_result(args.result, ok=False, error=f"初始化 option 失败: {e}")
        return 1

    results = []
    try:
        for raw_id in args.ids:
            raw_id = raw_id.strip()
            if not raw_id:
                continue
            # 解析 "123456" 或 "123456p789" / "p789"
            album_id = raw_id
            photo_id = None
            lower = raw_id.lower()
            if lower.startswith("p"):
                photo_id = lower[1:]
                album_id = None
            elif "p" in lower:
                album_id, _, photo_id = lower.partition("p")

            if album_id is None:
                # 只有章节id，需要先从章节拿到所属本子
                photo = client.get_photo_detail(photo_id)
                album_id = photo.album_id

            album = client.get_album_detail(album_id)
            log_progress(type="detail",
                         album_id=album_id,
                         photo_id=photo_id,
                         title=album.name,
                         authors=album.authors,
                         tags=album.tags,
                         page_count=getattr(album, "page_count", 0),
                         pub_date=getattr(album, "pub_date", ""),
                         update_date=getattr(album, "update_date", ""),
                         views=getattr(album, "views", ""),
                         likes=getattr(album, "likes", ""),
                         episode_count=len(album),
                         jmcomic_version=jmcomic.__version__,
                         )

            if args.detail_only:
                continue

            if photo_id:
                log_progress(type="download_start", album_id=album_id, photo_id=photo_id,
                             mode="photo")
                res = jmcomic.download_photo(photo_id, option, check_exception=True)
                detail = res.detail
            else:
                log_progress(type="download_start", album_id=album_id, mode="album",
                             episode_count=len(album))
                res = jmcomic.download_album(album_id, option, check_exception=True)
                detail = res.detail

            pdfs = res.manifest.get_export_filepath_list("pdf")
            log_progress(type="done",
                         album_id=album_id,
                         photo_id=photo_id,
                         title=detail.name,
                         pdfs=pdfs,
                         )
            results.append({
                "album_id": album_id,
                "photo_id": photo_id,
                "title": detail.name,
                "pdfs": pdfs,
            })

        _write_result(args.result, ok=True, results=results, version=jmcomic.__version__)
        return 0
    except Exception as e:
        traceback.print_exc()
        _write_result(args.result, ok=False, error=f"{type(e).__name__}: {e}")
        return 1


def _write_result(path, ok, **extra):
    out = {"ok": ok}
    out.update(extra)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    except Exception:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(json.dumps(out, ensure_ascii=False))
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
