"""
浏览器控制工具 - 网页抓取和简单交互
"""
import json
import sys
import os
import asyncio
from typing import Optional
from dataclasses import dataclass

# 确保能导入 beautifulsoup4
try:
    from bs4 import BeautifulSoup
except ImportError:
    # 尝试添加系统 Python 路径
    system_site_packages = r'C:\Users\21112\AppData\Local\Programs\Python\Python311\Lib\site-packages'
    if os.path.exists(system_site_packages):
        sys.path.insert(0, system_site_packages)
    from bs4 import BeautifulSoup

import httpx

from tools.registry import tool


@dataclass
class PageInfo:
    """页面信息"""
    url: str
    title: str
    content: str
    links: list[dict]
    forms: list[dict]
    status_code: int


class BrowserClient:
    """浏览器客户端（简化版）"""
    
    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )
        self.cookies: dict = {}
        self.history: list[str] = []
    
    async def get(self, url: str) -> PageInfo:
        """获取页面"""
        response = await self.client.get(url, cookies=self.cookies)
        response.raise_for_status()
        
        # 更新 cookies
        self.cookies.update(dict(response.cookies))
        self.history.append(url)
        
        return self._parse_page(url, response)
    
    async def post(self, url: str, data: dict = None, json_data: dict = None) -> PageInfo:
        """提交表单"""
        response = await self.client.post(
            url,
            data=data,
            json=json_data,
            cookies=self.cookies
        )
        response.raise_for_status()
        
        self.cookies.update(dict(response.cookies))
        self.history.append(url)
        
        return self._parse_page(url, response)
    
    async def search(self, query: str, engine: str = "duckduckgo") -> list[dict]:
        """搜索"""
        if engine == "duckduckgo":
            url = f"https://html.duckduckgo.com/html/?q={query}"
        elif engine == "google":
            url = f"https://www.google.com/search?q={query}"
        else:
            return [{"error": f"Unsupported search engine: {engine}"}]
        
        try:
            page = await self.get(url)
            
            # 解析搜索结果
            results = []
            soup = BeautifulSoup(page.content, "html.parser")
            
            # DuckDuckGo 结果
            for result in soup.select(".result"):
                title_elem = result.select_one(".result__title a")
                snippet_elem = result.select_one(".result__snippet")
                
                if title_elem:
                    results.append({
                        "title": title_elem.get_text(strip=True),
                        "url": title_elem.get("href", ""),
                        "snippet": snippet_elem.get_text(strip=True) if snippet_elem else ""
                    })
            
            return results[:10]
        
        except Exception as e:
            return [{"error": str(e)}]
    
    def _parse_page(self, url: str, response) -> PageInfo:
        """解析页面"""
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 提取标题
        title = soup.title.string if soup.title else ""
        
        # 提取正文
        # 移除脚本和样式
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        
        content = soup.get_text(separator="\n", strip=True)
        # 限制内容长度
        if len(content) > 5000:
            content = content[:5000] + "..."
        
        # 提取链接
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if href.startswith("http") and text:
                links.append({"url": href, "text": text})
        
        # 提取表单
        forms = []
        for form in soup.find_all("form"):
            action = form.get("action", "")
            method = form.get("method", "get").lower()
            inputs = []
            
            for inp in form.find_all(["input", "textarea", "select"]):
                inputs.append({
                    "name": inp.get("name", ""),
                    "type": inp.get("type", "text"),
                    "value": inp.get("value", "")
                })
            
            forms.append({
                "action": action,
                "method": method,
                "inputs": inputs
            })
        
        return PageInfo(
            url=url,
            title=title,
            content=content,
            links=links[:50],
            forms=forms,
            status_code=response.status_code
        )
    
    async def close(self):
        """关闭客户端"""
        await self.client.aclose()


# 全局浏览器客户端
_browser: Optional[BrowserClient] = None


def get_browser() -> BrowserClient:
    """获取浏览器客户端"""
    global _browser
    if _browser is None:
        _browser = BrowserClient()
    return _browser


@tool(
    name="web_fetch",
    description="获取网页内容。返回页面标题、正文、链接等信息。",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "网页 URL"
            },
            "extract": {
                "type": "string",
                "enum": ["all", "text", "links", "forms"],
                "description": "提取内容类型",
                "default": "all"
            }
        },
        "required": ["url"]
    }
)
async def web_fetch(url: str, extract: str = "all") -> dict:
    """获取网页"""
    try:
        browser = get_browser()
        page = await browser.get(url)
        
        result = {
            "url": page.url,
            "title": page.title,
            "status": page.status_code
        }
        
        if extract in ["all", "text"]:
            result["content"] = page.content
        
        if extract in ["all", "links"]:
            result["links"] = page.links
        
        if extract in ["all", "forms"]:
            result["forms"] = page.forms
        
        return result
    
    except Exception as e:
        return {"error": str(e)}


@tool(
    name="web_search",
    description="搜索网页。使用 DuckDuckGo 搜索引擎。",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词"
            },
            "engine": {
                "type": "string",
                "enum": ["duckduckgo", "google"],
                "description": "搜索引擎",
                "default": "duckduckgo"
            }
        },
        "required": ["query"]
    }
)
async def web_search(query: str, engine: str = "duckduckgo") -> dict:
    """搜索网页"""
    try:
        browser = get_browser()
        results = await browser.search(query, engine)
        return {"query": query, "results": results}
    
    except Exception as e:
        return {"error": str(e)}


@tool(
    name="web_submit_form",
    description="提交网页表单。",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "表单提交 URL"
            },
            "data": {
                "type": "object",
                "description": "表单数据"
            },
            "method": {
                "type": "string",
                "enum": ["post", "get"],
                "description": "请求方法",
                "default": "post"
            }
        },
        "required": ["url", "data"]
    }
)
async def web_submit_form(url: str, data: dict, method: str = "post") -> dict:
    """提交表单"""
    try:
        browser = get_browser()
        
        if method == "post":
            page = await browser.post(url, data=data)
        else:
            full_url = f"{url}?{'&'.join(f'{k}={v}' for k, v in data.items())}"
            page = await browser.get(full_url)
        
        return {
            "url": page.url,
            "title": page.title,
            "content": page.content[:2000],
            "status": page.status_code
        }
    
    except Exception as e:
        return {"error": str(e)}


@tool(
    name="extract_data",
    description="从网页中提取结构化数据。支持 CSS 选择器。",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "网页 URL"
            },
            "selector": {
                "type": "string",
                "description": "CSS 选择器"
            },
            "attribute": {
                "type": "string",
                "description": "提取的属性（如 href, src），默认提取文本",
                "default": "text"
            }
        },
        "required": ["url", "selector"]
    }
)
async def extract_data(url: str, selector: str, attribute: str = "text") -> dict:
    """提取网页数据"""
    try:
        browser = get_browser()
        page = await browser.get(url)
        
        soup = BeautifulSoup(page.content, "html.parser")
        elements = soup.select(selector)
        
        results = []
        for elem in elements[:100]:  # 限制数量
            if attribute == "text":
                results.append(elem.get_text(strip=True))
            elif attribute == "html":
                results.append(str(elem))
            else:
                value = elem.get(attribute, "")
                if value:
                    results.append(value)
        
        return {
            "url": url,
            "selector": selector,
            "count": len(results),
            "results": results
        }
    
    except Exception as e:
        return {"error": str(e)}
