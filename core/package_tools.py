"""Package registry tools — PyPI and npm search / info.

Tools:
    pypi_search  Search PyPI packages
    npm_search   Search npm packages
    pypi_info    Get PyPI package details
    npm_info     Get npm package details
"""

from __future__ import annotations

import json
from urllib.parse import quote

import httpx


def pypi_search(query: str, limit: int = 10) -> str:
    """Search PyPI for packages matching query.

    Args:
        query: Search keyword
        limit: Max results (default 10)

    Returns:
        JSON array of matching packages
    """
    if not query:
        return "[错误] query 参数不能为空"
    try:
        resp = httpx.get(
            f"https://pypi.org/search/?q={quote(query)}",
            headers={"Accept": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("results", [])[:limit]:
            results.append(
                {
                    "name": item.get("name", ""),
                    "version": item.get("version", ""),
                    "summary": (item.get("summary", "") or "")[:200],
                    "released": item.get("release_date", ""),
                }
            )
        return json.dumps({"total": data.get("total", 0), "results": results}, ensure_ascii=False, indent=2)
    except httpx.HTTPError as e:
        return f"[错误] PyPI 搜索请求失败: {e}"


def npm_search(query: str, limit: int = 10) -> str:
    """Search npm registry for packages matching query.

    Args:
        query: Search keyword
        limit: Max results (default 10)

    Returns:
        JSON array of matching packages
    """
    if not query:
        return "[错误] query 参数不能为空"
    try:
        resp = httpx.get(
            "https://registry.npmjs.org/-/v1/search",
            params={"text": query, "size": limit},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for obj in data.get("objects", [])[:limit]:
            pkg = obj.get("package", {})
            results.append(
                {
                    "name": pkg.get("name", ""),
                    "version": pkg.get("version", ""),
                    "description": (pkg.get("description", "") or "")[:200],
                    "publisher": pkg.get("publisher", {}).get("username", ""),
                    "date": pkg.get("date", ""),
                }
            )
        return json.dumps({"total": data.get("total", 0), "results": results}, ensure_ascii=False, indent=2)
    except httpx.HTTPError as e:
        return f"[错误] npm 搜索请求失败: {e}"


def pypi_info(package: str) -> str:
    """Get detailed info for a PyPI package.

    Args:
        package: Exact package name

    Returns:
        JSON with package metadata
    """
    if not package:
        return "[错误] package 参数不能为空"
    try:
        resp = httpx.get(
            f"https://pypi.org/pypi/{quote(package, safe='')}/json",
            timeout=15,
        )
        if resp.status_code == 404:
            return f"[错误] 未找到 PyPI 包: {package}"
        resp.raise_for_status()
        data = resp.json()
        info = data.get("info", {})
        latest = info.get("version", "")
        # Extract requires_python if present
        requires_python = info.get("requires_python", "")
        return json.dumps(
            {
                "name": info.get("name", ""),
                "version": latest,
                "summary": info.get("summary", ""),
                "author": info.get("author", ""),
                "author_email": info.get("author_email", ""),
                "license": info.get("license", ""),
                "homepage": info.get("home_page", ""),
                "project_url": info.get("project_url", ""),
                "requires_python": requires_python,
                "classifiers": info.get("classifiers", []),
                "latest_version": latest,
                "releases": list(data.get("releases", {}).keys())[-5:],
            },
            ensure_ascii=False,
            indent=2,
        )
    except httpx.HTTPError as e:
        return f"[错误] PyPI 请求失败: {e}"


def npm_info(package: str) -> str:
    """Get detailed info for an npm package.

    Args:
        package: Exact package name

    Returns:
        JSON with package metadata
    """
    if not package:
        return "[错误] package 参数不能为空"
    try:
        resp = httpx.get(
            f"https://registry.npmjs.org/{quote(package, safe='')}",
            timeout=15,
        )
        if resp.status_code == 404:
            return f"[错误] 未找到 npm 包: {package}"
        resp.raise_for_status()
        data = resp.json()
        latest_tag = data.get("dist-tags", {}).get("latest", "")
        latest_info = data.get("versions", {}).get(latest_tag, {}) if latest_tag else {}
        return json.dumps(
            {
                "name": data.get("name", ""),
                "description": data.get("description", ""),
                "latest_version": latest_tag,
                "license": latest_info.get("license", ""),
                "homepage": latest_info.get("homepage", ""),
                "repository": latest_info.get("repository", {}),
                "author": data.get("author", {}),
                "maintainers": data.get("maintainers", []),
                "keywords": latest_info.get("keywords", []),
                "versions": list(data.get("versions", {}).keys())[-5:],
            },
            ensure_ascii=False,
            indent=2,
        )
    except httpx.HTTPError as e:
        return f"[错误] npm 请求失败: {e}"
