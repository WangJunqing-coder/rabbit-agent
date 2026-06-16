"""
浏览器控制工具
"""
import asyncio
import json
from typing import Optional

from tools.registry import tool


@tool(
    name="web_fetch",
    description="获取网页内容。用于读取文档、API 文档、在线资源等。",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "网页 URL"
            },
            "extract_text": {
                "type": "boolean",
                "description": "是否只提取文本",
                "default": True
            }
        },
        "required": ["url"]
    }
)
async def web_fetch(url: str, extract_text: bool = True) -> dict:
    """获取网页内容"""
    try:
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, follow_redirects=True, timeout=30)
            response.raise_for_status()
            
            content = response.text
            
            if extract_text:
                # 简单的 HTML 标签移除
                import re
                # 移除 script 和 style 标签
                content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
                content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL)
                # 移除 HTML 标签
                content = re.sub(r'<[^>]+>', ' ', content)
                # 清理空白
                content = re.sub(r'\s+', ' ', content).strip()
                content = content[:5000]
            
            return {
                "success": True,
                "url": url,
                "status_code": response.status_code,
                "content": content[:5000]
            }
            
    except Exception as e:
        return {
            "success": False,
            "url": url,
            "error": str(e)
        }


@tool(
    name="web_search",
    description="搜索网络。使用搜索引擎查找信息。",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词"
            },
            "num_results": {
                "type": "integer",
                "description": "返回结果数量",
                "default": 5
            }
        },
        "required": ["query"]
    }
)
async def web_search(query: str, num_results: int = 5) -> dict:
    """网络搜索"""
    # 使用 DuckDuckGo Lite 版本
    try:
        import httpx
        from urllib.parse import quote
        
        url = f"https://lite.duckduckgo.com/lite/?q={quote(query)}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, follow_redirects=True, timeout=30)
            
            # 简单解析结果
            import re
            
            # 提取链接和标题
            results = []
            links = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>', response.text)
            
            for link, title in links[:num_results * 2]:
                if link.startswith('http') and 'duckduckgo' not in link:
                    results.append({
                        "title": title.strip(),
                        "url": link
                    })
                    if len(results) >= num_results:
                        break
            
            return {
                "success": True,
                "query": query,
                "results": results
            }
            
    except Exception as e:
        return {
            "success": False,
            "query": query,
            "error": str(e)
        }


@tool(
    name="download_file",
    description="下载文件到本地。",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "文件 URL"
            },
            "save_path": {
                "type": "string",
                "description": "保存路径"
            }
        },
        "required": ["url", "save_path"]
    }
)
async def download_file(url: str, save_path: str) -> dict:
    """下载文件"""
    try:
        import httpx
        from pathlib import Path
        
        save_file = Path(save_path).resolve()
        save_file.parent.mkdir(parents=True, exist_ok=True)
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, follow_redirects=True, timeout=120)
            response.raise_for_status()
            
            with open(save_file, "wb") as f:
                f.write(response.content)
            
            return {
                "success": True,
                "url": url,
                "path": str(save_file),
                "size": len(response.content)
            }
            
    except Exception as e:
        return {
            "success": False,
            "url": url,
            "error": str(e)
        }
