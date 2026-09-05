"""Bounded tile access to a fixed official host; never proxy user URLs."""
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_tile(key: str, layer: str, z: int, x: int, y: int):
    if layer not in {"vec", "cva", "img", "cia"} or not 1 <= z <= 18 or not (0 <= x < 2**z and 0 <= y < 2**z):
        raise ValueError("无效瓦片坐标或图层")
    if not key:
        raise ValueError("请先配置天地图 Key")
    query = urlencode(dict(SERVICE="WMTS", REQUEST="GetTile", VERSION="1.0.0", LAYER=layer, STYLE="default", TILEMATRIXSET="w", FORMAT="tiles", TILEMATRIX=z, TILEROW=y, TILECOL=x, tk=key))
    request = Request(f"https://t0.tianditu.gov.cn/{layer}_w/wmts?{query}", headers={"User-Agent": "Angelus-GEOINT/1.0"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=8) as response:
            body = response.read(2 * 1024 * 1024 + 1)
            if len(body) > 2 * 1024 * 1024:
                raise RuntimeError("oversized tile")
            if body.startswith(b"\x89PNG\r\n\x1a\n"):
                mime = "image/png"
            elif body.startswith(b"\xff\xd8\xff"):
                mime = "image/jpeg"
            else:
                raise RuntimeError("not a raster tile")
            return body, mime
    except Exception:
        # Never include upstream URLs (which contain the key) in exceptions.
        raise RuntimeError("天地图瓦片读取失败，请检查 Key 权限、服务配额与网络") from None
